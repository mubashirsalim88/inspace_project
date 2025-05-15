from functools import wraps
from flask_login import current_user
from flask import redirect, url_for, flash
from app import db
from app.models import AuditLog, ModuleData, UploadedFile
from datetime import datetime

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

def log_change(application_id, module_name, step, change_type, change_details):
    """Log a change to the audit_logs table."""
    audit_log = AuditLog(
        application_id=application_id,
        user_id=current_user.id,
        module_name=module_name,
        step=step,
        change_type=change_type,
        change_details=change_details,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit_log)
    # Commit is handled by the caller to ensure atomicity

def compare_form_data(old_data, new_data, application_id, module_name, step):
    """Compare old and new form data and log field changes."""
    for field, new_value in new_data.items():
        old_value = old_data.get(field)
        # Convert lists to strings for comparison (e.g., file paths)
        if isinstance(old_value, list) and isinstance(new_value, list):
            old_value = sorted(old_value) if old_value else []
            new_value = sorted(new_value) if new_value else []
        if old_value != new_value:
            change_details = {
                "field": field,
                "old_value": old_value,
                "new_value": new_value
            }
            log_change(application_id, module_name, step, "field_update", change_details)

def log_file_upload(application_id, module_name, step, field_name, filename):
    """Log a file upload."""
    change_details = {
        "field": field_name,
        "filename": filename,
        "action": "upload"
    }
    log_change(application_id, module_name, step, "file_upload", change_details)