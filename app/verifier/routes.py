# app/verifier/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from app import db, mail
from app.models import Application, ApplicationAssignment, User, Notification, ModuleData, EditRequest
from app.utils import role_required
from flask_mail import Message
import logging
from datetime import datetime, timedelta

verifier = Blueprint("verifier", __name__, url_prefix="/verifier", template_folder="templates")

logger = logging.getLogger(__name__)

# Setup CSRF protection
csrf = CSRFProtect()

@verifier.route("/home")
@login_required
@role_required(["Primary Verifier", "Secondary Verifier"])
def home():
    assignments_as_primary = ApplicationAssignment.query.filter_by(primary_verifier_id=current_user.id).all()
    assignments_as_secondary = ApplicationAssignment.query.filter_by(secondary_verifier_id=current_user.id).all()
    
    applications = []
    app_ids = set()
    for assignment in assignments_as_primary + assignments_as_secondary:
        app = Application.query.get(assignment.application_id)
        if app and app.id not in app_ids:
            applications.append(app)
            app_ids.add(app.id)
    
    # Group applications by module (all ten modules)
    module_apps = {f"module_{i}": [] for i in range(1, 11)}
    for app in applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in module_apps), None)
        if module_name:
            module_apps[module_name].append(app)

    # Define fixed module order
    fixed_modules = [f"module_{i}" for i in range(1, 11)]

    # Identify modules with actionable applications updated in the last 7 days
    actionable_statuses = ["Under Review"] if current_user.role == "Primary Verifier" else ["Pending Secondary Approval"]
    recent_actionable_modules = set()
    for module in module_apps:
        for app in module_apps[module]:
            if app.status in actionable_statuses and (datetime.now() - app.updated_at).days <= 7:
                recent_actionable_modules.add(module)

    return render_template(
        "verifier/home.html",
        module_apps=module_apps,
        fixed_modules=fixed_modules,
        recent_actionable_modules=recent_actionable_modules,
        role=current_user.role,
        datetime=datetime,
        csrf_token=generate_csrf()
    )

