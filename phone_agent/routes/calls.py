from flask import Blueprint, request, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import tempfile
import base64
import os
import re
import logging
import pandas as pd

from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, WEBHOOK_BASE_URL
from ai_agent import GeminiPhoneAgent
from voice_utils import synthesize_audio
from database import conn, add_order, get_last_order

calls_bp = Blueprint("calls", __name__)
logger = logging.getLogger("calls")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
agent = GeminiPhoneAgent()

# Store user states across calls (in-memory)
user_states = {}  # {phone: {"phase": "asking_product"/"awaiting_confirm", "order": {...}}}


def _audio_url_for(path):
    token = base64.b64encode(path.encode()).decode()
    return f"{WEBHOOK_BASE_URL}/audio/{token}"


def _speak(response, text):
    """Convert text → Deepgram TTS → Twilio play, fallback to .say"""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    ok = synthesize_audio(text, tmp_path)
    if ok:
        response.play(_audio_url_for(tmp_path))
    else:
        response.say(text)
    return


@calls_bp.route("/make_call", methods=["POST"])
def make_call():
    try:
        phone_number = request.json.get("phone_number")
        if not phone_number:
            return jsonify({"status": "error", "message": "phone_number required"}), 400

        call = twilio_client.calls.create(
            url=f"{WEBHOOK_BASE_URL}/start_conversation",
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER,
        )
        return jsonify({"status": "success", "call_sid": call.sid})
    except Exception as e:
        logger.exception("make_call error")
        return jsonify({"status": "error", "message": str(e)}), 500


@calls_bp.route("/start_conversation", methods=["POST"])
def start_conversation():
    response = VoiceResponse()
    from_number = request.values.get("From", "")

    # Greet returning users
    try:
        last = get_last_order(from_number)
        if last:
            msg = f"Welcome back! Your last order was for {last['quantity']} {last.get('product_name', last.get('product'))}. Would you like to reorder?"
            _speak(response, msg)
            user_states[from_number] = {"phase": "awaiting_reorder_confirm", "order": last}
            response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
            return str(response)
    except Exception:
        logger.exception("fetch last order failed")

    # Default greeting
    _speak(response, agent.greeting)
    response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
    return str(response)


@calls_bp.route("/process_conversation", methods=["POST"])
def process_conversation():
    response = VoiceResponse()
    from_number = request.values.get("From", "")
    user_speech = (request.values.get("SpeechResult") or "").strip().lower()

    state = user_states.get(from_number, {"phase": None})

    logger.info("User %s said: %s (phase=%s)", from_number, user_speech, state.get("phase"))

    # ========== PHASE: AWAITING CONFIRMATION ==========
    if state.get("phase") == "awaiting_confirm":
        if any(w in user_speech for w in ["yes", "confirm", "sure", "ok", "yeah"]):
            order = state["order"]
            try:
                product_name = order.get("product") or order.get("product_name")
                add_order(from_number, product_name, order.get("quantity", 1), order.get("price"))
                _speak(response, f"✅ Your order for {order.get('quantity',1)} {product_name} has been confirmed. Thank you!")
            except Exception:
                logger.exception("DB insert failed")
                _speak(response, "Sorry, there was an issue confirming your order. Please try again.")
        else:
            _speak(response, "Order cancelled. Would you like to check other products?")
        user_states.pop(from_number, None)
        response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
        return str(response)

    # ========== PHASE: AWAITING PRODUCT NAME ==========
    if state.get("phase") == "asking_product":
        product_name = user_speech.strip().title()
        try:
            df = pd.read_sql_query('SELECT * FROM inventory WHERE "Product Name" LIKE ? LIMIT 1', conn, params=(f"%{product_name}%",))
            if not df.empty:
                row = df.iloc[0]
                price = int(row.get("Price in Rupees", row.get("Price", 0)))
                product_actual = row["Product Name"]
                user_states[from_number] = {
                    "phase": "awaiting_confirm",
                    "order": {"product": product_actual, "quantity": 1, "price": price},
                }
                _speak(response, f"One {product_actual} costs ₹{price}. Would you like to confirm your order?")
            else:
                _speak(response, "Sorry, that product was not found. Try saying another name.")
                response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
                return str(response)
        except Exception:
            logger.exception("Product lookup failed")
            _speak(response, "Sorry, something went wrong checking the product.")
        response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
        return str(response)

    # ========== PHASE: AWAITING REORDER CONFIRM ==========
    if state.get("phase") == "awaiting_reorder_confirm":
        if any(w in user_speech for w in ["yes", "confirm", "sure", "ok", "yeah"]):
            order = state["order"]
            product_name = order.get("product_name") or order.get("product")
            add_order(from_number, product_name, order.get("quantity", 1), order.get("price"))
            _speak(response, f"Your previous order for {product_name} has been rebooked. Thank you!")
        else:
            _speak(response, "Alright, let's explore something new!")
        user_states.pop(from_number, None)
        response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
        return str(response)

    # ========== DEFAULT: AI CONVERSATION ==========
    bot_text = agent.send(user_speech).strip()

    # Detect buy intent
    if re.search(r"\b(buy|order|purchase|want)\b", user_speech, re.IGNORECASE):
        _speak(response, "Sure! What product would you like to buy?")
        user_states[from_number] = {"phase": "asking_product"}
        response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
        return str(response)

    # Normal response flow
    if bot_text.endswith("EXIT"):
        _speak(response, bot_text[:-4])
        return str(response)
    _speak(response, bot_text)
    response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=3, language="en-US")
    return str(response)
