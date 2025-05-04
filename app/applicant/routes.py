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

applicant = Blueprint("applicant", __name__, template_folder="templates")

@applicant.route("/home")
@login_required
def home():
    if current_user.role != "user":
        return redirect(url_for("index"))
    active_module = request.args.get("module", "module_1")
    applications = Application.query.filter_by(user_id=current_user.id).all()
    module_tabs = {f"module_{i}": {"steps": {}, "completed": False} for i in range(1, 11)}
    incomplete_apps = []
    module_apps = {
        "module_1": [], "module_2": [], "module_3": [], "module_4": [], 
        "module_5": [], "module_6": [], "module_7": [], "module_8": [], 
        "module_9": [], "module_10": []
    }

    for app in applications:
        module_1_completed = False
        module_data_by_module = {
            "module_1": [], "module_2": [], "module_3": [], "module_4": [], 
            "module_5": [], "module_6": [], "module_7": [], "module_8": [], 
            "module_9": [], "module_10": []
        }
        for md in app.module_data:
            module_tabs[md.module_name]["steps"][md.step] = {"completed": md.completed}
            module_data_by_module[md.module_name].append(md)
            if md.module_name == "module_1":
                required_steps = [
                    "applicant_identity", "entity_details", "management_ownership",
                    "financial_credentials", "operational_contact", "declarations_submission"
                ]
                if all(any(md2.step == rs and md2.completed for md2 in app.module_data) for rs in required_steps):
                    module_1_completed = True
                    module_tabs["module_1"]["completed"] = True

        for module in ["module_1", "module_2", "module_3", "module_4", "module_5", 
                       "module_6", "module_7", "module_8", "module_9", "module_10"]:
            if module_data_by_module[module] and app not in module_apps[module]:
                module_apps[module].append(app)

        if not module_1_completed and app not in incomplete_apps:
            incomplete_apps.append(app)

    return render_template(
        "applicant/home.html",
        applications=applications,
        module_tabs=module_tabs,
        incomplete_apps=incomplete_apps,
        module_apps=module_apps,
        active_module=active_module
    )

@applicant.route("/start_application")
@login_required
def start_application():
    if current_user.role != "user":
        return redirect(url_for("index"))
    module = request.args.get("module", "module_1")
    pending_app = Application.query.filter_by(user_id=current_user.id, status="Pending").join(ModuleData).filter(
        ModuleData.module_name == module, ModuleData.abandoned == False).first()
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
        success = True
    elif module == "module_2":
        steps = MODULE_2_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 2.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_2.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_3":
        steps = MODULE_3_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 3.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_3.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_4":
        steps = MODULE_4_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 4.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_4.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_5":
        steps = MODULE_5_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 5.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_5.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_6":
        steps = MODULE_6_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 6.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_6.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_7":
        steps = MODULE_7_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 7.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_7.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_8":
        steps = MODULE_8_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 8.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_8.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_9":
        steps = MODULE_9_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 9.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_9.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    elif module == "module_10":
        steps = MODULE_10_STEPS
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        module_1_complete = any(
            all(any(md.step == rs and md.completed for md in
                    ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all())
                for rs in ["applicant_identity", "entity_details", "management_ownership", "financial_credentials",
                           "operational_contact", "declarations_submission"])
            for app in all_user_apps
        )
        if not module_1_complete:
            flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 10.", "error")
            redirect_url = url_for("applicant.home", module="module_1")
            success = False
        else:
            redirect_url = url_for("module_10.fill_step", step=steps[0], application_id=new_app.id)
            success = True
    else:
        steps = ["step_1"]
        redirect_url = url_for("applicant.home")
        success = False

    if success:
        module_data = ModuleData(application_id=new_app.id, module_name=module, step=steps[0], data={}, completed=False)
        db.session.add(module_data)

    db.session.commit()

    return jsonify({
        "success": success,
        "application_id": new_app.id,
        "redirect_url": redirect_url,
        "message": f"Please complete Module 1 (Basic Details) for at least one application before starting {module.replace('_', ' ').title()}." if not success else None
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
        (md.module_name for md in application.module_data if md.module_name in [f"module_{i}" for i in range(1, 11)]),
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