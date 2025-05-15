from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    jsonify,
)
from flask_login import login_required, current_user
from app import db
from app.models import (
    Application,
    ModuleData,
    UploadedFile,
    EditRequest,
    ApplicationAssignment,
    Notification,
)
from app.utils import compare_form_data, log_file_upload
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_4 = Blueprint(
    "module_4", __name__, url_prefix="/module_4", template_folder="templates"
)

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
]

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "Uploads"
)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@module_4.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS and step != "summary":
        logger.error(f"Invalid step requested: {step}")
        return "Invalid step", 404

    app_id = request.args.get("application_id")
    if not app_id:
        logger.warning("No application_id provided, redirecting to dashboard")
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (
        application.status != "Pending"
        and not application.editable
        and step != "summary"
    ):
        flash("Unauthorized access or application not editable.", "error")
        return redirect(url_for("applicant.home"))

    module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_4", step=step
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=app_id, module_name="module_4", step=step, data={}
        )
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(
        application_id=app_id, module_name="module_4", step=step
    ).all()
    logger.debug(
        f"Step: {step}, Existing Files: {[(f.id, f.filename, f.field_name, f.filepath) for f in existing_files]}"
    )

    if request.method == "POST" and step != "miscellaneous_and_declarations":
        form_data = request.form.to_dict()
        file_fields = {
            "extension_and_orbit": ["orbit_plans"],
            "satellite_details": ["design_documents", "technical_specs"],
            "configuration_and_safety": ["safety_assessments"],
            "manufacturing_and_procurement": [
                "manufacturing_contracts",
                "procurement_agreements",
            ],
            "payload_details": ["payload_specs", "payload_agreements"],
            "ground_segment": ["ground_station_plans"],
            "itu_and_regulatory": ["authorization_files", "interference_files"],
            "launch_and_insurance": ["launch_contracts", "insurance_policies"],
            "miscellaneous_and_declarations": ["official_seal"],
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
                            module_name="module_4",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path,
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                        # Log file upload
                        log_file_upload(app_id, "module_4", step, field, f.filename)
                        logger.debug(f"Logged file upload: {field}: {f.filename}")
                    form_data[field] = file_paths
                else:
                    form_data[field] = old_data.get(field, [])
                    logger.debug(
                        f"No new upload for {field}, retaining: {form_data[field]}"
                    )
            logger.debug(f"Step {step} form_data: {form_data}")

        # Update module data
        module_data.data = form_data
        module_data.completed = True

        # Log field changes
        compare_form_data(old_data, form_data, app_id, "module_4", step)
        logger.debug(f"Logged field changes for step {step}, application {app_id}")

        try:
            db.session.commit()
            logger.debug(f"Saved ModuleData for step {step}: {module_data.data}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving ModuleData for step {step}: {str(e)}")
            flash(f"Error saving data: {str(e)}", "error")
            return redirect(
                url_for("module_4.fill_step", step=step, application_id=app_id)
            )

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(
                url_for(
                    "module_4.fill_step",
                    step=STEPS[next_step_idx],
                    application_id=app_id,
                )
            )
        return redirect(
            url_for("module_4.fill_step", step="summary", application_id=app_id)
        )

    if step == "summary":
        # Fetch Module 4 data
        all_module_4_data = ModuleData.query.filter_by(
            application_id=app_id, module_name="module_4"
        ).all()
        processed_module_4_data = []
        uploaded_files = []
        file_fields = {
            "extension_and_orbit": ["orbit_plans"],
            "satellite_details": ["design_documents", "technical_specs"],
            "configuration_and_safety": ["safety_assessments"],
            "manufacturing_and_procurement": [
                "manufacturing_contracts",
                "procurement_agreements",
            ],
            "payload_details": ["payload_specs", "payload_agreements"],
            "ground_segment": ["ground_station_plans"],
            "itu_and_regulatory": ["authorization_files", "interference_files"],
            "launch_and_insurance": ["launch_contracts", "insurance_policies"],
            "miscellaneous_and_declarations": ["official_seal", "additional_documents"],
        }
        for md in all_module_4_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if (
                    key in sum(file_fields.values(), [])
                    and isinstance(value, list)
                    and all(isinstance(v, str) for v in value)
                ):
                    for file_path in value:
                        if os.path.exists(
                            os.path.join(os.path.dirname(__file__), "..", file_path)
                        ):
                            uploaded_files.append(
                                {
                                    "step": md.step,
                                    "field": key,
                                    "filename": os.path.basename(file_path),
                                }
                            )
                            logger.debug(
                                f"Summary - Added file from ModuleData: Step: {md.step}, Field: {key}, File: {os.path.basename(file_path)}"
                            )
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc) for doc in value]
            processed_module_4_data.append(
                {"step": md.step, "data": data_copy, "completed": md.completed}
            )

        # Fetch from UploadedFile as fallback
        uploaded_file_entries = UploadedFile.query.filter_by(
            application_id=app_id, module_name="module_4"
        ).all()
        existing_files = {
            os.path.join(os.path.dirname(__file__), "..", f.filepath)
            for f in uploaded_file_entries
        }
        for f in uploaded_file_entries:
            absolute_path = os.path.join(os.path.dirname(__file__), "..", f.filepath)
            if absolute_path in existing_files and os.path.exists(absolute_path):
                if not any(uf["filename"] == f.filename for uf in uploaded_files):
                    uploaded_files.append(
                        {"step": f.step, "field": f.field_name, "filename": f.filename}
                    )
                    logger.debug(
                        f"Summary - Added file from UploadedFile: Step: {f.step}, Field: {f.field_name}, File: {f.filename}"
                    )

        # Fetch latest completed Module 1 data
        all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
        required_module_1_steps = [
            "applicant_identity",
            "entity_details",
            "management_ownership",
            "financial_credentials",
            "operational_contact",
            "declarations_submission",
        ]
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
                if (
                    not latest_submission_date
                    or app.created_at > latest_submission_date
                ):
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
            processed_module_1_data.append(
                {"step": md.step, "data": data_copy, "completed": md.completed}
            )

        return render_template(
            "module_4/summary.html",
            all_module_1_data=processed_module_1_data,
            all_module_4_data=processed_module_4_data,
            application_id=app_id,
            application=application,
            uploaded_files=uploaded_files,
        )

    all_module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_4"
    ).all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append(
            {"step": md.step, "data": data_copy, "completed": md.completed}
        )

    return render_template(
        f"module_4/{step}.html",
        form_data=module_data.data,
        application_id=app_id,
        steps=STEPS,
        current_step=step,
        all_module_data=processed_module_data,
        existing_files=existing_files,
        application=application,
    )