@verifier.route("/review/<int:application_id>", methods=["GET", "POST"])
@login_required
@role_required(["Primary Verifier", "Secondary Verifier"])
def review(application_id):
    logger.debug(f"Accessing review for application {application_id} by user {current_user.id}")
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    application = Application.query.get_or_404(application_id)
    
    if current_user.id not in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
        logger.warning(f"Unauthorized access attempt for application {application_id} by user {current_user.id}")
        flash("You are not authorized to review this application.", "error")
        return redirect(url_for("verifier.home"))

    # Allow review only if status is actionable for the current verifier
    actionable_statuses = ["Under Review"] if current_user.role == "Primary Verifier" else ["Pending Secondary Approval"]
    if application.status not in actionable_statuses:
        logger.warning(f"Application {application_id} not reviewable, status: {application.status}")
        flash("This application is not in a reviewable state.", "error")
        return redirect(url_for("verifier.home"))

    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id) if assignment.secondary_verifier_id else None

    module_name = next(
        (md.module_name for md in application.module_data if md.module_name in [f"module_{i}" for i in range(1, 11)]),
        None
    )
    if not module_name:
        logger.error(f"No valid module found for application {application_id}")
        flash("No valid module found for this application.", "error")
        return redirect(url_for("verifier.home"))
    
    pdf_download_url = url_for(f"{module_name}_pdf.download_pdf", application_id=application_id)

    if request.method == "POST":
        logger.debug(f"Processing POST request for application {application_id}, content-type: {request.content_type}")
        # Try form data first, fallback to JSON
        form_data = request.form
        if not form_data and request.is_json:
            form_data = request.json or {}
            logger.debug(f"JSON payload: {form_data}")
        else:
            logger.debug(f"Form data: {dict(form_data)}")

        action = form_data.get("action")
        other_verifier_id = assignment.secondary_verifier_id if current_user.role == "Primary Verifier" else assignment.primary_verifier_id

        if not action:
            logger.warning(f"Invalid POST request for application {application_id}: Missing action parameter")
            return jsonify({"status": "error", "message": "Missing action parameter."}), 400

        if action == "review":
            decision = form_data.get("decision")
            comments = form_data.get("comments")
            logger.debug(f"Review action: decision={decision}, comments={comments}")
            
            if decision not in ["approve", "reject"]:
                logger.warning(f"Invalid decision for application {application_id}: {decision}")
                flash("Invalid decision.", "error")
                return redirect(url_for("verifier.review", application_id=application_id))

            if decision == "reject" and not comments:
                logger.warning(f"Reject action for application {application_id} failed: comments required")
                flash("Comments are required when rejecting an application.", "error")
                return redirect(url_for("verifier.review", application_id=application_id))

            application.comments = comments

            if decision == "approve":
                if not assignment.secondary_verifier_id:  # Only one verifier
                    application.status = "Approved"
                    flash("Application approved.", "success")
                    notification = Notification(
                        user_id=application.user_id,
                        content=f"Your application #{application.id} has been approved. Comments: {comments or 'None'}",
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(notification)
                    logger.info(f"Application {application_id} approved, notification created")
                else:  # Two verifiers
                    if current_user.role == "Primary Verifier" and application.status == "Under Review":
                        application.status = "Pending Secondary Approval"
                        flash("Approval submitted. Awaiting Secondary Verifier.", "success")
                        if other_verifier_id:
                            notification = Notification(
                                user_id=other_verifier_id,
                                content=f"{current_user.username} approved application #{application.id}. Your approval is needed.",
                                timestamp=datetime.utcnow()
                            )
                            db.session.add(notification)
                            logger.info(f"Application {application_id} approved by Primary Verifier, notification sent to Secondary Verifier")
                    elif current_user.role == "Secondary Verifier" and application.status == "Pending Secondary Approval":
                        application.status = "Approved"
                        flash("Application fully approved.", "success")
                        notification = Notification(
                            user_id=application.user_id,
                            content=f"Your application #{application.id} has been approved by both verifiers. Comments: {comments or 'None'}",
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(notification)
                        if other_verifier_id:
                            notification = Notification(
                                user_id=other_verifier_id,
                                content=f"Application #{application.id} has been fully approved.",
                                timestamp=datetime.utcnow()
                            )
                            db.session.add(notification)
                            logger.info(f"Application {application_id} fully approved, notifications sent")
            else:  # Reject
                application.status = "Rejected"
                flash(f"Application rejected. Comments: {comments}", "success")
                notification = Notification(
                    user_id=application.user_id,
                    content=f"Your application #{application.id} has been rejected. Comments: {comments}",
                    timestamp=datetime.utcnow()
                )
                db.session.add(notification)
                if other_verifier_id:
                    notification = Notification(
                        user_id=other_verifier_id,
                        content=f"{current_user.username} rejected application #{application.id}. Comments: {comments}",
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(notification)
                    logger.info(f"Application {application_id} rejected, notifications sent")

            try:
                db.session.commit()
                logger.info(f"Database committed for review action on application {application_id}")
            except Exception as e:
                logger.error(f"Database commit failed for review action on application {application_id}: {str(e)}", exc_info=True)
                db.session.rollback()
                flash("An error occurred while processing the review. Please try again.", "error")
                return redirect(url_for("verifier.review", application_id=application_id))

            return redirect(url_for("verifier.home"))

        elif action == "enable_edit":
            comments = form_data.get("comments")
            logger.debug(f"Attempting to enable edit for application {application_id} by user {current_user.id}, comments: {comments}")
            logger.debug(f"Application status: {application.status}, Editable: {application.editable}")

            if not comments:
                logger.warning(f"Enable edit failed for application {application_id}: Comments are required")
                return jsonify({"status": "error", "message": "Comments are required when enabling edit."}), 400

            # Check if application is already in Pending or has an active edit request
            if application.status == "Pending":
                logger.warning(f"Enable edit failed for application {application_id}: Application is already editable")
                return jsonify({"status": "error", "message": "Application is already editable."}), 400

            active_edit_request = EditRequest.query.filter_by(
                application_id=application_id, status="Active"
            ).first()
            if active_edit_request:
                logger.warning(f"Enable edit failed for application {application_id}: Active edit request exists (ID: {active_edit_request.id})")
                return jsonify({"status": "error", "message": "An active edit request already exists."}), 400

            # Verify verifier_id and user_id exist
            verifier = User.query.get(current_user.id)
            if not verifier:
                logger.error(f"Enable edit failed for application {application_id}: Verifier user {current_user.id} not found")
                return jsonify({"status": "error", "message": "Invalid verifier user."}), 400

            applicant = User.query.get(application.user_id)
            if not applicant:
                logger.error(f"Enable edit failed for application {application_id}: Applicant user {application.user_id} not found")
                return jsonify({"status": "error", "message": "Invalid applicant user."}), 400

            try:
                # Set deadline (7 days from now)
                deadline = datetime.utcnow() + timedelta(days=7)
                logger.debug(f"Setting edit deadline for application {application_id} to {deadline}")

                # Create edit request
                edit_request = EditRequest(
                    application_id=application_id,
                    verifier_id=current_user.id,
                    comments=comments,
                    requested_at=datetime.utcnow(),
                    deadline=deadline,
                    status="Active"
                )
                db.session.add(edit_request)
                logger.debug(f"Created EditRequest for application {application_id}")

                # Update application status and editable flag
                application.status = "Pending"
                application.editable = True
                logger.debug(f"Updated application {application_id} status to Pending and editable to True")

                # Create notification
                notification = Notification(
                    user_id=application.user_id,
                    content=f"Application ID {application_id} ({module_name.replace('_', ' ').title()}) is now editable. Reason: {comments}. Please complete edits by {deadline.strftime('%B %d, %Y')}.",
                    timestamp=datetime.utcnow(),
                    read=False
                )
                db.session.add(notification)
                logger.debug(f"Created notification for user {application.user_id}")

                # Prepare email
                msg = Message(
                    "Application Edit Requested - IN-SPACe Portal",
                    sender="noreply@inspace.gov.in",
                    recipients=[application.user.email]
                )
                msg.body = (
                    f"Dear {application.user.name},\n\n"
                    f"Your application (ID: {application_id}, Module: {module_name.replace('_', ' ').title()}) requires edits.\n"
                    f"Verifier Comments: {comments}\n"
                    f"Please complete the necessary changes and resubmit by {deadline.strftime('%B %d, %Y')}.\n\n"
                    f"Edit Application: {url_for('applicant.home', module=module_name, _external=True)}\n"
                    f"Login: {url_for('auth.login', _external=True)}\n\n"
                    f"Regards,\nIN-SPACe Team"
                )
                logger.debug(f"Prepared email for {application.user.email}")

                # Commit database changes before sending email
                db.session.commit()
                logger.info(f"Database committed for application {application_id}")

                # Skip email sending for testing
                logger.debug("Email sending skipped for testing")
                # mail.send(msg)
                # logger.info(f"Email sent successfully to {application.user.email} for application {application_id}")

                return jsonify({"status": "success", "message": "Edit enabled for applicant. Applicant has been notified."})
            except Exception as e:
                logger.error(f"Enable edit failed for application {application_id}: {str(e)}", exc_info=True)
                db.session.rollback()
                return jsonify({"status": "error", "message": "Failed to enable edit. Please try again."}), 500
        else:
            logger.warning(f"Invalid action for application {application_id}: {action}")
            return jsonify({"status": "error", "message": f"Invalid action: {action}"}), 400

    logger.debug(f"Rendering review.html with csrf_token callable: {callable(generate_csrf)}")
    return render_template(
        "verifier/review.html",
        application=application,
        assignment=assignment,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier,
        pdf_download_url=pdf_download_url,
        role=current_user.role,
        csrf_token=generate_csrf
    )