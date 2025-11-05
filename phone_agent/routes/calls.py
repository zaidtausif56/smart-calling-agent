from flask import Blueprint, request, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import tempfile
import base64
import os
import re
import logging
import pandas as pd

from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, WEBHOOK_BASE_URL, TTS_MODE, TWILIO_VOICE
from ai_agent import GeminiPhoneAgent
from voice_utils import synthesize_audio
from database import get_db_connection, add_order, get_last_order

calls_bp = Blueprint("calls", __name__)
logger = logging.getLogger("calls")
logger.setLevel(logging.INFO)

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
agent = GeminiPhoneAgent()

# Store user states across calls (in-memory)
# Structure: {phone: {"phase": str, "order": dict, "silence_count": int, "last_product": str, "last_price": float, "last_quantity": int, "address": str}}
user_states = {}

# Speech timeout - reduced for faster responses
SPEECH_TIMEOUT = 5  # seconds (increased to give user more time)
MAX_SILENCE_COUNT = 3  # Maximum number of times to handle silence before ending call


def _audio_url_for(path):
    token = base64.b64encode(path.encode()).decode()
    return f"{WEBHOOK_BASE_URL}/audio/{token}"


def _speak(response, text):
    """Convert text → TTS → Twilio play
    Uses TTS_MODE config to choose between fast (Twilio) or quality (Deepgram)
    Voice model can be configured via TWILIO_VOICE in .env
    """
    logger.info(f"Speaking to user: {text}")
    
    # For faster response, use Twilio's TTS directly
    if TTS_MODE == "fast":
        response.say(text, voice=TWILIO_VOICE, language='en-US')
        return
    
    # Use Deepgram for better quality (but slower)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    ok = synthesize_audio(text, tmp_path)
    if ok:
        response.play(_audio_url_for(tmp_path))
    else:
        # Fallback to Twilio TTS if Deepgram fails
        response.say(text, voice=TWILIO_VOICE, language='en-US')
    return


