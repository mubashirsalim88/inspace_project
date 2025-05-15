from flask import Blueprint, render_template, jsonify, request, url_for, flash, redirect
from flask_login import login_required, current_user
from app.models import Application, ModuleData
from app import db
from app.modules.module_1.routes import STEPS as MODULE_1_STEPS
from app.modules.module_2.routes import STEPS as MODULE_2_STEPS
from app.modules.module_3.routes import STEPS as MODULE_3_STEPS
from app.modules.module_4.routes import STEPS as MODULE_4_STEPS
from app.modules.module_5.routes import STEPS as MODULE_5_STEPS
from app.modules.module_6.routes import STEPS as MODULE_6_STEPS
from app.modules.module_7.routes import STEPS as MODULE_7_STEPS
from app.modules.module_8.routes import STEPS as MODULE_8_STEPS
from app.modules.module_9.routes import STEPS as MODULE_9_STEPS
from app.modules.module_10.routes import STEPS as MODULE_10_STEPS
from app.__init__ import MODULE_NAME_MAPPING

applicant = Blueprint("applicant", __name__, template_folder="templates")

@applicant.route("/home")
@login_required
def home():
    if current_user.role != "user":
        return redirect(url_for("index"))
    active_module = request.args.get("module", "module_1")
    show_modules = request.args.get("show_modules", "false").lower() == "true"
    applications = Application.query.filter_by(user_id=current_user.id).all()
    module_tabs = {f"module_{i}": {"steps": {}, "completed": False} for i in range(1, 11)}
    incomplete_apps = []
    module_apps = {
        "module_1": [], "module_2": [], "module_3": [], "module_4": [], 
        "module_5": [], "module_6": [], "module_7": [], "module_8": [], 
        "module_9": [], "module_10": []
    }

    # Calculate statistics
    total_applications = Application.query.filter_by(user_id=current_user.id).count()
    approved_applications = Application.query.filter_by(user_id=current_user.id, status="Approved").count()
    pending_applications = Application.query.filter_by(user_id=current_user.id, status="Pending").count()

    for app in applications:
        module_1_completed = False
        module_data_by_module = {
            "module_1": [], "module_2": [], "module_3": [], "module_4": [], 
            "module_5": [], "module_6": [], "module_7": [], "module_8": [], 
            "module_9": [], "module_10": []
        }
        for md in app.module_data:
            if not md.abandoned:
                module_tabs[md.module_name]["steps"][md.step] = {"completed": md.completed}
                module_data_by_module[md.module_name].append(md)
                if md.module_name == "module_1":
                    required_steps = [
                        "applicant_identity", "entity_details", "management_ownership",
                        "financial_credentials", "operational_contact", "declarations_submission"
                    ]
                    if all(any(md2.step == rs and md2.completed for md2 in app.module_data if not md2.abandoned) for rs in required_steps):
                        module_1_completed = True
                        module_tabs["module_1"]["completed"] = True

        for module in ["module_1", "module_2", "module_3", "module_4", "module_5", 
                       "module_6", "module_7", "module_8", "module_9", "module_10"]:
            if module_data_by_module[module] and app not in module_apps[module]:
                module_apps[module].append(app)

        if not module_1_completed and app not in incomplete_apps and any(md.module_name == "module_1" for md in app.module_data if not md.abandoned):
            incomplete_apps.append(app)

    return render_template(
        "applicant/home.html",
        applications=applications,
        module_tabs=module_tabs,
        incomplete_apps=incomplete_apps,
        module_apps=module_apps,
        active_module=active_module,
        show_modules=show_modules,
        active_tab="modules" if show_modules else "home",
        MODULE_NAME_MAPPING=MODULE_NAME_MAPPING,
        total_applications=total_applications,
        approved_applications=approved_applications,
        pending_applications=pending_applications
    )

