import requests
import os
from dotenv import load_dotenv

load_dotenv()

from flask import Blueprint, abort
from flask import current_app as app
from flask import redirect, render_template, request, session, url_for

from CTFd.cache import clear_team_session, clear_user_session
from CTFd.exceptions.email import (
    UserConfirmTokenInvalidException,
    UserResetPasswordTokenInvalidException,
)
from CTFd.models import Brackets, Teams, UserFieldEntries, UserFields, Users, db
from CTFd.utils import config, email, get_app_config, get_config
from CTFd.utils import user as current_user
from CTFd.utils import validators
from CTFd.utils.config import is_teams_mode
from CTFd.utils.config.integrations import mlc_registration
from CTFd.utils.config.visibility import registration_visible
from CTFd.utils.crypto import verify_password
from CTFd.utils.decorators import ratelimit
from CTFd.utils.decorators.visibility import check_registration_visibility
from CTFd.utils.helpers import error_for, get_errors, markup
from CTFd.utils.logging import log
from CTFd.utils.modes import TEAMS_MODE
from CTFd.utils.security.auth import login_user, logout_user
from CTFd.utils.security.email import (
    remove_email_confirm_token,
    remove_reset_password_token,
    verify_email_confirm_token,
    verify_reset_password_token,
)
from CTFd.utils.validators import ValidationError

auth = Blueprint("auth", __name__)

from CTFd.utils.grpc import AuthenticationClient  # Update this line
from CTFd.utils import get_config

def get_auth_client():
    """Get a configured AuthenticationClient instance"""
    # import os
    
    # Original code for getting the client
    # from CTFd.utils.grpc import AuthenticationClient
    
    host = os.getenv('GRPC_HOST', 'grpc.lcas.spider-nitt.org')
    port = int(os.getenv('GRPC_PORT', '443'))
    
    # Debug logging
    print(f"gRPC Configuration:")
    print(f"Host: {host}")
    print(f"Port: {port}")
    
    # Use secure channel for port 443
    use_ssl = port == 443
    
    return AuthenticationClient(
        host=host,
        port=port,
        use_ssl=use_ssl
    )

# Replace this:
# auth_client = get_auth_client()

# With a function that returns the client when needed:
def get_active_auth_client():
    """Get an instance of the AuthenticationClient only when needed"""
    # from CTFd.utils.grpc import AuthenticationClient
    import os
    
    host = os.getenv('GRPC_HOST', 'grpc.lcas.spider-nitt.org')
    port = int(os.getenv('GRPC_PORT', '443'))
    use_ssl = port == 443
    
    return AuthenticationClient(
        host=host,
        port=port,
        use_ssl=use_ssl
    )

@auth.route("/confirm", methods=["POST", "GET"])
@auth.route("/confirm/<data>", methods=["POST", "GET"])
@ratelimit(method="POST", limit=10, interval=60)
def confirm(data=None):
    if not get_config("verify_emails"):
        # If the CTF doesn't care about confirming email addresses then redierct to challenges
        return redirect(url_for("challenges.listing"))

    # User is confirming email account
    if data and request.method == "GET":
        try:
            user_email = verify_email_confirm_token(data)
        except (UserConfirmTokenInvalidException):
            return render_template(
                "confirm.html",
                errors=["Your confirmation link is invalid, please generate a new one"],
            )

        user = Users.query.filter_by(email=user_email).first_or_404()
        if user.verified:
            return redirect(url_for("views.settings"))

        user.verified = True
        log(
            "registrations",
            format="[{date}] {ip} - successful confirmation for {name}",
            name=user.name,
        )
        db.session.commit()
        remove_email_confirm_token(data)
        clear_user_session(user_id=user.id)
        email.successful_registration_notification(user.email)
        db.session.close()
        if current_user.authed():
            return redirect(url_for("challenges.listing"))
        return redirect(url_for("auth.login"))

    # User is trying to start or restart the confirmation flow
    if current_user.authed() is False:
        return redirect(url_for("auth.login"))

    user = Users.query.filter_by(id=session["id"]).first_or_404()
    if user.verified:
        return redirect(url_for("views.settings"))

    if data is None:
        if request.method == "POST":
            # User wants to resend their confirmation email
            email.verify_email_address(user.email)
            log(
                "registrations",
                format="[{date}] {ip} - {name} initiated a confirmation email resend",
                name=user.name,
            )
            return render_template(
                "confirm.html", infos=[f"Confirmation email sent to {user.email}!"]
            )
        elif request.method == "GET":
            # User has been directed to the confirm page
            return render_template("confirm.html")


