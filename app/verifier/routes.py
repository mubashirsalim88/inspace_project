# app/verifier/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db, mail
from app.models import Application, ApplicationAssignment, User, Notification
from app.utils import role_required
from flask_mail import Message
import logging

verifier = Blueprint("verifier", __name__, url_prefix="/verifier", template_folder="templates")

logger = logging.getLogger(__name__)

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
    
    module_apps = {"module_1": [], "module_2": [], "module_3": [], "module_4": []}
    for app in applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in module_apps), None)
        if module_name:
            module_apps[module_name].append(app)

    return render_template(
        "verifier/home.html",
        module_apps=module_apps,
        role=current_user.role
    )

@verifier.route("/review/<int:application_id>", methods=["GET", "POST"])
@login_required
@role_required(["Primary Verifier", "Secondary Verifier"])
def review(application_id):
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    application = Application.query.get_or_404(application_id)
    
    if current_user.id not in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
        flash("You are not authorized to review this application.", "error")
        return redirect(url_for("verifier.home"))

    # Allow review only if status is actionable for the current verifier
    if application.status not in ["Under Review", 
                                 "Pending Secondary Approval" if current_user.role == "Secondary Verifier" else None]:
        flash("This application is not in a reviewable state.", "error")
        return redirect(url_for("verifier.home"))

    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id) if assignment.secondary_verifier_id else None

    module_name = next(
        (md.module_name for md in application.module_data if md.module_name in ["module_1", "module_2", "module_3", "module_4"]),
        None
    )
    if not module_name:
        flash("No valid module found for this application.", "error")
        return redirect(url_for("verifier.home"))
    
    pdf_download_url = url_for(f"{module_name}.download_pdf", application_id=application_id)

    if request.method == "POST":
        action = request.form.get("action")
        other_verifier_id = assignment.secondary_verifier_id if current_user.role == "Primary Verifier" else assignment.primary_verifier_id

        if action == "review":
            decision = request.form.get("decision")
            comments = request.form.get("comments")
            
            if decision not in ["approve", "reject"]:
                flash("Invalid decision.", "error")
                return redirect(url_for("verifier.review", application_id=application_id))

            if decision == "reject" and not comments:
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
                        timestamp=db.func.now()
                    )
                    db.session.add(notification)
                else:  # Two verifiers
                    if current_user.role == "Primary Verifier" and application.status == "Under Review":
                        application.status = "Pending Secondary Approval"
                        flash("Approval submitted. Awaiting Secondary Verifier.", "success")
                        if other_verifier_id:
                            notification = Notification(
                                user_id=other_verifier_id,
                                content=f"{current_user.username} approved application #{application.id}. Your approval is needed.",
                                timestamp=db.func.now()
                            )
                            db.session.add(notification)
                    elif current_user.role == "Secondary Verifier" and application.status == "Pending Secondary Approval":
                        application.status = "Approved"
                        flash("Application fully approved.", "success")
                        notification = Notification(
                            user_id=application.user_id,
                            content=f"Your application #{application.id} has been approved by both verifiers. Comments: {comments or 'None'}",
                            timestamp=db.func.now()
                        )
                        db.session.add(notification)
                        if other_verifier_id:
                            notification = Notification(
                                user_id=other_verifier_id,
                                content=f"Application #{application.id} has been fully approved.",
                                timestamp=db.func.now()
                            )
                            db.session.add(notification)
            else:  # Reject
                application.status = "Rejected"
                flash(f"Application rejected. Comments: {comments}", "success")
                notification = Notification(
                    user_id=application.user_id,
                    content=f"Your application #{application.id} has been rejected. Comments: {comments}",
                    timestamp=db.func.now()
                )
                db.session.add(notification)
                if other_verifier_id:
                    notification = Notification(
                        user_id=other_verifier_id,
                        content=f"{current_user.username} rejected application #{application.id}. Comments: {comments}",
                        timestamp=db.func.now()
                    )
                    db.session.add(notification)

            db.session.commit()
            return redirect(url_for("verifier.home"))

        elif action == "enable_edit":
            try:
                application.status = "Pending"
                db.session.commit()

                notification = Notification(
                    user_id=application.user_id,
                    content=f"Application ID {application_id} is now editable by request of {current_user.username}.",
                    timestamp=db.func.now(),
                    read=False
                )
                db.session.add(notification)

                msg = Message(
                    "Application Edit Enabled - IN-SPACe Portal",
                    sender="noreply@inspace.gov.in",
                    recipients=[application.user.email]
                )
                msg.body = f"Your application (ID: {application_id}) is now editable. Please make the necessary changes and resubmit.\n\nLogin: {url_for('auth.login', _external=True)}"
                mail.send(msg)

                db.session.commit()
                return jsonify({"status": "success", "message": "Edit enabled for applicant."})
            except Exception as e:
                logger.error(f"Error enabling edit for application {application_id}: {str(e)}")
                db.session.rollback()
                return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

    return render_template(
        "verifier/review.html",
        application=application,
        assignment=assignment,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier,
        pdf_download_url=pdf_download_url,
        role=current_user.role
    )