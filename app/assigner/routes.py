from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Application, ApplicationAssignment, User
from app.utils import role_required
from datetime import datetime, timedelta
from app.__init__ import MODULE_NAME_MAPPING

assigner = Blueprint("assigner", __name__, url_prefix="/assigner", template_folder="templates")

@assigner.route("/home")
@login_required
@role_required("Assigner")
def home():
    applications = Application.query.all()
    assigned_applications = Application.query.join(ApplicationAssignment).filter(ApplicationAssignment.assigner_id == current_user.id).all()
    
    module_apps = {f"module_{i}": [] for i in range(1, 11)}
    assigned_module_apps = {f"module_{i}": [] for i in range(1, 11)}
    
    for app in applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in module_apps), None)
        if module_name:
            module_apps[module_name].append(app)
    
    for app in assigned_applications:
        module_name = next((md.module_name for md in app.module_data if md.module_name in assigned_module_apps), None)
        if module_name:
            assigned_module_apps[module_name].append(app)

    recent_modules = set()
    for module in module_apps:
        for app in module_apps[module]:
            if app.status == "Submitted" and (datetime.now() - app.updated_at).days <= 7:
                recent_modules.add(module)

    return render_template(
        "assigner/home.html",
        module_apps=module_apps,
        assigned_module_apps=assigned_module_apps,
        recent_modules=recent_modules,
        datetime=datetime,
        MODULE_NAME_MAPPING=MODULE_NAME_MAPPING
    )

@assigner.route("/assign/<int:application_id>", methods=["GET", "POST"])
@login_required
@role_required("Assigner")
def assign(application_id):
    application = Application.query.get_or_404(application_id)
    if application.status != "Submitted":
        flash("Application not ready for assignment.", "error")
        return redirect(url_for("assigner.home"))

    if request.method == "POST":
        primary_id = request.form.get("primary_verifier_id")
        secondary_id = request.form.get("secondary_verifier_id")
        if not primary_id or not secondary_id:
            flash("Please select both verifiers.", "error")
            return redirect(url_for("assigner.assign", application_id=application_id))
        
        assignment = ApplicationAssignment(
            application_id=application_id,
            assigner_id=current_user.id,
            primary_verifier_id=primary_id,
            secondary_verifier_id=secondary_id
        )
        db.session.add(assignment)
        application.status = "Under Review"
        db.session.commit()
        flash("Application assigned successfully!", "success")
        return redirect(url_for("assigner.home"))

    verifiers = User.query.filter(User.role.in_(["Primary Verifier", "Secondary Verifier"])).all()
    return render_template("assigner/assign.html", application=application, verifiers=verifiers)

@assigner.route("/view_assignment/<int:application_id>")
@login_required
@role_required("Assigner")
def view_assignment(application_id):
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    application = Application.query.get(application_id)
    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id)
    return render_template(
        "assigner/view_assignment.html",
        application=application,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier
    )