@auth.route("/reset_password", methods=["POST", "GET"])
@auth.route("/reset_password/<data>", methods=["POST", "GET"])
@ratelimit(method="POST", limit=10, interval=60)
def reset_password(data=None):
    if config.can_send_mail() is False:
        return render_template(
            "reset_password.html",
            errors=[
                markup(
                    "This CTF is not configured to send email.<br> Please contact an organizer to have your password reset."
                )
            ],
        )

    if data is not None:
        try:
            email_address = verify_reset_password_token(data)
        except (UserResetPasswordTokenInvalidException):
            return render_template(
                "reset_password.html",
                errors=["Your reset link is invalid, please generate a new one"],
            )

        if request.method == "GET":
            return render_template("reset_password.html", mode="set")
        if request.method == "POST":
            password = request.form.get("password", "").strip()
            user = Users.query.filter_by(email=email_address).first_or_404()
            if user.oauth_id:
                return render_template(
                    "reset_password.html",
                    infos=[
                        "Your account was registered via an authentication provider and does not have an associated password. Please login via your authentication provider."
                    ],
                )

            pass_short = len(password) == 0
            if pass_short:
                return render_template(
                    "reset_password.html", errors=["Please pick a longer password"]
                )

            user.password = password
            db.session.commit()
            remove_reset_password_token(data)
            clear_user_session(user_id=user.id)
            log(
                "logins",
                format="[{date}] {ip} - successful password reset for {name}",
                name=user.name,
            )
            db.session.close()
            email.password_change_alert(user.email)
            return redirect(url_for("auth.login"))

    if request.method == "POST":
        email_address = request.form["email"].strip()
        user = Users.query.filter_by(email=email_address).first()

        get_errors()

        if not user:
            return render_template(
                "reset_password.html",
                infos=[
                    "If that account exists you will receive an email, please check your inbox"
                ],
            )

        if user.oauth_id:
            return render_template(
                "reset_password.html",
                infos=[
                    "The email address associated with this account was registered via an authentication provider and does not have an associated password. Please login via your authentication provider."
                ],
            )

        email.forgot_password(email_address)

        return render_template(
            "reset_password.html",
            infos=[
                "If that account exists you will receive an email, please check your inbox"
            ],
        )
    return render_template("reset_password.html")


