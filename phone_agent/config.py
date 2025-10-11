# config.py
import os
from dotenv import load_dotenv
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:5000")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # for generative ai (gemini)
# Google Cloud TTS uses GOOGLE_APPLICATION_CREDENTIALS env var (recommended).
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

DATABASE_FILE = os.getenv("DATABASE_FILE", "database.db")
PRODUCTS_CSV = os.getenv("PRODUCTS_CSV", "Products.csv")