@module_4.route(
    "/save_miscellaneous_and_declarations/<int:application_id>", methods=["POST"]
)
@login_required
def save_miscellaneous_and_declarations(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return (
            jsonify(
                {"status": "error", "message": "Unauthorized or already submitted"}
            ),
            403,
        )

    form_data = request.form.to_dict()
    file_fields = ["official_seal", "additional_documents"]

    module_data = ModuleData.query.filter_by(
        application_id=application_id,
        module_name="module_4",
        step="miscellaneous_and_declarations",
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=application_id,
            module_name="module_4",
            step="miscellaneous_and_declarations",
            data={},
        )
        db.session.add(module_data)

    # Capture old data for audit logging
    old_data = module_data.data.copy() if module_data.data else {}

    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = f"{application_id}_miscellaneous_and_declarations_{field}_{f.filename}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("Uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_4",
                    step="miscellaneous_and_declarations",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path,
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
                # Log file upload
                log_file_upload(
                    application_id,
                    "module_4",
                    "miscellaneous_and_declarations",
                    field,
                    f.filename,
                )
                logger.debug(f"Logged file upload: {field}: {f.filename}")
            form_data[field] = file_paths
        else:
            form_data[field] = old_data.get(field, [])
            logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

    for decl in [
        "coord_agreement",
        "cease_emission",
        "dst_compliance",
        "change_notification",
        "gov_control",
        "app_submission",
        "compliance_affirmation",
    ]:
        form_data[decl] = decl in request.form

    # Update module data
    module_data.data = form_data
    module_data.completed = True

    # Log field changes
    compare_form_data(
        old_data,
        form_data,
        application_id,
        "module_4",
        "miscellaneous_and_declarations",
    )
    logger.debug(
        f"Logged field changes for miscellaneous_and_declarations, application {application_id}"
    )

    try:
        db.session.commit()
        logger.debug(
            f"Saved ModuleData for miscellaneous_and_declarations: {module_data.data}"
        )
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        logger.error(
            f"Error saving ModuleData for miscellaneous_and_declarations: {str(e)}"
        )
        return jsonify({"status": "error", "message": str(e)}), 500


@module_4.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending" and not application.editable:
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_4"
    ).all()
    required_steps = STEPS
    completed_steps = {md.step for md in all_module_data if md.completed}
    if not set(required_steps).issubset(completed_steps):
        flash("Please complete all required steps.", "error")
        return redirect(
            url_for(
                "module_4.fill_step",
                step="miscellaneous_and_declarations",
                application_id=application_id,
            )
        )

    try:
        # Check for EditRequest and ApplicationAssignment
        edit_request = EditRequest.query.filter_by(
            application_id=application_id, status="Active"
        ).first()
        assignment = ApplicationAssignment.query.filter_by(
            application_id=application_id
        ).first()

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
                content=f"Application #{application_id} (Module 4) has been resubmitted after edits. Please review.",
                timestamp=datetime.utcnow(),
            )
            db.session.add(notification)

            if secondary_verifier_id:
                notification = Notification(
                    user_id=secondary_verifier_id,
                    content=f"Application #{application_id} (Module 4) has been resubmitted after edits. Please review.",
                    timestamp=datetime.utcnow(),
                )
                db.session.add(notification)

            flash("Application resubmitted successfully!", "success")
        else:
            # New submission
            application.status = "Submitted"
            application.editable = False
            flash("Application submitted for verification.", "success")

        db.session.commit()
        return redirect(
            url_for("module_4.fill_step", step="summary", application_id=application_id)
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(
            url_for(
                "module_4.fill_step",
                step="miscellaneous_and_declarations",
                application_id=application_id,
            )
        )


@module_4.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    if uploaded_file.application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    full_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath
    )
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    return send_file(
        full_path, as_attachment=True, download_name=uploaded_file.filename
    )
