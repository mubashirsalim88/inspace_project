# app/modules/module_4/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
from werkzeug.utils import secure_filename
import os
import io
import logging

module_4 = Blueprint("module_4", __name__, template_folder="templates")
logger = logging.getLogger(__name__)

STEPS = [
    "extension_and_orbit",
    "satellite_details",
    "configuration_and_safety",
    "manufacturing_and_procurement",
    "payload_details",
    "ground_segment",
    "itu_and_regulatory",
    "launch_and_insurance",
    "miscellaneous_and_declarations",
    "summary"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_4.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS:
        logger.error(f"Invalid step requested: {step}")
        return "Invalid step", 404

    app_id = request.args.get("application_id")
    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or application.status != "Pending":
        flash("Unauthorized access or application not editable.", "error")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_4").all()
    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_4", step=step).first()
    form_data = module_data.data if module_data else {}
    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_4", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[(f.id, f.filename) for f in existing_files]}")

    if request.method == "POST":
        form_data = request.form.to_dict()
        files = request.files.getlist("files") if "files" in request.files else []

        if not module_data:
            module_data = ModuleData(application_id=app_id, module_name="module_4", step=step, data=form_data, completed=False)
            db.session.add(module_data)
        else:
            module_data.data = form_data

        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                uploaded_file = UploadedFile(application_id=app_id, module_name="module_4", step=step, field_name=file.name, filename=filename, filepath=file_path)
                db.session.add(uploaded_file)

        module_data.completed = True
        db.session.commit()

        if "next" in request.form:
            next_step = STEPS[STEPS.index(step) + 1] if step != STEPS[-1] else step
            return redirect(url_for("module_4.fill_step", step=next_step, application_id=app_id))
        elif "previous" in request.form and step != STEPS[0]:
            previous_step = STEPS[STEPS.index(step) - 1]
            return redirect(url_for("module_4.fill_step", step=previous_step, application_id=app_id))

    return render_template(
        f"module_4/{step}.html",
        form_data=form_data,
        application_id=app_id,
        steps=STEPS,
        current_step=step,
        all_module_data=all_module_data,
        existing_files=existing_files,
        application=application
    )

@module_4.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    if uploaded_file.application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    return send_file(uploaded_file.filepath, as_attachment=True, download_name=uploaded_file.filename)

@module_4.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        flash("Unauthorized access or application already submitted.", "error")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_4").all()
    completed_steps = {md.step for md in all_module_data if md.completed}
    required_steps = set(STEPS[:-1])  # Exclude 'summary'
    
    if not required_steps.issubset(completed_steps):
        flash("Please complete all required steps.", "error")
        return redirect(url_for("module_4.fill_step", step="summary", application_id=application_id))

    application.status = "Submitted"
    db.session.commit()
    flash("Application submitted successfully!", "success")
    return redirect(url_for("applicant.home"))