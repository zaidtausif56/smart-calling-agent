# app.py
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from routes.calls import calls_bp
from routes.audio import audio_bp
from routes.auth import auth_bp
from database import init_db
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    CORS(app)
    app.logger.setLevel(logging.INFO)

    # Initialize DB (creates database.db and tables if missing)
    init_db()
    logger.info("Database initialized successfully")

    # Register blueprints
    app.register_blueprint(calls_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(auth_bp)
    logger.info("All blueprints registered successfully")

    # Home route
    @app.route('/')
    def home():
        return jsonify({
            'status': 'success',
            'message': 'VIT Marketplace Phone Agent API',
            'endpoints': {
                'make_call': '/make_call',
                'start_conversation': '/start_conversation',
                'process_conversation': '/process_conversation',
                'audio': '/audio/<filename>',
                'auth': {
                    'send_otp': '/api/auth/send-otp',
                    'verify_otp': '/api/auth/verify-otp',
                    'orders': '/api/orders'
                }
            }
        })

    return app

if __name__ == "__main__":
    app = create_app()
    logger.info("Starting Flask application on http://0.0.0.0:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
