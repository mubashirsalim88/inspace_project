# app/dashboard/routes.py
from flask import Blueprint, render_template, jsonify, request, url_for
from flask_login import login_required, current_user
from app.models import Application, ModuleData
from app import db
from app.modules.module_1.routes import STEPS as MODULE_1_STEPS
from app.modules.module_2.routes import STEPS as MODULE_2_STEPS

dashboard = Blueprint("dashboard", __name__, template_folder="templates")

@dashboard.route("/home")
@login_required
def home():
    if current_user.role == "user":
        active_module = request.args.get("module", "module_1")  # Default to module_1 if no module specified
        applications = Application.query.filter_by(user_id=current_user.id).all()
        module_tabs = {f"module_{i}": {"steps": {}, "completed": False} for i in range(1, 16)}
        incomplete_apps = []
        module_apps = {
            "module_1": [],
            "module_2": []
        }
        
        for app in applications:
            module_1_completed = False
            has_module_1_data = False
            has_module_2_data = False
            for md in app.module_data:
                module_tabs[md.module_name]["steps"][md.step] = {"completed": md.completed}
                if md.module_name == "module_1":
                    has_module_1_data = True
                    required_steps = ["applicant_identity", "entity_details", "management_ownership", "financial_credentials", "operational_contact", "declarations_submission"]
                    if all(any(md2.step == rs and md2.completed for md2 in app.module_data) for rs in required_steps):
                        module_1_completed = True
                        module_tabs["module_1"]["completed"] = True
                elif md.module_name == "module_2" and md.completed:  # Only count completed steps for Module 2
                    has_module_2_data = True
            if has_module_1_data and app not in module_apps["module_1"]:
                module_apps["module_1"].append(app)
            if has_module_2_data and app not in module_apps["module_2"]:
                module_apps["module_2"].append(app)
            if not module_1_completed and app not in incomplete_apps:
                incomplete_apps.append(app)
        
        return render_template(
            "user_dashboard.html",
            applications=applications,
            module_tabs=module_tabs,
            incomplete_apps=incomplete_apps,
            module_apps=module_apps,
            active_module=active_module  # Pass active module to template
        )

@dashboard.route("/start_application")
@login_required
def start_application():
    module = request.args.get("module", "module_1")
    pending_app = Application.query.filter_by(user_id=current_user.id, status="Pending").join(ModuleData).filter(ModuleData.module_name == module, ModuleData.abandoned == False).first()
    if pending_app:
        for md in pending_app.module_data:
            md.abandoned = True
        db.session.commit()

    new_app = Application(user_id=current_user.id, status="Pending")
    db.session.add(new_app)
    db.session.flush()

    if module == "module_1":
        steps = MODULE_1_STEPS
        redirect_url = url_for("module_1.fill_step", step=steps[0], application_id=new_app.id)
    elif module == "module_2":
        # Check Module 1 completion before starting Module 2
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials", "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            redirect_url = url_for("module_1.fill_step", step="applicant_identity", application_id=new_app.id)
        else:
            steps = MODULE_2_STEPS
            redirect_url = url_for("module_2.fill_step", step=steps[0], application_id=new_app.id)
    else:
        steps = ["step_1"]
        redirect_url = url_for("dashboard.home")

    module_data = ModuleData(application_id=new_app.id, module_name=module, step=steps[0], data={}, completed=False)
    db.session.add(module_data)
    db.session.commit()
    
    return jsonify({"success": True, "application_id": new_app.id, "redirect_url": redirect_url})