# app/utils.py
from functools import wraps
from flask_login import current_user
from flask import redirect, url_for, flash

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in to access this page.", "error")
                return redirect(url_for("auth.login"))
            if isinstance(roles[0], list):
                allowed_roles = roles[0]
            else:
                allowed_roles = roles
            if current_user.role not in allowed_roles:
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator