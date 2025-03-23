# app/dashboard/routes.py
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.models import Application, ModuleData
from app import db
from app.modules.module_1.routes import STEPS as MODULE_1_STEPS

dashboard = Blueprint("dashboard", __name__, template_folder="templates")

@dashboard.route("/home")
@login_required
def home():
    if current_user.role == "user":
        applications = Application.query.filter_by(user_id=current_user.id).all()
        module_tabs = {f"module_{i}": {"steps": {}, "completed": False} for i in range(1, 16)}
        incomplete_apps = []
        module_apps = {
            "module_1": [],
            "module_2": []
        }
        
        for app in applications:
            for md in app.module_data:
                module_tabs[md.module_name]["steps"][md.step] = {"completed": md.completed}
                if md.module_name in module_apps:
                    if app not in module_apps[md.module_name]:
                        module_apps[md.module_name].append(app)
                if md.module_name == "module_1" and all(s["completed"] for s in module_tabs["module_1"]["steps"].values()):
                    module_tabs["module_1"]["completed"] = True
            if not module_tabs["module_1"]["completed"] and app not in incomplete_apps:
                incomplete_apps.append(app)
        
        return render_template(
            "user_dashboard.html",
            applications=applications,
            module_tabs=module_tabs,
            incomplete_apps=incomplete_apps,
            module_apps=module_apps
        )

@dashboard.route("/start_application")
@login_required
def start_application():
    module = request.args.get("module", "module_1")
    pending_app = Application.query.filter_by(user_id=current_user.id, status="Pending").join(ModuleData).filter(ModuleData.module_name == module, ModuleData.abandoned == False).first()
    if pending_app:
        # Mark existing as abandoned if user wants to start new
        for md in pending_app.module_data:
            md.abandoned = True
        db.session.commit()

    new_app = Application(user_id=current_user.id, status="Pending")
    db.session.add(new_app)
    db.session.flush()

    # Use module-specific steps
    if module == "module_1":
        steps = MODULE_1_STEPS
    else:
        steps = ["step_1"]  # Fallback for other modules (update when Module 2 is added)

    module_data = ModuleData(application_id=new_app.id, module_name=module, step=steps[0], data={}, completed=False)
    db.session.add(module_data)
    db.session.commit()
    return jsonify({"success": True, "application_id": new_app.id})