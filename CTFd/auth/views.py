from flask import jsonify
from CTFd.auth import auth

@auth.route('/status')
def auth_status():
    return jsonify({
        'success': True,
        'message': 'Authentication service is running'
    })
