from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, Application, ApplicationAssignment, ChatMessage, Notification, AuditLog, EditRequest
from app.utils import role_required
from datetime import datetime

admin = Blueprint("admin", __name__, template_folder="templates")

@admin.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    total_users = User.query.filter(User.role != "admin").count()
    total_applications = Application.query.count()
    total_assignments = ApplicationAssignment.query.count()
    total_messages = ChatMessage.query.count()
    total_notifications = Notification.query.count()
    # Fetch 10 most recent audit logs
    recent_audit_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    
    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_applications=total_applications,
        total_assignments=total_assignments,
        total_messages=total_messages,
        total_notifications=total_notifications,
        current_time=datetime.utcnow(),
        recent_audit_logs=recent_audit_logs
    )

@admin.route("/users", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_users():
    if request.method == "POST":
        user_id = request.form.get("user_id")
        new_role = request.form.get("role")
        
        if not user_id or not new_role:
            flash("User ID and role are required.", "error")
            return redirect(url_for("admin.manage_users"))

        user = User.query.get_or_404(user_id)
        valid_roles = ["user", "Assigner", "Primary Verifier", "Secondary Verifier", "admin"]
        if new_role not in valid_roles:
            flash("Invalid role selected.", "error")
            return redirect(url_for("admin.manage_users"))

        user.role = new_role
        db.session.commit()
        flash(f"Role updated for {user.username} to {new_role}.", "success")
        return redirect(url_for("admin.manage_users"))

    users = User.query.all()
    users_by_role = {
        "user": User.query.filter_by(role="user").count(),
        "Assigner": User.query.filter_by(role="Assigner").count(),
        "Primary Verifier": User.query.filter_by(role="Primary Verifier").count(),
        "Secondary Verifier": User.query.filter_by(role="Secondary Verifier").count(),
        "admin": User.query.filter_by(role="admin").count(),
    }
    recent_users = User.query.order_by(User.id.desc()).limit(10).all()
    return render_template("admin/users.html", users=users, users_by_role=users_by_role, recent_users=recent_users)

@admin.route("/applications")
@login_required
@role_required("admin")
def applications():
    applications = Application.query.order_by(Application.created_at.desc()).all()
    applications_by_status = {
        "Pending": Application.query.filter_by(status="Pending").count(),
        "Submitted": Application.query.filter_by(status="Submitted").count(),
        "Under Review": Application.query.filter_by(status="Under Review").count(),
        "Approved": Application.query.filter_by(status="Approved").count(),
        "Rejected": Application.query.filter_by(status="Rejected").count(),
    }
    return render_template("admin/applications.html", applications=applications, applications_by_status=applications_by_status)

@admin.route("/assignments")
@login_required
@role_required("admin")
def assignments():
    assignments = ApplicationAssignment.query.order_by(ApplicationAssignment.id.desc()).all()
    return render_template("admin/assignments.html", assignments=assignments)

@admin.route("/chat")
@login_required
@role_required("admin")
def chat():
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).all()
    return render_template("admin/chat.html", messages=messages)

@admin.route("/notifications")
@login_required
@role_required("admin")
def notifications():
    notifications = Notification.query.order_by(Notification.timestamp.desc()).all()
    return render_template("admin/notifications.html", notifications=notifications)

@admin.route("/audit_logs/<int:application_id>")
@login_required
@role_required("admin")
def view_audit_logs(application_id):
    application = Application.query.get_or_404(application_id)
    audit_logs = AuditLog.query.filter_by(application_id=application_id).order_by(AuditLog.timestamp.desc()).all()
    edit_requests = EditRequest.query.filter_by(application_id=application_id).order_by(EditRequest.requested_at.desc()).all()
    return render_template(
        "admin/audit_logs.html",
        audit_logs=audit_logs,
        application=application,
        application_id=application_id,
        edit_requests=edit_requests
    )