# voice_utils.py
import os
import logging
from io import BytesIO

from deepgram import DeepgramClient

logger = logging.getLogger("voice_utils")
logger.setLevel(logging.INFO)  # change as needed

# Read key from .env (optional — DeepgramClient() will often read from env itself)
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Initialize Deepgram client. If DEEPGRAM_API_KEY is None, DeepgramClient() may still pick it from env.
deepgram = DeepgramClient()

def synthesize_audio(text: str, output_path: str, model: str = "aura-2-thalia-en") -> bool:
    """
    Use Deepgram to convert text to speech and save as MP3.
    Returns True on success, False on failure.

    Uses the new SDK API: deepgram.speak.v1.audio.generate(...)
    """
    try:
        # Call the new SDK TTS generation API
        response = deepgram.speak.v1.audio.generate(
            text=text,
            model=model
        )

        # response.stream is a BytesIO-like object. Get the bytes and write to file.
        # Defensive: check for .stream attribute
        if not hasattr(response, "stream"):
            logger.error("Deepgram response has no 'stream' attribute.")
            return False

        # Some SDK versions return a BytesIO, some return a wrapper with getvalue()
        stream = response.stream
        if hasattr(stream, "getvalue"):
            audio_bytes = stream.getvalue()
        else:
            # Fallback: read from stream
            audio_bytes = stream.read() if hasattr(stream, "read") else None

        if not audio_bytes:
            logger.error("No audio bytes received from Deepgram.")
            return False

        # Save bytes to output_path
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        logger.info(f"Saved TTS audio to {output_path}")
        return True

    except Exception as e:
        logger.exception(f"Deepgram TTS error: {e}")
        return False