@auth.route("/register", methods=["POST", "GET"])
@check_registration_visibility
@ratelimit(method="POST", limit=10, interval=5)
def register():
    errors = get_errors()
    if current_user.authed():
        return redirect(url_for("challenges.listing"))

    num_users_limit = int(get_config("num_users", default=0))
    num_users = Users.query.filter_by(banned=False, hidden=False).count()
    if num_users_limit and num_users >= num_users_limit:
        abort(
            403,
            description=f"Reached the maximum number of users ({num_users_limit}).",
        )

    if request.method == "POST":
        from CTFd.forms.auth import RegistrationForm as RegistrationFormClass
        form = RegistrationFormClass(request.form)
        name = request.form.get("name", "").strip()
        
        # Add roll number validation
        # Skip validation for admin users
        if current_user.authed():
            is_admin = current_user.type == "admin"
        else:
            is_admin = False
            
        if not is_admin and name:
            # Get validation settings from environment variables
            min_roll_length = int(os.getenv("MIN_ROLL_LENGTH", "6"))
            allowed_batch_code = os.getenv("ALLOWED_BATCH_CODE")  # No default value
            error_message = os.getenv("REGISTRATION_ERROR_MESSAGE", 
                                     "Only First year students are allowed to participate in this CTF")
            
            # Only validate if the name is not empty and user is not an admin
            if len(name) < min_roll_length:
                errors.append(error_message)
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name,
                )
            # Only validate batch code if an allowed batch code is specified
            elif allowed_batch_code and name[4:6] != allowed_batch_code:
                errors.append(error_message)
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name,
                )
        
        # Rest of the function continues as before
        if form.generate_otp.data:
            if not name:
                errors.append("Please enter your Roll No.")
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name,
                )
            names = (
                Users.query.add_columns(Users.name, Users.id).filter_by(name=name).first()
            )
            if names:
                errors.append("This Roll No. is already registered")
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name,
                )
            print (name + "Bye")
            try:
                # Ensure credentials are properly formatted
                client_id = os.getenv('GRPC_CLIENT_ID')
                client_secret = os.getenv('GRPC_CLIENT_SECRET')
                
                # Generate OTP for registration
                auth_client = get_active_auth_client()
                success, message = auth_client.generate_otp(
                    client_id=client_id,
                    client_secret=client_secret,
                    roll_no=int(name)
                )
                
                if not success:
                    log(
                        "registrations",
                        format="[{date}] {ip} - OTP generation failed for {name}: {message}",
                        name=name,
                        message=message
                    )
                    errors.append(f"Failed to generate OTP: {message}")
                    return render_template(
                        "register.html",
                        errors=errors,
                        name=name
                    )
                # Store information in session
                session['otp_requested'] = True
                session['roll_no'] = name
                log(
                    "registrations",
                    format="[{date}] {ip} - OTP generated for {name}",
                    name=name
                )
                # Return to the same page with OTP field now visible
                return render_template(
                    "register.html",
                    name=name,
                    otp_requested=True
                )
            except ValueError as e:
                log(
                    "registrations",
                    format="[{date}] {ip} - Invalid roll number format for {name}",
                    name=name
                )
                errors.append("Invalid roll number format")
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name
                )
        # If the Submit button was pressed (OTP verification)
        elif form.submit.data:
            otp = request.form.get("otp")
            if not otp:
                errors.append("Please enter the OTP sent to your mobile")
                return render_template(
                    "register.html", 
                    errors=errors,
                    name=name,
                    otp_requested=True
                )
            print (name + "Hello")
            # Basic validation checks
            name_len = len(name) == 0
            team_name_email_check = validators.validate_email(name)
            
            website = request.form.get("website")
            affiliation = request.form.get("affiliation")
            country = request.form.get("country")
            registration_code = str(request.form.get("registration_code", ""))
            bracket_id = request.form.get("bracket_id", None)
            
            # Run validation checks
            if country:
                try:
                    validators.validate_country_code(country)
                    valid_country = True
                except ValidationError:
                    valid_country = False
            else:
                valid_country = True
            
            if website:
                valid_website = validators.validate_url(website)
            else:
                valid_website = True

            if affiliation:
                valid_affiliation = len(affiliation) < 128
            else:
                valid_affiliation = True

            if bracket_id:
                valid_bracket = bool(
                    Brackets.query.filter_by(id=bracket_id, type="users").first()
                )
            else:
                if Brackets.query.filter_by(type="users").count():
                    valid_bracket = False
                else:
                    valid_bracket = True

            # Check registration code if required
            if get_config("registration_code"):
                if (
                    registration_code.lower()
                    != str(get_config("registration_code", default="")).lower()
                ):
                    errors.append("The registration code you entered was incorrect")
            # Process additional user fields
            fields = {}
            for field in UserFields.query.all():
                fields[field.id] = field

            entries = {}
            for field_id, field in fields.items():
                value = request.form.get(f"fields[{field_id}]", "").strip()
                if field.required is True and (value is None or value == ""):
                    errors.append("Please provide all required fields")
                    break

                if field.field_type == "boolean":
                    entries[field_id] = bool(value)
                else:
                    entries[field_id] = value
            
            # Check for validation errors
            if team_name_email_check is True:
                errors.append("Your Roll No. cannot be an email address")
            if name_len:
                errors.append("Roll No. cannot be empty")
            if valid_website is False:
                errors.append("Websites must be a proper URL starting with http or https")
            if valid_country is False:
                errors.append("Invalid country")
            if valid_affiliation is False:
                errors.append("Please provide a shorter affiliation")
            if valid_bracket is False:
                errors.append("Please provide a valid bracket")
            
            # If there are validation errors, redisplay the form
            if len(errors) > 0:
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name,
                    otp_requested=True
                )
            
            # Verify OTP
            try:
                client_id = os.getenv('GRPC_CLIENT_ID')
                client_secret = os.getenv('GRPC_CLIENT_SECRET')
                auth_client = get_active_auth_client()
                success, message, student_name = auth_client.verify_otp(
                    client_id=client_id,
                    client_secret=client_secret,
                    roll_no=int(name),
                    otp=int(otp)
                )
                
                if not success:
                    log(
                        "registrations",
                        format="[{date}] {ip} - OTP verification failed for {name}: {message}",
                        name=name,
                        message=message
                    )
                    errors.append(f"OTP verification failed: {message}")
                    return render_template(
                        "register.html",
                        errors=errors,
                        name=name,
                        otp_requested=True
                    )
                    
                # OTP verified successfully, create the user
                user = Users(
                    name=name,
                    email=name + "@nitt.edu",
                    password=name + "@123",
                    # fullname=student_name,  # Assign the student_name to the fullname field
                    bracket_id=bracket_id,
                )
                if website:
                    user.website = website
                if affiliation:
                    user.affiliation = affiliation
                if country:
                    user.country = country

                db.session.add(user)
                db.session.commit()
                db.session.flush()

                # Add user field entries
                for field_id, value in entries.items():
                    entry = UserFieldEntries(
                        field_id=field_id, value=value, user_id=user.id
                    )
                    db.session.add(entry)
                db.session.commit()
                
                # Clear session data
                session.pop('otp_requested', None)
                session.pop('roll_no', None)
                
                login_user(user)

                log(
                    "registrations",
                    format="[{date}] {ip} - {name} registered successfully after OTP verification",
                    name=name
                )
                
                if request.args.get("next") and validators.is_safe_url(
                    request.args.get("next")
                ):
                    return redirect(request.args.get("next"))
                
                if is_teams_mode():
                    return redirect(url_for("teams.private"))
                
                return redirect(url_for("challenges.listing"))
            
            except ValueError as e:
                log(
                    "registrations",
                    format="[{date}] {ip} - Error during OTP verification for {name}: {error}",
                    name=name,
                    error=str(e)
                )
                errors.append("Invalid OTP format")
                return render_template(
                    "register.html",
                    errors=errors,
                    name=name,
                    otp_requested=True
                )
                
        else:
            # This block handles any other condition (not generate_otp, not submit)
            print (name + " Hi")
            return render_template("register.html", errors=errors, name=name)
            
    else:
        # This is for GET requests
        # print (name + " end")
        return render_template("register.html", 
                          errors=errors, 
                          otp_requested=session.get('otp_requested', False),
                          name=session.get('roll_no', ''))
    

