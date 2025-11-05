# voice_utils.py
import os
import logging
import requests

logger = logging.getLogger("voice_utils")
logger.setLevel(logging.INFO)

# Read Deepgram API key from environment
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

def synthesize_audio(text: str, output_path: str, model: str = "aura-asteria-en") -> bool:
    """
    Use Deepgram to convert text to speech and save as audio file.
    Returns True on success, False on failure.
    
    Uses direct HTTP API call as per Deepgram documentation.
    """
    try:
        if not DEEPGRAM_API_KEY:
            logger.error("DEEPGRAM_API_KEY not set in environment variables")
            return False
        
        url = "https://api.deepgram.com/v1/speak"
        querystring = {"model": model}
        payload = {"text": text}
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, params=querystring)
        
        if response.status_code == 200:
            # Save the audio content to file
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"Saved TTS audio to {output_path}")
            return True
        else:
            logger.error(f"Deepgram API error: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.exception(f"Deepgram TTS error: {e}")
        return False
