"""
Authentication routes for OTP-based login system
"""
from flask import Blueprint, request, jsonify
from twilio.rest import Client
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
from database import store_otp, verify_otp_code, get_orders_by_phone, update_order_status, delete_order
import jwt
import datetime
import secrets
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Secret key for JWT (in production, store this in environment variables)
JWT_SECRET = secrets.token_hex(32)

# Initialize Twilio client
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    logger.info("Twilio client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Twilio client: {e}")
    twilio_client = None


@auth_bp.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to the provided phone number via Twilio SMS"""
    try:
        data = request.json
        phone_number = data.get('phoneNumber', '').strip()
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
        
        # Ensure phone number has country code
        if not phone_number.startswith('+'):
            # Assuming Indian numbers by default, adjust as needed
            phone_number = '+91' + phone_number.lstrip('0')
        
        # Generate 6-digit OTP
        otp = str(secrets.randbelow(900000) + 100000)
        
        # Store OTP in database (expires in 10 minutes)
        store_otp(phone_number, otp)
        
        # Send OTP via Twilio
        if twilio_client:
            try:
                message = twilio_client.messages.create(
                    from_=TWILIO_PHONE_NUMBER,
                    body=f'Your OTP for login is: {otp}. Valid for 10 minutes.',
                    to=phone_number
                )
                logger.info(f"OTP sent to {phone_number}, Message SID: {message.sid}")
                
                return jsonify({
                    'success': True,
                    'message': 'OTP sent successfully',
                    'messageSid': message.sid
                }), 200
                
            except Exception as twilio_error:
                logger.error(f"Twilio error: {twilio_error}")
                # For development: return OTP in response if Twilio fails
                return jsonify({
                    'success': True,
                    'message': 'OTP generated (Twilio unavailable)',
                    'otp': otp  # Remove this in production!
                }), 200
        else:
            # Development mode: return OTP directly
            logger.warning(f"Twilio client not available. OTP for {phone_number}: {otp}")
            return jsonify({
                'success': True,
                'message': 'OTP generated (dev mode)',
                'otp': otp  # Remove this in production!
            }), 200
            
    except Exception as e:
        logger.exception(f"Error sending OTP: {e}")
        return jsonify({'error': 'Failed to send OTP'}), 500


@auth_bp.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP and return JWT token"""
    try:
        data = request.json
        phone_number = data.get('phoneNumber', '').strip()
        otp = data.get('otp', '').strip()
        
        if not phone_number or not otp:
            return jsonify({'error': 'Phone number and OTP are required'}), 400
        
        # Ensure phone number has country code
        if not phone_number.startswith('+'):
            phone_number = '+91' + phone_number.lstrip('0')
        
        # Verify OTP
        if verify_otp_code(phone_number, otp):
            # Generate JWT token
            token = jwt.encode({
                'phone_number': phone_number,
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
            }, JWT_SECRET, algorithm='HS256')
            
            logger.info(f"Login successful for {phone_number}")
            
            return jsonify({
                'success': True,
                'token': token,
                'phoneNumber': phone_number
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid or expired OTP'
            }), 401
            
    except Exception as e:
        logger.exception(f"Error verifying OTP: {e}")
        return jsonify({'error': 'Failed to verify OTP'}), 500


@auth_bp.route('/api/orders', methods=['GET'])
def get_orders():
    """Get all orders for the authenticated user"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            phone_number = payload['phone_number']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        # Get orders from database
        orders = get_orders_by_phone(phone_number)
        
        return jsonify({
            'success': True,
            'orders': orders,
            'phoneNumber': phone_number
        }), 200
        
    except Exception as e:
        logger.exception(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500


@auth_bp.route('/api/orders/<string:order_id>', methods=['GET'])
def get_order_detail(order_id):
    """Get details of a specific order"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            phone_number = payload['phone_number']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        # Get all orders and find the specific one
        orders = get_orders_by_phone(phone_number)
        order = next((o for o in orders if str(o['id']) == str(order_id)), None)
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        return jsonify({
            'success': True,
            'order': order
        }), 200
        
    except Exception as e:
        logger.exception(f"Error fetching order detail: {e}")
        return jsonify({'error': 'Failed to fetch order detail'}), 500


@auth_bp.route('/api/orders/<string:order_id>', methods=['PATCH'])
def update_order(order_id):
    """Update order status"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            phone_number = payload['phone_number']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        data = request.json
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
        
        # Update order status
        success = update_order_status(order_id, phone_number, new_status)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Order updated successfully'
            }), 200
        else:
            return jsonify({'error': 'Order not found or unauthorized'}), 404
        
    except Exception as e:
        logger.exception(f"Error updating order: {e}")
        return jsonify({'error': 'Failed to update order'}), 500


@auth_bp.route('/api/orders/<string:order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Cancel (delete) an order"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            phone_number = payload['phone_number']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        # Delete order
        success = delete_order(order_id, phone_number)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Order cancelled successfully'
            }), 200
        else:
            return jsonify({'error': 'Order not found or unauthorized'}), 404
        
    except Exception as e:
        logger.exception(f"Error cancelling order: {e}")
        return jsonify({'error': 'Failed to cancel order'}), 500
