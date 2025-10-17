# app.py
from flask import Flask, render_template
from flask_cors import CORS
from routes.calls import calls_bp
from routes.audio import audio_bp
from database import init_db
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def create_app():
    app = Flask(__name__)
    CORS(app)
    app.logger.setLevel(logging.INFO)

    # Initialize DB (creates database.db and tables if missing)
    init_db()

    # Register blueprints
    app.register_blueprint(calls_bp)
    app.register_blueprint(audio_bp)

    return app

if __name__ == "__main__":
    create_app().run(debug=True, host="0.0.0.0", port=5000)
