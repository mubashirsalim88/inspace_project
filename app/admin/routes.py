from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import User, Application, ApplicationAssignment, ChatMessage, Notification, AuditLog, EditRequest
from app.utils import role_required
from datetime import datetime
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

admin = Blueprint("admin", __name__, template_folder="templates")

@admin.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    logger.info(f"Admin dashboard accessed by user {current_user.id}")
    try:
        total_users = User.query.filter(User.role != "admin").count()
        total_applications = Application.query.count()
        total_assignments = ApplicationAssignment.query.count()
        total_notifications = Notification.query.count()
        total_messages = ChatMessage.query.count()
        total_edit_requests = EditRequest.query.count()
        recent_audit_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
        recent_applications = Application.query.order_by(Application.updated_at.desc()).limit(5).all()
        active_edit_requests = EditRequest.query.filter_by(status="Active").order_by(EditRequest.requested_at.desc()).limit(5).all()
        return render_template(
            "admin/dashboard.html",
            total_users=total_users,
            total_applications=total_applications,
            total_assignments=total_assignments,
            total_notifications=total_notifications,
            total_messages=total_messages,
            total_edit_requests=total_edit_requests,
            recent_audit_logs=recent_audit_logs,
            recent_applications=recent_applications,
            active_edit_requests=active_edit_requests,
            current_time=datetime.utcnow()
        )
    except Exception as e:
        logger.error(f"Error in admin dashboard for user {current_user.id}: {str(e)}")
        flash("Error loading dashboard.", "error")
        return render_template("admin/dashboard.html", error="Unable to load dashboard.")

