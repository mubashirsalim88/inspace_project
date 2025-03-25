# app/utils.py
from functools import wraps
from flask_login import current_user
from flask import abort

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if isinstance(role, list):
                if current_user.role not in role:
                    abort(403)  # Forbidden
            elif current_user.role != role:
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator