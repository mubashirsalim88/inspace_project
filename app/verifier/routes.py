from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from app import db, mail
from app.models import Application, ApplicationAssignment, User, Notification, ModuleData, EditRequest, ChatMessage, AuditLog
from app.utils import role_required
from flask_mail import Message
import logging
from datetime import datetime, timedelta

verifier = Blueprint("verifier", __name__, url_prefix="/verifier", template_folder="templates")

logger = logging.getLogger(__name__)

csrf = CSRFProtect()

@verifier.route("/home")
@login_required
@role_required(["Primary Verifier", "Secondary Verifier"])
def home():
    logger.debug(f"Fetching home data for user {current_user.id}, role: {current_user.role}")
    
    # Fetch assignments for the current user
    assignments_as_primary = ApplicationAssignment.query.filter_by(primary_verifier_id=current_user.id).all()
    assignments_as_secondary = ApplicationAssignment.query.filter_by(secondary_verifier_id=current_user.id).all()
    logger.debug(f"Found {len(assignments_as_primary)} primary assignments, {len(assignments_as_secondary)} secondary assignments")
    
    applications = []
    completed_applications = []
    app_ids = set()
    completed_app_ids = set()
    unread_messages = {}
    app_has_secondary_verifier = {}
    
    # Combine and deduplicate applications
    for assignment in assignments_as_primary + assignments_as_secondary:
        app = Application.query.get(assignment.application_id)
        if app and app.id not in app_ids and app.id not in completed_app_ids:
            logger.debug(f"Processing application {app.id}, status: {app.status}")
            unread_count = ChatMessage.query.filter_by(
                application_id=app.id,
                receiver_id=current_user.id,
                read=False
            ).count()
            unread_messages[app.id] = unread_count
            app_has_secondary_verifier[app.id] = bool(assignment.secondary_verifier_id)
            if app.status in ["Approved", "Rejected"]:
                completed_applications.append(app)
                completed_app_ids.add(app.id)
            else:
                applications.append(app)
                app_ids.add(app.id)
    
    logger.debug(f"Total applications: {len(applications)}, completed: {len(completed_applications)}")
    
    # Initialize module dictionaries
    module_apps = {f"module_{i}": [] for i in range(1, 11)}
    completed_module_apps = {f"module_{i}": [] for i in range(1, 11)}
    
    # Categorize applications by module
    for app in applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in module_apps), None)
        if module_name:
            module_apps[module_name].append(app)
            logger.debug(f"Added application {app.id} to {module_name}")
        else:
            logger.warning(f"No valid module found for application {app.id}")
    
    for app in completed_applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in completed_module_apps), None)
        if module_name:
            completed_module_apps[module_name].append(app)
            logger.debug(f"Added completed application {app.id} to {module_name}")
        else:
            logger.warning(f"No valid module found for completed application {app.id}")
    
    # Calculate summary metrics
    total_apps = sum(len(apps) for apps in module_apps.values()) + sum(len(apps) for apps in completed_module_apps.values())
    target_status = "Under Review" if current_user.role == "Primary Verifier" else "Pending Secondary Approval"
    pending_reviews = sum(1 for apps in module_apps.values() for app in apps if app.status == target_status)
    total_unread = sum(unread_messages.values())
    completed_count = sum(len(apps) for apps in completed_module_apps.values())
    
    logger.debug(f"Summary: total_apps={total_apps}, pending_reviews={pending_reviews}, total_unread={total_unread}, completed_count={completed_count}")
    
    fixed_modules = [f"module_{i}" for i in range(1, 11)]
    actionable_statuses = ["Under Review"] if current_user.role == "Primary Verifier" else ["Pending Secondary Approval"]
    recent_actionable_modules = set()
    
    # Identify modules with recent actionable applications
    for module in module_apps:
        for app in module_apps[module]:
            if app.status in actionable_statuses and (datetime.now() - app.updated_at).days <= 7:
                recent_actionable_modules.add(module)
                logger.debug(f"Found recent actionable application {app.id} in {module}")
    
    logger.debug(f"Rendering home.html with {len(module_apps)} modules, {len(unread_messages)} apps with messages")
    return render_template(
        "verifier/home.html",
        module_apps=module_apps,
        completed_module_apps=completed_module_apps,
        fixed_modules=fixed_modules,
        recent_actionable_modules=recent_actionable_modules,
        role=current_user.role,
        datetime=datetime,
        csrf_token=generate_csrf,
        unread_messages=unread_messages,
        app_has_secondary_verifier=app_has_secondary_verifier,
        total_apps=total_apps,
        pending_reviews=pending_reviews,
        total_unread=total_unread,
        completed_count=completed_count
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
    
    pdf_download_url = url_for(f"{module_name}_pdf.download_pdf", application_id=application_id, _external=True)

    unread_messages = {}
    unread_count = ChatMessage.query.filter_by(
        application_id=application.id,
        receiver_id=current_user.id,
        read=False
    ).count()
    unread_messages[application.id] = unread_count

    # Fetch all edit requests for the application
    edit_requests = EditRequest.query.filter_by(application_id=application_id).order_by(EditRequest.requested_at.desc()).all()
    
    # Get selected edit request ID from query parameter, default to most recent
    selected_edit_request_id = request.args.get('edit_request_id', type=int)
    if selected_edit_request_id:
        selected_edit_request = EditRequest.query.filter_by(id=selected_edit_request_id, application_id=application_id).first()
    else:
        selected_edit_request = edit_requests[0] if edit_requests else None

    audit_logs = []
    if selected_edit_request:
        # Determine the end of the edit period: either deadline or resubmission time (updated_at)
        end_time = min(selected_edit_request.deadline, application.updated_at) if application.status != "Pending" else selected_edit_request.deadline
        # Filter audit logs within the edit request timeframe
        audit_logs = AuditLog.query.filter(
            AuditLog.application_id == application_id,
            AuditLog.timestamp >= selected_edit_request.requested_at,
            AuditLog.timestamp <= end_time
        ).order_by(AuditLog.timestamp.desc()).all()

    if request.method == "POST":
        logger.debug(f"Processing POST request for application {application_id}, content-type: {request.content_type}")
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
                if not assignment.secondary_verifier_id:
                    application.status = "Pending Director Approval"
                    flash("Application approved. Awaiting Director approval.", "success")
                    notification = Notification(
                        user_id=application.user_id,
                        content=f"Your application #{application.id} has been verified and is awaiting Director approval. Comments: {comments or 'None'}",
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(notification)
                    directors = User.query.filter_by(role="Director").all()
                    for director in directors:
                        notification = Notification(
                            user_id=director.id,
                            content=f"Application #{application.id} is awaiting your final approval.",
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(notification)
                    logger.info(f"Application {application_id} approved, awaiting Director, notifications sent")
                else:
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
                        application.status = "Pending Director Approval"
                        flash("Application verified. Awaiting Director approval.", "success")
                        notification = Notification(
                            user_id=application.user_id,
                            content=f"Your application #{application.id} has been verified by both verifiers and is awaiting Director approval. Comments: {comments or 'None'}",
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(notification)
                        directors = User.query.filter_by(role="Director").all()
                        for director in directors:
                            notification = Notification(
                                user_id=director.id,
                                content=f"Application #{application.id} is awaiting your final approval.",
                                timestamp=datetime.utcnow()
                            )
                            db.session.add(notification)
                        if other_verifier_id:
                            notification = Notification(
                                user_id=other_verifier_id,
                                content=f"Application #{application.id} has been verified and is awaiting Director approval.",
                                timestamp=datetime.utcnow()
                            )
                            db.session.add(notification)
                            logger.info(f"Application {application_id} verified, notifications sent to Directors and Primary Verifier")
            else:
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

            if application.status == "Pending":
                logger.warning(f"Enable edit failed for application {application_id}: Application is already editable")
                return jsonify({"status": "error", "message": "Application is already editable."}), 400

            active_edit_request = EditRequest.query.filter_by(
                application_id=application_id, status="Active"
            ).first()
            if active_edit_request:
                logger.warning(f"Enable edit failed for application {application_id}: Active edit request exists (ID: {active_edit_request.id})")
                return jsonify({"status": "error", "message": "An active edit request already exists."}), 400

            verifier = User.query.get(current_user.id)
            if not verifier:
                logger.error(f"Enable edit failed for application {application_id}: Verifier user {current_user.id} not found")
                return jsonify({"status": "error", "message": "Invalid verifier user."}), 400

            applicant = User.query.get(application.user_id)
            if not applicant:
                logger.error(f"Enable edit failed for application {application_id}: Applicant user {application.user_id} not found")
                return jsonify({"status": "error", "message": "Invalid applicant user."}), 400

            try:
                deadline = datetime.utcnow() + timedelta(days=7)
                logger.debug(f"Setting edit deadline for application {application_id} to {deadline}")

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

                application.status = "Pending"
                application.editable = True
                logger.debug(f"Updated application {application_id} status to Pending and editable to True")

                notification = Notification(
                    user_id=application.user_id,
                    content=f"Application ID {application_id} ({module_name.replace('_', ' ').title()}) is now editable. Reason: {comments}. Please complete edits by {deadline.strftime('%B %d, %Y')}.",
                    timestamp=datetime.utcnow(),
                    read=False
                )
                db.session.add(notification)
                logger.debug(f"Created notification for user {application.user_id}")

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

                db.session.commit()
                logger.info(f"Database committed for application {application_id}")

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
        csrf_token=generate_csrf,
        unread_messages=unread_messages,
        audit_logs=audit_logs,
        edit_requests=edit_requests,
        selected_edit_request=selected_edit_request
    )