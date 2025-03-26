# app/modules/module_3/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
from io import BytesIO
import os
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_3 = Blueprint("module_3", __name__, url_prefix="/module_3", template_folder="templates")

STEPS = [
    "renewal_and_provisioning",
    "satellite_constellation_details",
    "payload_details",
    "ground_segment",
    "itu_and_regulatory",
    "launch_and_regulatory",
    "misc_and_declarations",
    "summary"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_3.route("/fill_step/<step>", methods=["GET", "POST"])
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
        logger.warning(f"Unauthorized access or invalid status for user {current_user.id}, app {app_id}")
        return "Unauthorized or invalid application", 403

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_3", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_3", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_3", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST":
        form_data = request.form.to_dict()

        file_fields = {
            "satellite_constellation_details": ["relationship_evidence", "lease_contract"],
            "payload_details": ["hosted_payload_agreement", "hosted_payload_authorization"],
            "itu_and_regulatory": ["foreign_admin_approval", "interference_analysis", "license_copy"],
            "launch_and_regulatory": ["dot_license_copies"],
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
                            module_name="module_3",
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
                return redirect(url_for("module_3.fill_step", step=STEPS[next_step_idx], application_id=app_id))
            return redirect(url_for("module_3.fill_step", step="summary", application_id=app_id))
        return redirect(url_for("module_3.fill_step", step=step, application_id=app_id))

    if step == "summary" and not module_data.completed:
        module_data.completed = True
        db.session.commit()

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_3").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    template_map = {
        "misc_and_declarations": "module_3/misc_and_declarations.html",
        "summary": "module_3/summary.html"
    }
    return render_template(
        template_map.get(step, f"module_3/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

@module_3.route("/submit_application/<application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        flash("Unauthorized or already submitted.", "error")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_3").all()
    required_steps = [s for s in STEPS if s != "summary"]
    completed_steps = [md.step for md in all_module_data if md.completed]
    if not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps.", "error")
        return redirect(url_for("module_3.fill_step", step="misc_and_declarations", application_id=application_id))

    application.status = "Submitted"
    db.session.commit()
    flash("Application submitted successfully!", "success")
    return redirect(url_for("applicant.home", module="module_3"))

@module_3.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("module_3.fill_step", step=STEPS[0], application_id=application.id))
    return render_template("module_3/start_application.html")