@calls_bp.route("/make_call", methods=["POST"])
def make_call():
    try:
        phone_number = request.json.get("phone_number")
        if not phone_number:
            return jsonify({"status": "error", "message": "phone_number required"}), 400

        logger.info(f"Initiating call to {phone_number}")
        
        if not WEBHOOK_BASE_URL:
            logger.error("WEBHOOK_BASE_URL not set in environment variables")
            return jsonify({"status": "error", "message": "Server configuration error"}), 500
        
        call = twilio_client.calls.create(
            url=WEBHOOK_BASE_URL + "/start_conversation",
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
    # For outbound calls, "To" is the user's number (recipient), "From" is Twilio's number
    user_number = request.values.get("To", "")
    
    logger.info(f"Starting conversation with {user_number}")

    # Greet returning users
    try:
        last = get_last_order(user_number)
        if last:
            product_name = last.get('product_name', last.get('product', 'your previous item'))
            qty = last.get('quantity', 1)
            msg = f"Welcome back! Your last order was for {qty} {product_name}. Would you like to reorder the same item?"
            _speak(response, msg)
            user_states[user_number] = {"phase": "awaiting_reorder_confirm", "order": last, "silence_count": 0}
            response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
            return str(response)
    except Exception as e:
        logger.exception("fetch last order failed")

    # Default greeting
    _speak(response, agent.greeting)
    response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
    return str(response)


@calls_bp.route("/process_conversation", methods=["POST"])
def process_conversation():
    response = VoiceResponse()
    # For outbound calls, "To" is the user's number (recipient), "From" is Twilio's number
    user_number = request.values.get("To", "")
    user_speech = (request.values.get("SpeechResult") or "").strip()

    # Initialize or get user state
    if user_number not in user_states:
        user_states[user_number] = {"phase": None, "silence_count": 0}
    
    state = user_states[user_number]

    logger.info(f"User {user_number} said: '{user_speech}' (phase={state.get('phase')}, silence_count={state.get('silence_count', 0)})")
    
    # Handle empty speech (silence or no input detected)
    if not user_speech:
        silence_count = state.get("silence_count", 0) + 1
        user_states[user_number]["silence_count"] = silence_count
        
        logger.info(f"Silence detected for {user_number}. Count: {silence_count}/{MAX_SILENCE_COUNT}")
        
        # Escalating prompts based on silence count
        if silence_count == 1:
            _speak(response, "I didn't catch that. Could you please repeat?")
        elif silence_count == 2:
            _speak(response, "Are you still there? Please let me know if you'd like to continue browsing or if I can help you with anything.")
        elif silence_count >= MAX_SILENCE_COUNT:
            _speak(response, "I haven't heard from you. I'll end this call now. Feel free to call back anytime. Thank you for contacting V-I-T Marketplace!")
            user_states.pop(user_number, None)
            # End call by not adding gather
            return str(response)
        else:
            _speak(response, "Hello? If you need more time to decide, that's okay. Just let me know when you're ready.")
        
        # Keep gathering input
        response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
        return str(response)
    
    # Reset silence counter when user speaks
    user_states[user_number]["silence_count"] = 0
    user_speech_lower = user_speech.lower()

    # ========== PHASE: AWAITING ADDRESS ==========
    if state.get("phase") == "awaiting_address":
        # User has provided their delivery address
        if user_speech and len(user_speech) > 5:  # Basic validation
            address = user_speech.strip()
            user_states[user_number]["address"] = address
            logger.info(f"Address received for {user_number}: {address}")
            
            # Now ask for final confirmation
            order = state["order"]
            product_name = order.get("product") or order.get("product_name")
            quantity = order.get("quantity", 1)
            price = order.get("price")
            total = price * quantity
            
            _speak(response, f"Thank you! So to confirm, I'm delivering {quantity} {product_name} for rupees {int(total)} to {address}. Shall I place the order?")
            user_states[user_number]["phase"] = "awaiting_final_confirm"
            response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
            return str(response)
        else:
            # Address is too short or invalid
            _speak(response, "I didn't catch your complete address. Could you please provide your full delivery address including street, area, and city?")
            response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
            return str(response)

    # ========== PHASE: AWAITING FINAL CONFIRMATION ==========
    if state.get("phase") == "awaiting_final_confirm":
        if any(w in user_speech_lower for w in ["yes", "confirm", "sure", "ok", "yeah", "yep", "place", "go ahead"]):
            order = state["order"]
            address = state.get("address", "No address provided")
            try:
                product_name = order.get("product") or order.get("product_name")
                quantity = order.get("quantity", 1)
                price = order.get("price")
                
                logger.info(f"Confirming order: {user_number}, {product_name}, qty={quantity}, price={price}, address={address}")
                
                add_order(user_number, product_name, quantity, price, address)
                _speak(response, f"Perfect! Your order for {quantity} {product_name} has been confirmed and will be delivered to {address}. Thank you for shopping with V-I-T Marketplace!")
                user_states.pop(user_number, None)
                # End call after confirmation
                return str(response)
                
            except Exception as e:
                logger.exception("DB insert failed")
                _speak(response, "Sorry, there was an issue confirming your order. Please try again later.")
                user_states.pop(user_number, None)
                return str(response)
        else:
            _speak(response, "No problem! Would you like to change something or cancel the order?")
            user_states[user_number] = {"phase": None, "silence_count": 0}
            response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
            return str(response)

    # ========== PHASE: AWAITING REORDER CONFIRM ==========
    if state.get("phase") == "awaiting_reorder_confirm":
        if any(w in user_speech_lower for w in ["yes", "confirm", "sure", "ok", "yeah", "yep"]):
            order = state["order"]
            product_name = order.get("product_name") or order.get("product")
            quantity = order.get("quantity", 1)
            price = order.get("total_price", 0) / quantity if quantity > 0 else order.get("price", 0)
            
            # Ask for delivery address before confirming reorder
            user_states[user_number] = {
                "phase": "awaiting_address",
                "order": {"product": product_name, "quantity": quantity, "price": price},
                "silence_count": 0
            }
            _speak(response, f"Great! Before I confirm your reorder for {quantity} {product_name}, please provide your delivery address including street, area, and city.")
            response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
            return str(response)
        else:
            _speak(response, "No problem! What would you like to explore today?")
            user_states[user_number] = {"phase": None, "silence_count": 0}
            response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
            return str(response)

    # ========== DEFAULT: AI CONVERSATION ==========
    logger.info(f"Sending to AI agent: {user_speech}")
    bot_text = agent.send_message(user_speech).strip()
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
    
    # ========== STORE PRODUCT/PRICE CONTEXT FROM AI RESPONSE ==========
    # Extract and store product details mentioned by AI for later use
    try:
        # First, extract quantity from user's speech or AI's response
        # Check user's speech first (e.g., "I would like to purchase 2")
        user_qty_match = re.search(r'\b(purchase|buy|order|want)\s+(\d+)\b', user_speech_lower)
        if user_qty_match:
            qty = int(user_qty_match.group(2))
            if qty < 100:  # Sanity check
                user_states[user_number]["last_quantity"] = qty
                logger.info(f"Stored quantity from user speech: {qty}")
        
        # Extract product name (look for known product types - expanded list)
        # Pattern: Look for brand/descriptor + product type, avoiding "order for" prefix
        product_name_match = re.search(r'(?:^|[^a-z])((?:[A-Z][\w-]*\s+)?(?:[A-Z][\w-]*\s+)?(headphones?|speaker|t-shirt|jeans|shoes?|flour|earbuds?|smartphone|laptop|watch|phone|tablet|bag|jacket|shirt|pants))', bot_text, re.IGNORECASE)
        if product_name_match:
            prod_name = product_name_match.group(1).strip()
            # Clean up the product name - remove extra prefixes
            prod_name = re.sub(r'^(your order for|order for|the)\s+', '', prod_name, flags=re.IGNORECASE).strip()
            # Remove leading numbers (quantities)
            prod_name = re.sub(r'^\d+\s+', '', prod_name).strip()
            user_states[user_number]["last_product"] = prod_name
            logger.info(f"Stored product name: {prod_name}")
        
        # Look for price mentions (avoid confusing price with quantity)
        # Pattern: "for 1999 rupees", "priced at 1999", "costs 1999"
        price_match = re.search(r'(?:for|at|costs?|price|priced at|available for)\s+(\d+)\s*rupees', bot_text, re.IGNORECASE)
        if not price_match:
            price_match = re.search(r'(?:total|amount)\s+(?:will be|is|are)\s*(\d+)\s*rupees', bot_text, re.IGNORECASE)
        
        if price_match:
            price_value = int(price_match.group(1))
            # Check if this looks like a unit price (< 10000) or total price
            if "total" in bot_text.lower() or price_value > 5000:
                user_states[user_number]["last_total"] = price_value
                # If we have quantity, calculate unit price
                if "last_quantity" in user_states[user_number] and user_states[user_number]["last_quantity"] > 1:
                    unit_price = price_value / user_states[user_number]["last_quantity"]
                    user_states[user_number]["last_price"] = unit_price
                    logger.info(f"Stored context: total={price_value}, unit_price={unit_price}")
                else:
                    user_states[user_number]["last_price"] = price_value
                    logger.info(f"Stored context: total/price={price_value}")
            else:
                # This is likely a unit price
                user_states[user_number]["last_price"] = price_value
                logger.info(f"Stored context: unit_price={price_value}")
        
        # Look for quantity mentions in AI's response (e.g., "order for 2 Speakers", "2 units")
        # Check if AI is confirming an order with quantity
        ai_qty_match = re.search(r'\b(?:order for|added|ordered)\s+(\d{1,2})\s+', bot_text, re.IGNORECASE)
        if ai_qty_match:
            qty = int(ai_qty_match.group(1))
            if qty < 100:  # Sanity check - quantities shouldn't be huge
                user_states[user_number]["last_quantity"] = qty
                logger.info(f"Stored quantity from AI: {qty}")
        elif "last_quantity" not in user_states[user_number]:
            # Default to 1 if no quantity mentioned
            user_states[user_number]["last_quantity"] = 1
            
    except Exception as e:
        logger.exception(f"Error storing context: {e}")
    
    # ========== DETECT ORDER PLACEMENT BY AI ==========
    # Check if AI has confirmed an order - using regex for more flexible matching
    order_confirmed_patterns = [
        r'order.*has been placed',
        r'order.*placed',
        r'order.*confirmed',
        r'purchase.*confirmed',
        r'order.*is being processed',
        r'order for \d+.*at \d+.*rupees',  # "order for 2 Speaker at 9998 rupees"
        r'processing your order'
    ]
    # Debug: Check each pattern
    matched_patterns = [pattern for pattern in order_confirmed_patterns if re.search(pattern, bot_text.lower())]
    order_confirmed = len(matched_patterns) > 0
    
    if matched_patterns:
        logger.info(f"✅ ORDER CONFIRMED DETECTED! Matched patterns: {matched_patterns}")
        logger.info(f"Bot text: {bot_text}")
    else:
        logger.debug(f"No order confirmation detected in: {bot_text[:100]}")
    
    # Also check if user is confirming purchase and AI is ready to finalize
    user_wants_to_proceed = any(phrase in user_speech_lower for phrase in ["yes", "proceed", "confirm", "go ahead", "i want to buy", "let's do it", "sure", "proceed to checkout"])
    ai_ready_to_finalize = any(keyword in bot_text.lower() for keyword in [
        "shall i go ahead", 
        "shall i confirm", 
        "confirm your purchase",
        "would you like me to process",
        "proceed to checkout",
        "process this for you"
    ])
    
    # If user confirms and AI is asking for final confirmation
    logger.info(f"Check: user_wants_to_proceed={user_wants_to_proceed}, ai_ready_to_finalize={ai_ready_to_finalize}")
    
    if user_wants_to_proceed and ai_ready_to_finalize:
        logger.info("✅ User confirming purchase, AI asking for final confirmation. Asking for address...")
        
        try:
            # Use stored context
            product_name = user_states[user_number].get("last_product", "Unknown Product")
            unit_price = user_states[user_number].get("last_price", 0)
            quantity = user_states[user_number].get("last_quantity", 1)
            
            if unit_price > 0 and product_name != "Unknown Product":
                logger.info(f"Preparing order: {user_number}, {product_name}, qty={quantity}, price={unit_price}")
                
                # Store order details and ask for address
                user_states[user_number]["order"] = {
                    "product": product_name,
                    "quantity": quantity,
                    "price": unit_price
                }
                user_states[user_number]["phase"] = "awaiting_address"
                
                # Ask for delivery address
                bot_text = f"Great! Before I confirm your order for {quantity} {product_name}, I'll need your delivery address. Please provide your complete address including street, area, and city."
            else:
                logger.warning(f"Insufficient context to prepare order: product={product_name}, price={unit_price}")
        except Exception as e:
            logger.exception(f"Error preparing order: {e}")
    
    if order_confirmed:
        logger.info("AI confirmed an order. Attempting to extract order details...")
        
        # Try to extract product name and quantity from the AI's response
        try:
            # Pattern 1: "order for [quantity] [product] at [price]" or "order for [product] has been"
            # Stop at: "at", "for", "has been", "is being", or punctuation
            match = re.search(r'order for (?:the\s+)?(?:(\d+)\s+)?([A-Za-z\s]+?)(?:\s+at\s+\d+|\s+for\s+\d+|\s+has been|\s+is being|\.)', bot_text, re.IGNORECASE)
            
            if match:
                quantity_str = match.group(1)  # May be None
                product_name = match.group(2).strip()
                
                # Parse quantity
                if quantity_str:
                    try:
                        quantity = int(quantity_str)
                    except:
                        word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
                        quantity = word_to_num.get(quantity_str.lower(), 1)
                else:
                    # Use stored quantity or default to 1
                    quantity = user_states[user_number].get("last_quantity", 1)
                
                logger.info(f"Extracted from order confirmation: product={product_name}, qty={quantity}")
                
                # Try to extract price from current response
                price_match = re.search(r'(\d+)\s*rupees', bot_text, re.IGNORECASE)
                
                if price_match:
                    total_price = int(price_match.group(1))
                    unit_price = total_price / quantity if quantity > 0 else total_price
                    logger.info(f"Price from message: {unit_price}")
                else:
                    # If no price in current message, use stored context
                    logger.info("No price in confirmation message, using stored context")
                    unit_price = user_states[user_number].get("last_price", 0)
                    if unit_price == 0:
                        total = user_states[user_number].get("last_total", 0)
                        unit_price = total / quantity if quantity > 0 and total > 0 else 0
                    logger.info(f"Price from context: {unit_price}")
                
                if unit_price > 0:
                    # Store order details and ask for address instead of saving immediately
                    logger.info(f"Preparing order: {user_number}, {product_name}, qty={quantity}, price={unit_price}")
                    
                    user_states[user_number]["order"] = {
                        "product": product_name,
                        "quantity": quantity,
                        "price": unit_price
                    }
                    user_states[user_number]["phase"] = "awaiting_address"
                    
                    # Override AI response to ask for address
                    bot_text = f"Perfect! Before I confirm your order for {quantity} {product_name}, I'll need your delivery address. Please provide your complete address including street, area, and city."
                else:
                    logger.error(f"Could not determine price for order. Product={product_name}, Qty={quantity}")
            else:
                # Try to use fully stored context if pattern doesn't match
                logger.info("Pattern didn't match, trying stored context")
                product_name = user_states[user_number].get("last_product")
                unit_price = user_states[user_number].get("last_price")
                quantity = user_states[user_number].get("last_quantity", 1)
                
                if product_name and unit_price:
                    logger.info(f"Preparing order from stored context: {user_number}, {product_name}, qty={quantity}, price={unit_price}")
                    
                    user_states[user_number]["order"] = {
                        "product": product_name,
                        "quantity": quantity,
                        "price": unit_price
                    }
                    user_states[user_number]["phase"] = "awaiting_address"
                    
                    # Override AI response to ask for address
                    bot_text = f"Perfect! Before I confirm your order for {quantity} {product_name}, I'll need your delivery address. Please provide your complete address including street, area, and city."
                else:
                    logger.error(f"Insufficient stored context. Product={product_name}, Price={unit_price}")
        except Exception as e:
            logger.exception(f"Error extracting order details: {e}")
    
    # NOTE: Buy intent detection removed - the AI agent handles the entire conversation flow
    # naturally without needing manual phase transitions. The AI can query products,
    # provide information, and guide the user through the purchase process.

    # Handle EXIT command
    if bot_text.endswith("EXIT"):
        goodbye_msg = bot_text[:-4].strip() if len(bot_text) > 4 else "Thank you for calling V-I-T Marketplace. Goodbye!"
        _speak(response, goodbye_msg)
        user_states.pop(user_number, None)
        return str(response)
    
    # Normal response
    _speak(response, bot_text)
    response.gather(input="speech", action="/process_conversation", timeout=SPEECH_TIMEOUT, language="en-US")
    return str(response)