@applicant.route("/start_application")
@login_required
def start_application():
    if current_user.role != "user":
        return redirect(url_for("index"))
    module = request.args.get("module", "module_1")
    
    # Create new application
    new_app = Application(user_id=current_user.id, status="Pending")
    db.session.add(new_app)
    db.session.flush()

    # Check if module_1 is completed for modules 2-10
    success = True
    steps = []
    redirect_url = url_for("applicant.home")
    module_name_display = MODULE_NAME_MAPPING.get(module, module.replace('_', ' ').title())

    if module == "module_1":
        steps = MODULE_1_STEPS
        redirect_url = url_for("module_1.fill_step", step=steps[0], application_id=new_app.id)
    elif module in MODULE_NAME_MAPPING:
        steps = globals()[f"MODULE_{module.split('_')[1]}_STEPS"]
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed and not md.abandoned for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", 
                           "financial_credentials", "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash(f"Please complete Module 1 (Basic Details) for at least one application before starting {module_name_display}.", "error")
            redirect_url = url_for("applicant.home", module="module_1", show_modules=True)
            success = False
        else:
            redirect_url = url_for(f"{module}.fill_step", step=steps[0], application_id=new_app.id)
    else:
        success = False

    if success:
        module_data = ModuleData(application_id=new_app.id, module_name=module, step=steps[0], data={}, completed=False)
        db.session.add(module_data)

    db.session.commit()

    return jsonify({
        "success": success,
        "application_id": new_app.id,
        "redirect_url": redirect_url,
        "message": f"Please complete Module 1 (Basic Details) for at least one application before starting {module_name_display}." if not success else None
    })

@applicant.route("/edit_application/<int:application_id>", methods=["GET"])
@login_required
def edit_application(application_id):
    if current_user.role != "user":
        flash("Unauthorized access.", "error")
        return redirect(url_for("index"))
    
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("You are not authorized to edit this application.", "error")
        return redirect(url_for("applicant.home"))
    
    if not application.editable or application.status != "Pending":
        flash("This application is not currently editable.", "error")
        return redirect(url_for("applicant.home"))

    # Find the module associated with the application
    module_name = next(
        (md.module_name for md in application.module_data if md.module_name in [f"module_{i}" for i in range(1, 11)] and not md.abandoned),
        None
    )
    if not module_name:
        flash("No valid module found for this application.", "error")
        return redirect(url_for("applicant.home"))

    # Redirect to the appropriate module's fill_step route
    if module_name == "module_1":
        redirect_url = url_for("module_1.fill_step", step="applicant_identity", application_id=application_id)
    elif module_name == "module_2":
        redirect_url = url_for("module_2.fill_step", step="satellite_overview", application_id=application_id)
    elif module_name == "module_3":
        redirect_url = url_for("module_3.fill_step", step="renewal_and_provisioning", application_id=application_id)
    elif module_name == "module_4":
        redirect_url = url_for("module_4.fill_step", step="extension_and_orbit", application_id=application_id)
    elif module_name == "module_5":
        redirect_url = url_for("module_5.fill_step", step="host_space_object_details", application_id=application_id)
    elif module_name == "module_6":
        redirect_url = url_for("module_6.fill_step", step="itu_filing_details", application_id=application_id)
    elif module_name == "module_7":
        redirect_url = url_for("module_7.fill_step", step="previous_authorization", application_id=application_id)
    elif module_name == "module_8":
        redirect_url = url_for("module_8.fill_step", step="renewal_and_extension_details", application_id=application_id)
    elif module_name == "module_9":
        redirect_url = url_for("module_9.fill_step", step="general_info", application_id=application_id)
    elif module_name == "module_10":
        redirect_url = url_for("module_10.fill_step", step="general_info", application_id=application_id)
    else:
        flash("Invalid module configuration.", "error")
        return redirect(url_for("applicant.home"))

    return redirect(redirect_url)

@applicant.route("/abandon_application/<int:application_id>", methods=["POST"])
@login_required
def abandon_application(application_id):
    if current_user.role != "user":
        flash("Unauthorized access.", "error")
        return redirect(url_for("index"))
    
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("You are not authorized to modify this application.", "error")
        return redirect(url_for("applicant.home"))
    
    if application.status != "Pending":
        flash("Only pending applications can be abandoned.", "error")
        return redirect(url_for("applicant.home"))

    for md in application.module_data:
        md.abandoned = True
    db.session.commit()
    
    flash("Application abandoned successfully.", "success")
    return jsonify({"success": True, "message": "Application abandoned successfully."})