from flask import Blueprint
from CTFd.auth.otp import otp

# Create main auth blueprint
auth = Blueprint("auth", __name__)

# Register the OTP blueprint as a sub-blueprint
auth.register_blueprint(otp, url_prefix="/otp")

# Import other auth-related views and functionality
from CTFd.auth import views  # noqa: F401
