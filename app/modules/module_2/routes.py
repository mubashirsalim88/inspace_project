# app/modules/module_2/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
from io import BytesIO
import os
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_2 = Blueprint("module_2", __name__, url_prefix="/module_2", template_folder="templates")

STEPS = [
    "satellite_overview",
    "satellite_configuration",
    "safety_and_manufacturing",
    "payload_details",
    "ground_segment",
    "itu_and_regulatory",
    "misc_and_declarations",
    "summary"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_2.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS:
        logger.error(f"Invalid step requested: {step}")
        return "Invalid step", 404

    app_id = request.args.get("application_id")
    if not app_id:
        logger.warning("No application_id provided, redirecting to dashboard")
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (application.status != "Pending" and step != "summary"):
        logger.warning(f"Unauthorized access or invalid application status for user {current_user.id}, app {app_id}")
        return "Unauthorized or invalid application", 403

    # Check Module 1 completion before proceeding with Module 2
    all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
    module_1_complete = False
    required_module_1_steps = ["applicant_identity", "entity_details", "management_ownership", "financial_credentials", "operational_contact", "declarations_submission"]

    for app in all_user_apps:
        module_1_data = ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all()
        if all(any(md.step == rs and md.completed for md in module_1_data) for rs in required_module_1_steps):
            module_1_complete = True
            break

    if not module_1_complete:
        flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 2.", "error")
        logger.info(f"User {current_user.id} redirected to Module 1 due to incomplete Module 1 data")
        # Redirect to Module 1 without creating Module 2 data
        existing_module_2_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2").first()
        if existing_module_2_data and not existing_module_2_data.completed:
            db.session.delete(existing_module_2_data)  # Clean up incomplete Module 2 data
            db.session.commit()
        return redirect(url_for("module_1.fill_step", step="applicant_identity", application_id=app_id))

    # Only create ModuleData if Module 1 is complete
    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_2", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_2", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST":
        form_data = request.form.to_dict()

        file_fields = {
            "safety_and_manufacturing": ["safety_assessment_report", "consent_document"],
            "payload_details": ["annexure_4"],
            "ground_segment": [],
            "itu_and_regulatory": ["interference_analysis_indian", "interference_analysis_non_indian", "annexure_2", "launch_service_agreement", "insurance_details", "dot_license_copies"],
            "misc_and_declarations": ["official_seal"]
        }

        if step in file_fields:
            for field in file_fields[step]:
                files = request.files.getlist(field)
                if files and files[0].filename:
                    file_paths = []
                    for f in files:
                        filename = f"{app_id}_{step}_{field}_{f.filename}"
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        f.save(file_path)
                        relative_path = os.path.join("uploads", filename)
                        uploaded_file = UploadedFile(
                            application_id=app_id,
                            module_name="module_2",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                        logger.debug(f"Uploaded {field}: {f.filename} to {file_path}")
                    form_data[field] = file_paths
                else:
                    form_data[field] = module_data.data.get(field, [])
                    logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

        module_data.data = form_data
        module_data.completed = True
        db.session.commit()

        if "next" in request.form:
            next_step_idx = STEPS.index(step) + 1
            if next_step_idx < len(STEPS):
                return redirect(url_for("module_2.fill_step", step=STEPS[next_step_idx], application_id=app_id))
            return redirect(url_for("module_2.fill_step", step="summary", application_id=app_id))
        return redirect(url_for("module_2.fill_step", step=step, application_id=app_id))

    if step == "summary" and not module_data.completed:
        module_data.completed = True
        db.session.commit()

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    template_map = {
        "misc_and_declarations": "module_2/misc_and_declarations.html",
        "summary": "module_2/summary.html"
    }
    return render_template(
        template_map.get(step, f"module_2/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

@module_2.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    application = Application.query.get_or_404(uploaded_file.application_id)
    if application.user_id != current_user.id:
        return "Unauthorized", 403
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath)
    print(f"Attempting to download: {full_path}")
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    return send_file(full_path, as_attachment=True, download_name=uploaded_file.filename)

@module_2.route("/submit_application/<application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_2").all()
    required_steps = [s for s in STEPS if s != "summary"]
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(url_for("module_2.fill_step", step="misc_and_declarations", application_id=application_id))

    application.status = "Submitted"
    db.session.commit()
    flash("Application submitted successfully!", "success")
    return redirect(url_for("applicant.home", module="module_2"))

@module_2.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("module_2.fill_step", step=STEPS[0], application_id=application.id))
    return render_template("module_2/start_application.html")