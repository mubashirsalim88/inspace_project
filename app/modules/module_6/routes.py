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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_6 = Blueprint("module_6", __name__, url_prefix="/module_6", template_folder="templates")

STEPS = [
    "itu_filing_details",
    "beam_operation_frequency_space_to_earth",
    "beam_operation_frequency_earth_to_space",
    "earth_station_details",
    "communication_satellite_frequency_plan",
    "interference_analysis",
    "space_system_details",
    "undertaking_declaration"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_6.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS and step != "summary":
        logger.error(f"Invalid step requested: {step}. Valid steps are: {STEPS}")
        flash(f"Invalid step: {step}. Redirecting to the first step.", "error")
        return redirect(url_for("module_6.fill_step", step=STEPS[0], application_id=request.args.get("application_id")))

    app_id = request.args.get("application_id")
    if not app_id:
        logger.warning("No application_id provided, redirecting to dashboard")
        flash("Application ID required.", "error")
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (
        application.status != "Pending" and not application.editable and step != "summary"
    ):
        logger.warning(f"Unauthorized access or invalid status for user {current_user.id}, app {app_id}")
        flash("Unauthorized or application not editable.", "error")
        return redirect(url_for("applicant.home"))

    # Check Module 1 completion
    all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
    module_1_complete = False
    required_module_1_steps = [
        "applicant_identity",
        "entity_details",
        "management_ownership",
        "financial_credentials",
        "operational_contact",
        "declarations_submission",
    ]
    for app in all_user_apps:
        module_1_data = ModuleData.query.filter_by(
            application_id=app.id, module_name="module_1"
        ).all()
        if all(
            any(md.step == rs and md.completed for md in module_1_data)
            for rs in required_module_1_steps
        ):
            module_1_complete = True
            break

    if not module_1_complete:
        flash(
            "Please complete Module 1 (Basic Details) for at least one application before starting Module 6.",
            "error",
        )
        logger.info(f"User {current_user.id} redirected to Module 1 due to incomplete Module 1 data")
        existing_module_6_data = ModuleData.query.filter_by(
            application_id=app_id, module_name="module_6"
        ).first()
        if existing_module_6_data and not existing_module_6_data.completed:
            db.session.delete(existing_module_6_data)
            db.session.commit()
        return redirect(
            url_for("module_1.fill_step", step="applicant_identity", application_id=app_id)
        )

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_6", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_6", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_6", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST" and step != "undertaking_declaration":
        form_data = request.form.to_dict()
        file_fields = {
            "communication_satellite_frequency_plan": [
                "gateway_uplink_frequency_doc",
                "gateway_downlink_frequency_doc",
                "user_uplink_frequency_doc",
                "user_downlink_frequency_doc"
            ],
            "interference_analysis": ["coordination_agreement"],
            "undertaking_declaration": ["official_seal"]
        }

        # Capture old data for audit logging
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
                            module_name="module_6",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                        # Log file upload
                        log_file_upload(app_id, "module_6", step, field, f.filename)
                        logger.debug(f"Logged file upload: {field}: {f.filename}")
                    form_data[field] = file_paths
                else:
                    form_data[field] = old_data.get(field, [])
                    logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

        # Update module data
        module_data.data = form_data
        module_data.completed = True

        # Log field changes
        compare_form_data(old_data, form_data, app_id, "module_6", step)
        logger.debug(f"Logged field changes for step {step}, application {app_id}")

        db.session.commit()

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(url_for("module_6.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_6.fill_step", step="summary", application_id=app_id))

    if step == "summary":
        # Fetch Module 6 data
        all_module_6_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_6").all()
        processed_module_6_data = []
        for md in all_module_6_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(v) for v in value]
            processed_module_6_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

        # Fetch latest completed Module 1 data
        latest_module_1_data = []
        latest_app_id = None
        latest_submission_date = None
        for app in all_user_apps:
            module_1_data = ModuleData.query.filter_by(
                application_id=app.id, module_name="module_1"
            ).all()
            if all(
                any(md.step == rs and md.completed for md in module_1_data)
                for rs in required_module_1_steps
            ):
                if not latest_submission_date or app.created_at > latest_submission_date:
                    latest_submission_date = app.created_at
                    latest_app_id = app.id
                    latest_module_1_data = module_1_data

        # Process Module 1 data
        processed_module_1_data = []
        for md in latest_module_1_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc) for doc in value]
            processed_module_1_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

        return render_template(
            "module_6/summary.html",
            all_module_1_data=processed_module_1_data,
            all_module_6_data=processed_module_6_data,
            application_id=app_id,
            application=application
        )

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_6").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    return render_template(
        f"module_6/{step}.html",
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

@module_6.route("/save_undertaking_declaration/<int:application_id>", methods=["POST"])
@login_required
def save_undertaking_declaration(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return jsonify({"status": "error", "message": "Unauthorized or already submitted"}), 403

    form_data = request.form.to_dict()
    file_fields = ["official_seal"]

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_6", step="undertaking_declaration").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_6", step="undertaking_declaration", data={})
        db.session.add(module_data)

    # Capture old data for audit logging
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
                    module_name="module_6",
                    step="undertaking_declaration",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
                # Log file upload
                log_file_upload(application_id, "module_6", "undertaking_declaration", field, f.filename)
                logger.debug(f"Logged file upload: {field}: {f.filename}")
            form_data[field] = file_paths
        else:
            form_data[field] = old_data.get(field, [])
            logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

    for decl in ['apply_for_itu_filing', 'conformity_with_laws']:
        form_data[decl] = decl in request.form

    # Update module data
    module_data.data = form_data
    module_data.completed = True

    # Log field changes
    compare_form_data(old_data, form_data, application_id, "module_6", "undertaking_declaration")
    logger.debug(f"Logged field changes for undertaking_declaration, application {application_id}")

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_6.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("module_6.fill_step", step="summary", application_id=application_id))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_6").all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps.", "error")
        return redirect(url_for("module_6.fill_step", step="undertaking_declaration", application_id=application_id))

    try:
        # Check for EditRequest and ApplicationAssignment
        edit_request = EditRequest.query.filter_by(application_id=application_id, status="Active").first()
        assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first()

        if edit_request and assignment:
            # Reuse existing assignment
            application.status = "Under Review"
            application.editable = False
            edit_request.status = "Completed"
            edit_request.completed_at = datetime.utcnow()

            # Notify original verifiers
            primary_verifier_id = assignment.primary_verifier_id
            secondary_verifier_id = assignment.secondary_verifier_id

            notification = Notification(
                user_id=primary_verifier_id,
                content=f"Application #{application_id} (Module 6) has been resubmitted after edits. Please review.",
                timestamp=datetime.utcnow()
            )
            db.session.add(notification)

            if secondary_verifier_id:
                notification = Notification(
                    user_id=secondary_verifier_id,
                    content=f"Application #{application_id} (Module 6) has been resubmitted after edits. Please review.",
                    timestamp=datetime.utcnow()
                )
                db.session.add(notification)

            flash("Application resubmitted successfully!", "success")
        else:
            # New submission
            application.status = "Submitted"
            application.editable = False
            flash("Application submitted for verification.", "success")

        db.session.commit()
        return redirect(url_for("module_6.fill_step", step="summary", application_id=application_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for("module_6.fill_step", step="undertaking_declaration", application_id=application_id))

@module_6.route("/download_file/<int:file_id>")
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