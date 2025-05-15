from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
)
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, EditRequest, ApplicationAssignment, Notification
from app.utils import compare_form_data, log_file_upload
from datetime import datetime
import os
import logging
import re

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_8 = Blueprint("module_8", __name__, url_prefix="/module_8", template_folder="templates")

STEPS = [
    "renewal_and_extension_details",
    "station_details",
    "technical_information",
    "regulatory_license_details",
    "miscellaneous",
    "undertaking_declaration"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def clean_filename(filename):
    """Convert raw filename to a clean display name."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'^\d+_?', '', name)
    name = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_?', '', name)
    parts = name.split('_')
    if len(parts) > 2:
        step = ' '.join(word.capitalize() for word in parts[0].split('_'))
        field = ' '.join(word.capitalize() for word in '_'.join(parts[1:-1]).split('_'))
        filename_part = ' '.join(word.capitalize() for word in parts[-1].split('_'))
        name = f"{step} {field} {filename_part}"
    else:
        name = ' '.join(word.capitalize() for word in name.split('_'))
    if len(name) > 80:
        name = name[:77] + "..."
    return name

@module_8.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS and step != "summary":
        logger.error(f"Invalid step requested: {step}. Valid steps are: {STEPS}")
        flash(f"Invalid step: {step}. Redirecting to the first step.", "error")
        return redirect(url_for("module_8.fill_step", step=STEPS[0], application_id=request.args.get("application_id")))

    app_id = request.args.get("application_id")
    if not app_id:
        logger.warning("No application_id provided, redirecting to dashboard")
        flash("Application ID required.", "error")
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id:
        logger.warning(f"Unauthorized access for user {current_user.id}, app {app_id}")
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))

    # If the application is submitted, only allow access to the summary page
    if application.status == "Submitted" and step != "summary":
        logger.debug(f"Application {app_id} is submitted, redirecting to summary")
        return redirect(url_for("module_8.fill_step", step="summary", application_id=app_id))

    # If the application is not pending and the step is not summary, redirect to home
    if application.status != "Pending" and step != "summary":
        logger.warning(f"Application {app_id} is not editable (status: {application.status})")
        flash("Application not editable.", "error")
        return redirect(url_for("applicant.home"))

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_8", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_8", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_8", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST" and step != "undertaking_declaration":
        form_data = request.form.to_dict()
        file_fields = {
            "station_details": ["station_technical_specs_doc"],
            "technical_information": ["frequency_allocation_doc"],
            "regulatory_license_details": ["license_document"],
            "miscellaneous": ["additional_documents"],
            "undertaking_declaration": ["official_seal"]
        }

        old_data = module_data.data.copy() if module_data.data else {}

        if step in file_fields:
            for field in file_fields[step]:
                files = request.files.getlist(field)
                if files and files[0].filename:
                    file_paths = []
                    for f in files:
                        filename = f"{app_id}_{step}_{field}_{f.filename}"
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        f.save(file_path)
                        relative_path = os.path.join("Uploads", filename)
                        uploaded_file = UploadedFile(
                            application_id=app_id,
                            module_name="module_8",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                        log_file_upload(app_id, "module_8", step, field, f.filename)
                        logger.debug(f"Logged file upload: {field}: {f.filename}")
                    form_data[field] = file_paths
                else:
                    form_data[field] = old_data.get(field, [])
                    logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

        module_data.data = form_data
        module_data.completed = True
        compare_form_data(old_data, form_data, app_id, "module_8", step)
        logger.debug(f"Logged field changes for step {step}, application {app_id}")

        db.session.commit()

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(url_for("module_8.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_8.fill_step", step="summary", application_id=app_id))

    if step == "summary":
        # Fetch Module 8 data
        module_8_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_8").all()
        
        # Fetch latest completed Module 1 data
        all_user_apps = Application.query.filter_by(user_id=application.user_id).all()
        latest_module_1_data = []
        latest_app_id = None
        latest_submission_date = None
        required_module_1_steps = [
            "applicant_identity", "entity_details", "management_ownership",
            "financial_credentials", "operational_contact", "declarations_submission"
        ]
        for app in all_user_apps:
            module_1_data = ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all()
            if all(
                any(md.step == rs and md.completed for md in module_1_data)
                for rs in required_module_1_steps
            ):
                if not latest_submission_date or app.created_at > latest_submission_date:
                    latest_submission_date = app.created_at
                    latest_app_id = app.id
                    latest_module_1_data = module_1_data

        # Combine Module 1 and Module 8 data
        all_module_data = []
        for md in latest_module_1_data:
            if md.step.lower() != "summary":
                data_copy = md.data.copy()
                for key, value in data_copy.items():
                    if isinstance(value, list) and all(isinstance(v, str) for v in value):
                        data_copy[key] = [
                            {"display_name": clean_filename(os.path.basename(doc)), "file_path": doc}
                            for doc in value
                        ]
                all_module_data.append({
                    "module_name": "module_1",
                    "step": md.step,
                    "data": data_copy,
                    "completed": md.completed
                })

        for md in module_8_data:
            if md.step.lower() != "summary":
                data_copy = md.data.copy()
                for key, value in data_copy.items():
                    if isinstance(value, list) and all(isinstance(v, str) for v in value):
                        data_copy[key] = [
                            {"display_name": clean_filename(os.path.basename(doc)), "file_path": doc}
                            for doc in value
                        ]
                all_module_data.append({
                    "module_name": "module_8",
                    "step": md.step,
                    "data": data_copy,
                    "completed": md.completed
                })

        # Fetch uploaded files for both modules
        uploaded_files = []
        if latest_app_id:
            uploaded_files += UploadedFile.query.filter_by(application_id=latest_app_id, module_name="module_1").all()
        uploaded_files += UploadedFile.query.filter_by(application_id=app_id, module_name="module_8").all()
        file_id_map = {clean_filename(f.filename): f.id for f in uploaded_files}
        file_path_map = {clean_filename(f.filename): f.filepath for f in uploaded_files}

        return render_template(
            "module_8/summary.html",
            all_module_data=all_module_data,
            application_id=app_id,
            application=application,
            file_id_map=file_id_map,
            file_path_map=file_path_map
        )

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_8").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [
                    {"display_name": clean_filename(os.path.basename(doc)), "file_path": doc}
                    for doc in value
                ]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    return render_template(
        f"module_8/{step}.html",
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

@module_8.route("/save_undertaking_declaration/<int:application_id>", methods=["POST"])
@login_required
def save_undertaking_declaration(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return jsonify({"status": "error", "message": "Unauthorized or already submitted"}), 403

    form_data = request.form.to_dict()
    file_fields = ["official_seal"]

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_8", step="undertaking_declaration").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_8", step="undertaking_declaration", data={})
        db.session.add(module_data)

    old_data = module_data.data.copy() if module_data.data else {}

    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = f"{application_id}_undertaking_declaration_{field}_{f.filename}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("Uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_8",
                    step="undertaking_declaration",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
                log_file_upload(application_id, "module_8", "undertaking_declaration", field, f.filename)
                logger.debug(f"Logged file upload: {field}: {f.filename}")
            form_data[field] = file_paths
        else:
            form_data[field] = old_data.get(field, [])
            logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

    for decl in ['apply_for_authorization', 'conformity_with_laws']:
        form_data[decl] = decl in request.form

    module_data.data = form_data
    module_data.completed = True
    compare_form_data(old_data, form_data, application_id, "module_8", "undertaking_declaration")
    logger.debug(f"Logged field changes for undertaking_declaration, application {application_id}")

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_8.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("module_8.fill_step", step="summary", application_id=application_id))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_8").all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(url_for("module_8.fill_step", step="undertaking_declaration", application_id=application_id))

    try:
        edit_request = EditRequest.query.filter_by(application_id=application_id, status="Active").first()
        assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first()

        if edit_request and assignment:
            application.status = "Under Review"
            application.editable = False
            edit_request.status = "Completed"
            edit_request.completed_at = datetime.utcnow()

            primary_verifier_id = assignment.primary_verifier_id
            secondary_verifier_id = assignment.secondary_verifier_id

            notification = Notification(
                user_id=primary_verifier_id,
                content=f"Application #{application_id} (Module 8) has been resubmitted after edits. Please review.",
                timestamp=datetime.utcnow()
            )
            db.session.add(notification)

            if secondary_verifier_id:
                notification = Notification(
                    user_id=secondary_verifier_id,
                    content=f"Application #{application_id} (Module 8) has been resubmitted after edits. Please review.",
                    timestamp=datetime.utcnow()
                )
                db.session.add(notification)

            flash("Application resubmitted successfully!", "success")
        else:
            application.status = "Submitted"
            application.editable = False
            flash("Application submitted for verification.", "success")

        db.session.commit()
        return redirect(url_for("module_8.fill_step", step="summary", application_id=application_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for("module_8.fill_step", step="undertaking_declaration", application_id=application_id))

@module_8.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    application = Application.query.get_or_404(uploaded_file.application_id)
    if application.user_id != current_user.id:
        return "Unauthorized", 403
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath)
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    return send_file(full_path, as_attachment=True, download_name=uploaded_file.filename)