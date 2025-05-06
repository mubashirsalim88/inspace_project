# app/director/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from app import db, mail
from app.models import Application, ApplicationAssignment, User, Notification
from app.utils import role_required
from flask_mail import Message
import logging
from datetime import datetime, timedelta

director = Blueprint("director", __name__, url_prefix="/director", template_folder="templates")

logger = logging.getLogger(__name__)

# Setup CSRF protection
csrf = CSRFProtect()

@director.route("/home")
@login_required
@role_required("Director")
def home():
    # Fetch applications
    actionable_applications = Application.query.filter_by(status="Pending Director Approval").all()
    completed_applications = Application.query.filter(Application.status.in_(["Approved", "Rejected"])).all()
    
    # Group applications by module (all ten modules)
    module_apps = {f"module_{i}": [] for i in range(1, 11)}
    completed_module_apps = {f"module_{i}": [] for i in range(1, 11)}
    
    for app in actionable_applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in module_apps), None)
        if module_name:
            module_apps[module_name].append(app)
    
    for app in completed_applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in completed_module_apps), None)
        if module_name:
            completed_module_apps[module_name].append(app)

    # Define fixed module order
    fixed_modules = [f"module_{i}" for i in range(1, 11)]

    # Identify modules with actionable applications updated in the last 7 days
    recent_actionable_modules = set()
    for module in module_apps:
        for app in module_apps[module]:
            if (datetime.now() - app.updated_at).days <= 7:
                recent_actionable_modules.add(module)

    return render_template(
        "director/home.html",
        module_apps=module_apps,
        completed_module_apps=completed_module_apps,
        fixed_modules=fixed_modules,
        recent_actionable_modules=recent_actionable_modules,
        role=current_user.role,
        datetime=datetime,
        csrf_token=generate_csrf
    )

@director.route("/review/<int:application_id>", methods=["GET", "POST"])
@login_required
@role_required("Director")
def review(application_id):
    logger.debug(f"Accessing review for application {application_id} by Director {current_user.id}")
    application = Application.query.get_or_404(application_id)
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    
    logger.debug(f"Application {application_id} status: {application.status}, user_id: {application.user_id}, updated_at: {application.updated_at}")
    if application.status != "Pending Director Approval":
        logger.warning(f"Application {application_id} not reviewable by Director, status: {application.status}")
        flash(f"This application is not in a reviewable state. Current status: {application.status}", "error")
        return redirect(url_for("director.home"))

    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id) if assignment.secondary_verifier_id else None

    module_name = next(
        (md.module_name for md in application.module_data if md.module_name in [f"module_{i}" for i in range(1, 11)]),
        None
    )
    if not module_name:
        logger.error(f"No valid module found for application {application_id}")
        flash("No valid module found for this application.", "error")
        return redirect(url_for("director.home"))
    
    # Ensure correct endpoint for PDF download
    pdf_download_url = url_for(f"{module_name}_pdf.download_pdf", application_id=application_id, _external=True)

    if request.method == "POST":
        logger.debug(f"Processing POST request for application {application_id}, content-type: {request.content_type}")
        form_data = request.form
        if not form_data and request.is_json:
            form_data = request.json or {}
            logger.debug(f"JSON payload: {form_data}")
        else:
            logger.debug(f"Form data: {dict(form_data)}")

        action = form_data.get("action")
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
                return redirect(url_for("director.review", application_id=application_id))

            if decision == "reject" and not comments:
                logger.warning(f"Reject action for application {application_id} failed: comments required")
                flash("Comments are required when rejecting an application.", "error")
                return redirect(url_for("director.review", application_id=application_id))

            application.comments = comments

            if decision == "approve":
                application.status = "Approved"
                flash("Application approved.", "success")
                notification = Notification(
                    user_id=application.user_id,
                    content=f"Your application #{application.id} has been approved by the Director. Comments: {comments or 'None'}",
                    timestamp=datetime.utcnow()
                )
                db.session.add(notification)
                # Notify verifiers
                for verifier_id in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
                    if verifier_id:
                        notification = Notification(
                            user_id=verifier_id,
                            content=f"Application #{application.id} has been approved by the Director.",
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(notification)
                logger.info(f"Application {application_id} approved by Director, notifications sent")
            else:  # Reject
                application.status = "Rejected"
                flash(f"Application rejected. Comments: {comments}", "success")
                notification = Notification(
                    user_id=application.user_id,
                    content=f"Your application #{application.id} has been rejected by the Director. Comments: {comments}",
                    timestamp=datetime.utcnow()
                )
                db.session.add(notification)
                # Notify verifiers
                for verifier_id in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
                    if verifier_id:
                        notification = Notification(
                            user_id=verifier_id,
                            content=f"Application #{application.id} has been rejected by the Director. Comments: {comments}",
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(notification)
                logger.info(f"Application {application_id} rejected by Director, notifications sent")

            try:
                db.session.commit()
                logger.info(f"Database committed for review action on application {application_id}")
            except Exception as e:
                logger.error(f"Database commit failed for review action on application {application_id}: {str(e)}", exc_info=True)
                db.session.rollback()
                flash("An error occurred while processing the review. Please try again.", "error")
                return redirect(url_for("director.review", application_id=application_id))

            # Send email to applicant (handle separately to avoid rollback)
            try:
                msg = Message(
                    f"Application {application_id} {'Approved' if decision == 'approve' else 'Rejected'} - IN-SPACe Portal",
                    sender="noreply@inspace.gov.in",
                    recipients=[application.user.email]
                )
                msg.body = (
                    f"Dear {application.user.name},\n\n"
                    f"Your application (ID: {application_id}, Module: {module_name.replace('_', ' ').title()}) has been "
                    f"{'approved' if decision == 'approve' else 'rejected'} by the Director.\n"
                    f"Comments: {comments or 'None'}\n\n"
                    f"View Application: {url_for('applicant.home', module=module_name, _external=True)}\n"
                    f"Login: {url_for('auth.login', _external=True)}\n\n"
                    f"Regards,\nIN-SPACe Team"
                )
                mail.send(msg)
                logger.info(f"Email sent to {application.user.email} for application {application_id}")
            except Exception as e:
                logger.error(f"Email sending failed for application {application_id}: {str(e)}", exc_info=True)
                flash("Application processed, but failed to send notification email.", "warning")

            return redirect(url_for("director.home"))

    logger.debug(f"Rendering review.html for Director")
    return render_template(
        "director/review.html",
        application=application,
        assignment=assignment,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier,
        pdf_download_url=pdf_download_url,
        module_name=module_name,
        role=current_user.role,
        csrf_token=generate_csrf
    )