@auth.route("/login", methods=["POST", "GET"])
@ratelimit(method="POST", limit=10, interval=5)
def login():
    errors = get_errors()
    if request.method == "POST":
        from CTFd.forms.auth import LoginForm
        form = LoginForm(request.form)
        name = request.form.get("name", "").strip()
        action = request.form.get("action")

        # Check which action was requested
        if form.generate_otp.data:
            if not name:
                errors.append("Please enter your Roll No.")
                return render_template(
                    "login.html",
                    errors=errors,
                    name=name,
                )

            # Check if user exists
            user = Users.query.filter_by(name=name).first()
            if not user:
                errors.append("This Roll No. is not registered")
                return render_template(
                    "login.html",
                    errors=errors,
                    name=name,
                )

            try:
                # Ensure credentials are properly formatted
                client_id = os.getenv('GRPC_CLIENT_ID')
                client_secret = os.getenv('GRPC_CLIENT_SECRET')
                
                # Generate OTP for login
                auth_client = get_active_auth_client()
                success, message = auth_client.generate_otp(
                    client_id=client_id,
                    client_secret=client_secret,
                    roll_no=int(name)
                )
                
                if not success:
                    log(
                        "logins",
                        format="[{date}] {ip} - OTP generation failed for {name}: {message}",
                        name=name,
                        message=message
                    )
                    errors.append(f"Failed to generate OTP: {message}")
                    return render_template(
                        "login.html",
                        errors=errors,
                        name=name
                    )

                # Store information in session
                session['otp_requested'] = True
                session['roll_no'] = name
                
                log(
                    "logins",
                    format="[{date}] {ip} - OTP generated for {name}",
                    name=name
                )
                
                # Return to the same page with OTP field now visible
                return render_template(
                    "login.html",
                    name=name,
                    otp_requested=True
                )
            except ValueError as e:
                log(
                    "logins",
                    format="[{date}] {ip} - Invalid roll number format for {name}",
                    name=name
                )
                errors.append("Invalid roll number format")
                return render_template(
                    "login.html",
                    errors=errors,
                    name=name
                )

        # If the Submit button was pressed (OTP verification)
        elif form.submit.data:
            otp = request.form.get("otp")
            if not otp:
                errors.append("Please enter the OTP sent to your mobile")
                return render_template(
                    "login.html", 
                    errors=errors,
                    name=name,
                    otp_requested=True
                )

            try:
                client_id = os.getenv('GRPC_CLIENT_ID')
                client_secret = os.getenv('GRPC_CLIENT_SECRET')
                auth_client = get_active_auth_client()
                success, message, details = auth_client.verify_otp(
                    client_id=client_id,
                    client_secret=client_secret,
                    roll_no=int(name),
                    otp=int(otp)
                )
                
                if not success:
                    log(
                        "logins",
                        format="[{date}] {ip} - OTP verification failed for {name}: {message}",
                        name=name,
                        message=message
                    )
                    errors.append(f"OTP verification failed: {message}")
                    return render_template(
                        "login.html",
                        errors=errors,
                        name=name,
                        otp_requested=True
                    )

                # OTP verified successfully, log the user in
                user = Users.query.filter_by(name=name).first()
                session.regenerate()
                login_user(user)
                
                # Clear session data
                session.pop('otp_requested', None)
                session.pop('roll_no', None)
                
                log(
                    "logins",
                    format="[{date}] {ip} - {name} logged in successfully after OTP verification",
                    name=name
                )
                
                db.session.close()
                if request.args.get("next") and validators.is_safe_url(
                    request.args.get("next")
                ):
                    return redirect(request.args.get("next"))
                return redirect(url_for("challenges.listing"))
            
            except ValueError as e:
                log(
                    "logins",
                    format="[{date}] {ip} - Error during OTP verification for {name}: {error}",
                    name=name,
                    error=str(e)
                )
                errors.append("Invalid OTP format")
                return render_template(
                    "login.html",
                    errors=errors,
                    name=name,
                    otp_requested=True
                )
        else:
            return render_template("login.html", errors=errors, name=name)
    else:
        db.session.close()
        return render_template(
            "login.html", 
            errors=errors,
            otp_requested=session.get('otp_requested', False),
            name=session.get('roll_no', '')
        )


