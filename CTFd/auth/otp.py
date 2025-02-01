from flask import Blueprint, request, jsonify
from CTFd.utils.auth.lynx_client import LynxAuthClient
from CTFd.models import Users, db
from CTFd.utils.logging import log
from CTFd.utils.security.auth import login_user

# Create blueprint with url_prefix
otp = Blueprint('otp', __name__, url_prefix='/auth/otp')

@otp.route('/generate', methods=['POST'])
def generate_otp():
    # Initialize client within request context
    client = LynxAuthClient()
    
    data = request.get_json()
    roll_no = data.get('rollNo')
    
    if not roll_no:
        return jsonify({'success': False, 'message': 'Roll number is required'}), 400

    success, message = client.generate_otp(int(roll_no))
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'message': message}), 400

@otp.route('/verify', methods=['POST'])
def verify_otp():
    # Initialize client within request context
    client = LynxAuthClient()
    
    data = request.get_json()
    roll_no = data.get('rollNo')
    otp = data.get('otp')
    
    if not roll_no or not otp:
        return jsonify({'success': False, 'message': 'Roll number and OTP are required'}), 400

    success, message, details = client.verify_otp(int(roll_no), int(otp))
    if not success:
        return jsonify({'success': False, 'message': message}), 400

    # Extract user details
    name = details.fields['studentName'].string_value
    department = details.fields['studentDepartment'].string_value

    # Find or create user
    user = Users.query.filter_by(name=roll_no).first()
    if not user:
        user = Users(
            name=roll_no,
            email=f"{roll_no}@student.nitt.edu",
            password=None,
            verified=True
        )
        db.session.add(user)
    
    db.session.commit()
    login_user(user)
    
    log("logins", "[{date}] {ip} - {name} logged in via OTP", name=user.name)
    
    return jsonify({
        'success': True,
        'message': message,
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email
        }
    })