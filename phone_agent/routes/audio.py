# routes/audio.py
import base64
import io
import os
from flask import Blueprint, send_file, current_app

audio_bp = Blueprint("audio", __name__)

@audio_bp.route("/audio/<filename>", methods=["GET"])
def serve_audio(filename):
    try:
        actual_filename = base64.b64decode(filename).decode()
        if not os.path.exists(actual_filename):
            current_app.logger.error(f"Audio file not found: {actual_filename}")
            return "Audio file not found", 404
        with open(actual_filename, "rb") as audio_file:
            return send_file(io.BytesIO(audio_file.read()), mimetype="audio/mpeg")
    except Exception as e:
        current_app.logger.error(f"Error serving audio: {e}")
        return "Error serving audio", 500
