# app/verifier/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Application, ApplicationAssignment, User
from app.utils import role_required

verifier = Blueprint("verifier", __name__, url_prefix="/verifier", template_folder="templates")

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
        if app.status == "Under Review" and app.id not in app_ids:
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
    application = Application.query.get(application_id)
    
    if current_user.id not in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
        flash("You are not authorized to review this application.", "error")
        return redirect(url_for("verifier.home"))

    if application.status != "Under Review":
        flash("This application is not in a reviewable state.", "error")
        return redirect(url_for("verifier.home"))

    # Fetch verifier objects
    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id)

    if request.method == "POST":
        decision = request.form.get("decision")
        comments = request.form.get("comments")
        
        if decision not in ["approve", "reject"]:
            flash("Invalid decision.", "error")
            return redirect(url_for("verifier.review", application_id=application_id))

        if decision == "reject" and not comments:
            flash("Comments are required when rejecting an application.", "error")
            return redirect(url_for("verifier.review", application_id=application_id))

        if decision == "approve":
            if current_user.role == "Primary Verifier":
                application.status = "Primary Verified" if assignment.secondary_verifier_id else "Verified"
            elif current_user.role == "Secondary Verifier":
                application.status = "Verified" if application.status == "Primary Verified" else "Secondary Verified"
            flash("Application approved. Awaiting other verifier if applicable.", "success")
        else:
            application.status = "Rejected"
            # application.rejection_comments = comments  # Uncomment when column is added
            flash(f"Application rejected. Comments: {comments}", "success")

        db.session.commit()
        return redirect(url_for("verifier.home"))

    return render_template(
        "verifier/review.html",
        application=application,
        assignment=assignment,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier,
        role=current_user.role
    )