@admin.route("/users", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_users():
    if request.method == "POST":
        action = request.form.get("action")
        user_id = request.form.get("user_id")
        if not user_id:
            flash("User ID is required.", "error")
            return redirect(url_for("admin.manage_users"))

        user = User.query.get_or_404(user_id)
        if action == "update_role":
            new_role = request.form.get("role")
            valid_roles = ["user", "Assigner", "Primary Verifier", "Secondary Verifier", "Director", "admin"]
            if new_role not in valid_roles:
                flash("Invalid role selected.", "error")
                return redirect(url_for("admin.manage_users"))
            user.role = new_role
            db.session.commit()
            flash(f"Role updated for {user.username} to {new_role}.", "success")
        elif action == "delete":
            if user.role == "admin" and User.query.filter_by(role="admin").count() == 1:
                flash("Cannot delete the last admin user.", "error")
                return redirect(url_for("admin.manage_users"))
            db.session.delete(user)
            db.session.commit()
            flash(f"User {user.username} deleted.", "success")
        return redirect(url_for("admin.manage_users"))

    users = User.query.all()
    users_by_role = {
        role: User.query.filter_by(role=role).count()
        for role in ["user", "Assigner", "Primary Verifier", "Secondary Verifier", "Director", "admin"]
    }
    recent_users = User.query.order_by(User.id.desc()).limit(10).all()
    return render_template(
        "admin/users.html",
        users=users,
        users_by_role=users_by_role,
        recent_users=recent_users,
        valid_roles=["user", "Assigner", "Primary Verifier", "Secondary Verifier", "Director", "admin"]
    )

@admin.route("/applications", methods=["GET", "POST"])
@login_required
@role_required("admin")
def applications():
    if request.method == "POST":
        application_id = request.form.get("application_id")
        action = request.form.get("action")
        application = Application.query.get_or_404(application_id)
        if action == "update_status":
            new_status = request.form.get("status")
            valid_statuses = ["Pending", "Submitted", "Under Review", "Approved", "Rejected"]
            if new_status not in valid_statuses:
                flash("Invalid status selected.", "error")
                return redirect(url_for("admin.applications"))
            application.status = new_status
            application.editable = new_status == "Pending"
            db.session.commit()
            flash(f"Application {application_id} status updated to {new_status}.", "success")
        return redirect(url_for("admin.applications"))

    applications = Application.query.order_by(Application.updated_at.desc()).all()
    applications_by_status = {
        status: Application.query.filter_by(status=status).count()
        for status in ["Pending", "Submitted", "Under Review", "Approved", "Rejected"]
    }
    return render_template(
        "admin/applications.html",
        applications=applications,
        applications_by_status=applications_by_status
    )

@admin.route("/assign_application/<int:application_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def assign_application(application_id):
    application = Application.query.get_or_404(application_id)
    if request.method == "POST":
        primary_verifier_id = request.form.get("primary_verifier_id")
        secondary_verifier_id = request.form.get("secondary_verifier_id")
        if not primary_verifier_id:
            flash("Primary Verifier is required.", "error")
            return redirect(url_for("admin.assign_application", application_id=application_id))

        primary_verifier = User.query.get_or_404(primary_verifier_id)
        secondary_verifier = User.query.get(secondary_verifier_id) if secondary_verifier_id else None
        if primary_verifier.role not in ["Primary Verifier", "admin"]:
            flash("Primary Verifier must have appropriate role.", "error")
            return redirect(url_for("admin.assign_application", application_id=application_id))
        if secondary_verifier and secondary_verifier.role not in ["Secondary Verifier", "admin"]:
            flash("Secondary Verifier must have appropriate role.", "error")
            return redirect(url_for("admin.assign_application", application_id=application_id))

        assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first()
        if not assignment:
            assignment = ApplicationAssignment(
                application_id=application_id,
                assigner_id=current_user.id,
                primary_verifier_id=primary_verifier_id,
                secondary_verifier_id=secondary_verifier_id
            )
            db.session.add(assignment)
        else:
            assignment.primary_verifier_id = primary_verifier_id
            assignment.secondary_verifier_id = secondary_verifier_id
            assignment.assigner_id = current_user.id

        application.status = "Under Review"
        db.session.commit()
        flash(f"Application {application_id} assigned successfully.", "success")
        return redirect(url_for("admin.applications"))

    primary_verifiers = User.query.filter(User.role.in_(["Primary Verifier", "admin"])).all()
    secondary_verifiers = User.query.filter(User.role.in_(["Secondary Verifier", "admin"])).all()
    return render_template(
        "admin/assign_application.html",
        application=application,
        primary_verifiers=primary_verifiers,
        secondary_verifiers=secondary_verifiers
    )

@admin.route("/notifications")
@login_required
@role_required("admin")
def notifications():
    notifications = Notification.query.order_by(Notification.timestamp.desc()).all()
    return render_template("admin/notifications.html", notifications=notifications)

@admin.route("/chat")
@login_required
@role_required("admin")
def chat():
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).all()
    return render_template("admin/chat.html", messages=messages)

@admin.route("/audit_logs/<int:application_id>")
@login_required
@role_required("admin")
def audit_logs(application_id):
    application = Application.query.get_or_404(application_id)
    audit_logs = AuditLog.query.filter_by(application_id=application_id).order_by(AuditLog.timestamp.desc()).all()
    return render_template(
        "admin/audit_logs.html",
        audit_logs=audit_logs,
        application=application
    )

@admin.route("/edit_requests", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_requests():
    if request.method == "POST":
        edit_request_id = request.form.get("edit_request_id")
        action = request.form.get("action")
        edit_request = EditRequest.query.get_or_404(edit_request_id)
        application = Application.query.get_or_404(edit_request.application_id)
        if action == "approve":
            edit_request.status = "Approved"
            application.editable = True
            application.status = "Pending"
            db.session.commit()
            flash(f"Edit request {edit_request_id} approved.", "success")
        elif action == "reject":
            edit_request.status = "Rejected"
            db.session.commit()
            flash(f"Edit request {edit_request_id} rejected.", "success")
        return redirect(url_for("admin.edit_requests"))

    edit_requests = EditRequest.query.order_by(EditRequest.requested_at.desc()).all()
    return render_template("admin/edit_requests.html", edit_requests=edit_requests)