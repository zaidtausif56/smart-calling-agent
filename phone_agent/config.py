# config.py
import os
from dotenv import load_dotenv
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:5000")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # for generative ai (gemini)
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")  # for TTS
# Google Cloud TTS uses GOOGLE_APPLICATION_CREDENTIALS env var (recommended).
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

DATABASE_FILE = os.getenv("DATABASE_FILE", "database.db")
PRODUCTS_CSV = os.getenv("PRODUCTS_CSV", "Products.csv")

# TTS Configuration
# Set to 'fast' for Twilio's built-in TTS (faster response, good quality)
# Set to 'quality' for Deepgram TTS (slower response, better quality)
TTS_MODE = os.getenv("TTS_MODE", "fast")  # Options: 'fast' or 'quality'

# Twilio TTS Voice (used when TTS_MODE is 'fast')
# Options: Polly.Joanna, Polly.Salli, Polly.Matthew, Polly.Joey, etc.
# See: https://www.twilio.com/docs/voice/twiml/say/text-speech#amazon-polly
TWILIO_VOICE = os.getenv("TWILIO_VOICE", "Polly.Joanna")
