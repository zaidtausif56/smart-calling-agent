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
logger.setLevel(logging.INFO)

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
agent = GeminiPhoneAgent()

# Store user states across calls (in-memory)
user_states = {}  # {phone: {"phase": "asking_product"/"awaiting_confirm", "order": {...}}}


def _audio_url_for(path):
    token = base64.b64encode(path.encode()).decode()
    return f"{WEBHOOK_BASE_URL}/audio/{token}"


def _speak(response, text):
    """Convert text → Deepgram TTS → Twilio play, fallback to .say"""
    logger.info(f"Speaking to user: {text}")
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

        logger.info(f"Initiating call to {phone_number}")
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
    
    logger.info(f"Starting conversation with {from_number}")

    # Greet returning users
    try:
        last = get_last_order(from_number)
        if last:
            product_name = last.get('product_name', last.get('product', 'your previous item'))
            qty = last.get('quantity', 1)
            msg = f"Welcome back! Your last order was for {qty} {product_name}. Would you like to reorder the same item?"
            _speak(response, msg)
            user_states[from_number] = {"phase": "awaiting_reorder_confirm", "order": last}
            response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
            return str(response)
    except Exception as e:
        logger.exception("fetch last order failed")

    # Default greeting
    _speak(response, agent.greeting)
    response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
    return str(response)


@calls_bp.route("/process_conversation", methods=["POST"])
def process_conversation():
    response = VoiceResponse()
    from_number = request.values.get("From", "")
    user_speech = (request.values.get("SpeechResult") or "").strip()

    state = user_states.get(from_number, {"phase": None})

    logger.info(f"User {from_number} said: '{user_speech}' (phase={state.get('phase')})")
    
    # Handle empty speech
    if not user_speech:
        _speak(response, "I didn't catch that. Could you please repeat?")
        response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
        return str(response)

    user_speech_lower = user_speech.lower()

    # ========== PHASE: AWAITING CONFIRMATION ==========
    if state.get("phase") == "awaiting_confirm":
        if any(w in user_speech_lower for w in ["yes", "confirm", "sure", "ok", "yeah", "yep"]):
            order = state["order"]
            try:
                product_name = order.get("product") or order.get("product_name")
                quantity = order.get("quantity", 1)
                price = order.get("price")
                
                logger.info(f"Confirming order: {from_number}, {product_name}, qty={quantity}, price={price}")
                
                add_order(from_number, product_name, quantity, price)
                _speak(response, f"Great! Your order for {quantity} {product_name} has been confirmed. Thank you for shopping with V-I-T Marketplace!")
                user_states.pop(from_number, None)
                # End call after confirmation
                return str(response)
                
            except Exception as e:
                logger.exception("DB insert failed")
                _speak(response, "Sorry, there was an issue confirming your order. Please try again later.")
                user_states.pop(from_number, None)
                return str(response)
        else:
            _speak(response, "No problem! Is there anything else I can help you with today?")
            user_states.pop(from_number, None)
            response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
            return str(response)

    # ========== PHASE: AWAITING PRODUCT NAME ==========
    if state.get("phase") == "asking_product":
        product_name = user_speech.strip().title()
        logger.info(f"User looking for product: {product_name}")
        
        try:
            df = pd.read_sql_query(
                'SELECT * FROM inventory WHERE "Product Name" LIKE ? LIMIT 1', 
                conn, 
                params=(f"%{product_name}%",)
            )
            
            if not df.empty:
                row = df.iloc[0]
                price = float(row.get("Price in Rupees", row.get("Price", 0)))
                product_actual = row["Product Name"]
                stock = int(row.get("Stock", 0))
                
                if stock > 0:
                    user_states[from_number] = {
                        "phase": "awaiting_confirm",
                        "order": {"product": product_actual, "quantity": 1, "price": price},
                    }
                    _speak(response, f"Great! One {product_actual} costs rupees {int(price)}. We have {stock} units in stock. Would you like to confirm your order?")
                else:
                    _speak(response, f"Sorry, {product_actual} is currently out of stock. Would you like to check another product?")
                    user_states.pop(from_number, None)
            else:
                _speak(response, f"I couldn't find {product_name} in our inventory. Could you try saying the product name differently, or ask me what products we have available?")
                
            response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
            return str(response)
            
        except Exception as e:
            logger.exception("Product lookup failed")
            _speak(response, "Sorry, I'm having trouble checking our inventory. Please try again.")
            response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
            return str(response)

    # ========== PHASE: AWAITING REORDER CONFIRM ==========
    if state.get("phase") == "awaiting_reorder_confirm":
        if any(w in user_speech_lower for w in ["yes", "confirm", "sure", "ok", "yeah", "yep"]):
            order = state["order"]
            product_name = order.get("product_name") or order.get("product")
            quantity = order.get("quantity", 1)
            price = order.get("total_price", 0) / quantity if quantity > 0 else order.get("price", 0)
            
            try:
                add_order(from_number, product_name, quantity, price)
                _speak(response, f"Perfect! I've rebooked your order for {quantity} {product_name}. Thank you!")
                user_states.pop(from_number, None)
                return str(response)
            except Exception as e:
                logger.exception("Reorder failed")
                _speak(response, "Sorry, there was an issue processing your reorder.")
                user_states.pop(from_number, None)
                return str(response)
        else:
            _speak(response, "No problem! What would you like to explore today?")
            user_states.pop(from_number, None)
            response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
            return str(response)

    # ========== DEFAULT: AI CONVERSATION ==========
    logger.info(f"Sending to AI agent: {user_speech}")
    bot_text = agent.send(user_speech).strip()
    logger.info(f"AI agent response: {bot_text}")
    
    # SAFETY CHECK: Never speak SQL queries or raw SQL response data to user
    # Check if response looks like a SQL query or raw database dump
    if bot_text.startswith("SQL:"):
        logger.error(f"SQL query detected in bot response! This should never happen: {bot_text}")
        bot_text = "I'm having trouble finding that information. Could you please rephrase your question?"
    elif bot_text.startswith("SQL Response:"):
        logger.error(f"Raw SQL response detected in bot response! This should never happen: {bot_text[:200]}")
        bot_text = "I found some information but I'm having trouble presenting it. Could you ask me again?"
    elif "Product Name" in bot_text and "Price in Rupees" in bot_text:
        # Looks like a data table dump
        logger.error(f"Database table dump detected in bot response: {bot_text[:200]}")
        bot_text = "I found the information but I'm having trouble explaining it properly. Could you please ask again?"
    
    # Detect buy intent
    if re.search(r"\b(buy|order|purchase|want)\b", user_speech_lower, re.IGNORECASE):
        _speak(response, "Great! What product would you like to buy?")
        user_states[from_number] = {"phase": "asking_product"}
        response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
        return str(response)

    # Handle EXIT command
    if bot_text.endswith("EXIT"):
        goodbye_msg = bot_text[:-4].strip() if len(bot_text) > 4 else "Thank you for calling V-I-T Marketplace. Goodbye!"
        _speak(response, goodbye_msg)
        user_states.pop(from_number, None)
        return str(response)
    
    # Normal response
    _speak(response, bot_text)
    response.gather(input="speech", action=f"{WEBHOOK_BASE_URL}/process_conversation", timeout=5, language="en-US")
    return str(response)
