# app/admin/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, Application, ApplicationAssignment, ChatMessage, Notification
from functools import wraps
from datetime import datetime

admin = Blueprint("admin", __name__, template_folder="templates")

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != "admin":
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for("applicant.home"))
        return f(*args, **kwargs)
    return decorated_function

# Overview/Dashboard
@admin.route("/dashboard")
@admin_required
def dashboard():
    total_users = User.query.filter(User.role != "admin").count()
    total_applications = Application.query.count()
    total_assignments = ApplicationAssignment.query.count()
    total_messages = ChatMessage.query.count()
    total_notifications = Notification.query.count()
    
    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_applications=total_applications,
        total_assignments=total_assignments,
        total_messages=total_messages,
        total_notifications=total_notifications,
        current_time=datetime.utcnow()
    )

# Manage Users
@admin.route("/users", methods=["GET", "POST"])
@admin_required
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

# Applications
@admin.route("/applications")
@admin_required
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

# Assignments
@admin.route("/assignments")
@admin_required
def assignments():
    assignments = ApplicationAssignment.query.order_by(ApplicationAssignment.id.desc()).all()
    return render_template("admin/assignments.html", assignments=assignments)

# Chat Messages
@admin.route("/chat")
@admin_required
def chat():
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).all()
    return render_template("admin/chat.html", messages=messages)

# Notifications
@admin.route("/notifications")
@admin_required
def notifications():
    notifications = Notification.query.order_by(Notification.timestamp.desc()).all()
    return render_template("admin/notifications.html", notifications=notifications)