@auth.route("/oauth")
def oauth_login():
    endpoint = (
        get_app_config("OAUTH_AUTHORIZATION_ENDPOINT")
        or get_config("oauth_authorization_endpoint")
        or "https://auth.majorleaguecyber.org/oauth/authorize"
    )

    if get_config("user_mode") == "teams":
        scope = "profile team"
    else:
        scope = "profile"

    client_id = get_app_config("OAUTH_CLIENT_ID") or get_config("oauth_client_id")

    if client_id is None:
        error_for(
            endpoint="auth.login",
            message="OAuth Settings not configured. "
            "Ask your CTF administrator to configure MajorLeagueCyber integration.",
        )
        return redirect(url_for("auth.login"))

    redirect_url = "{endpoint}?response_type=code&client_id={client_id}&scope={scope}&state={state}".format(
        endpoint=endpoint, client_id=client_id, scope=scope, state=session["nonce"]
    )
    return redirect(redirect_url)


@auth.route("/redirect", methods=["GET"])
@ratelimit(method="GET", limit=10, interval=60)
def oauth_redirect():
    oauth_code = request.args.get("code")
    state = request.args.get("state")
    if session["nonce"] != state:
        log("logins", "[{date}] {ip} - OAuth State validation mismatch")
        error_for(endpoint="auth.login", message="OAuth State validation mismatch.")
        return redirect(url_for("auth.login"))

    if oauth_code:
        url = (
            get_app_config("OAUTH_TOKEN_ENDPOINT")
            or get_config("oauth_token_endpoint")
            or "https://auth.majorleaguecyber.org/oauth/token"
        )

        client_id = get_app_config("OAUTH_CLIENT_ID") or get_config("oauth_client_id")
        client_secret = get_app_config("OAUTH_CLIENT_SECRET") or get_config(
            "oauth_client_secret"
        )
        headers = {"content-type": "application/x-www-form-urlencoded"}
        data = {
            "code": oauth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
        }
        token_request = requests.post(url, data=data, headers=headers)

        if token_request.status_code == requests.codes.ok:
            token = token_request.json()["access_token"]
            user_url = (
                get_app_config("OAUTH_API_ENDPOINT")
                or get_config("oauth_api_endpoint")
                or "https://api.majorleaguecyber.org/user"
            )

            headers = {
                "Authorization": "Bearer " + str(token),
                "Content-type": "application/json",
            }
            api_data = requests.get(url=user_url, headers=headers).json()

            user_id = api_data["id"]
            user_name = api_data["name"]
            user_email = api_data["email"]

            user = Users.query.filter_by(email=user_email).first()
            if user is None:
                # Respect the user count limit
                num_users_limit = int(get_config("num_users", default=0))
                num_users = Users.query.filter_by(banned=False, hidden=False).count()
                if num_users_limit and num_users >= num_users_limit:
                    abort(
                        403,
                        description=f"Reached the maximum number of users ({num_users_limit}).",
                    )

                # Check if we are allowing registration before creating users
                if registration_visible() or mlc_registration():
                    user = Users(
                        name=user_name,
                        email=user_email,
                        oauth_id=user_id,
                        verified=True,
                    )
                    db.session.add(user)
                    db.session.commit()
                else:
                    log("logins", "[{date}] {ip} - Public registration via MLC blocked")
                    error_for(
                        endpoint="auth.login",
                        message="Public registration is disabled. Please try again later.",
                    )
                    return redirect(url_for("auth.login"))

            if get_config("user_mode") == TEAMS_MODE and user.team_id is None:
                team_id = api_data["team"]["id"]
                team_name = api_data["team"]["name"]

                team = Teams.query.filter_by(oauth_id=team_id).first()
                if team is None:
                    num_teams_limit = int(get_config("num_teams", default=0))
                    num_teams = Teams.query.filter_by(
                        banned=False, hidden=False
                    ).count()
                    if num_teams_limit and num_teams >= num_teams_limit:
                        abort(
                            403,
                            description=f"Reached the maximum number of teams ({num_teams_limit}). Please join an existing team.",
                        )

                    team = Teams(name=team_name, oauth_id=team_id, captain_id=user.id)
                    db.session.add(team)
                    db.session.commit()
                    clear_team_session(team_id=team.id)

                team_size_limit = get_config("team_size", default=0)
                if team_size_limit and len(team.members) >= team_size_limit:
                    plural = "" if team_size_limit == 1 else "s"
                    size_error = "Teams are limited to {limit} member{plural}.".format(
                        limit=team_size_limit, plural=plural
                    )
                    error_for(endpoint="auth.login", message=size_error)
                    return redirect(url_for("auth.login"))

                team.members.append(user)
                db.session.commit()

            if user.oauth_id is None:
                user.oauth_id = user_id
                user.verified = True
                db.session.commit()
                clear_user_session(user_id=user.id)

            login_user(user)

            return redirect(url_for("challenges.listing"))
        else:
            log("logins", "[{date}] {ip} - OAuth token retrieval failure")
            error_for(endpoint="auth.login", message="OAuth token retrieval failure.")
            return redirect(url_for("auth.login"))
    else:
        log("logins", "[{date}] {ip} - Received redirect without OAuth code")
        error_for(
            endpoint="auth.login", message="Received redirect without OAuth code."
        )
        return redirect(url_for("auth.login"))


@auth.route("/logout")
def logout():
    if current_user.authed():
        logout_user()
    return redirect(url_for("views.static_html"))