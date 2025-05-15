from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_file,
    flash,
    abort,
    current_app,
)
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, ApplicationAssignment, EditRequest, Notification
from app.utils import compare_form_data, log_file_upload
from config import Config
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_10 = Blueprint(
    "module_10", __name__, url_prefix="/module_10", template_folder="templates"
)

STEPS = [
    "general_info",
    "space_object_part1",
    "space_object_part2",
    "undertaking",
    "annexure_a",
    "annexure_1_security",
    "annexure_2_ssa_satellite",
    "annexure_3_ssa_launch",
    "annexure_4_hosted_payload",
]

UPLOAD_FOLDER = Config.UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_10.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS and step != "summary":
        logger.error(f"Invalid step requested: {step}. Valid steps are: {STEPS}")
        flash("Invalid step.", "error")
        return redirect(url_for("applicant.home"))

    app_id = request.args.get("application_id")
    if not app_id:
        logger.warning("No application_id provided, redirecting to dashboard")
        flash("Application ID is required.", "error")
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (
        application.status != "Pending"
        and not application.editable
        and step != "summary"
    ):
        logger.warning(f"Unauthorized access for user {current_user.id}, app {app_id}")
        flash("Unauthorized or invalid application.", "error")
        return redirect(url_for("applicant.home"))

    # Ensure ModuleData exists for the current step
    module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_10", step=step
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=app_id, module_name="module_10", step=step, data={}
        )
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(
        application_id=app_id, module_name="module_10", step=step
    ).all()
    logger.debug(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST":
        form_data = request.form.to_dict()

        # Capture old data for audit logging
        old_data = module_data.data.copy() if module_data.data else {}

        if step == "undertaking":
            # Handle checkbox fields
            for decl in [
                "authorization_affirmation",
                "compliance_laws",
                "dst_guidelines",
                "records_submission",
                "data_guidelines",
                "national_security_data",
                "registration_termination",
                "submission_authorization",
                "conformance_laws",
            ]:
                form_data[decl] = decl in request.form
        else:
            # Handle file uploads for other steps
            file_fields = {
                "space_object_part2": ["consent_copy"],
                "annexure_a": ["kml_file"],
                "annexure_2_ssa_satellite": ["safety_report", "ground_segment_file"],
                "annexure_3_ssa_launch": ["hazardous_materials_file", "ground_station_file", "attachments"],
                "annexure_4_hosted_payload": [
                    "indian_agreement_copy",
                    "indian_operation_mechanism_file",
                    "non_indian_authorization_copy",
                    "non_indian_agreement_copy",
                    "non_indian_operation_mechanism_file",
                ],
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
                            if not os.path.exists(file_path):
                                logger.error(f"Failed to save file: {file_path}")
                                flash("Error saving file. Please try again.", "error")
                                return redirect(url_for("module_10.fill_step", step=step, application_id=app_id))
                            relative_path = os.path.join("Uploads", filename)
                            uploaded_file = UploadedFile(
                                application_id=app_id,
                                module_name="module_10",
                                step=step,
                                field_name=field,
                                filename=f.filename,
                                filepath=relative_path,
                            )
                            db.session.add(uploaded_file)
                            file_paths.append(relative_path)
                            # Log file upload
                            log_file_upload(app_id, "module_10", step, field, f.filename)
                            logger.debug(f"Logged file upload: {field}: {f.filename}")
                        form_data[field] = file_paths
                    else:
                        form_data[field] = old_data.get(field, [])
                        logger.debug(f"No new upload for {field}, retaining: {form_data[field]}")

            # Handle dynamic fields for other steps
            if step == "space_object_part1":
                satellite_names = request.form.getlist("satellite_names")
                form_data["satellite_names"] = [name for name in satellite_names if name]
                form_data["payload_details"] = request.form.get("payload_details", "")
                form_data["owner_name"] = request.form.get("owner_name", "")
                form_data["contact_person"] = request.form.get("contact_person", "")
                form_data["owner_email"] = request.form.get("owner_email", "")
                form_data["owner_address"] = request.form.get("owner_address", "")
            elif step == "annexure_a":
                dissemination_entries = []
                for i in range(len(request.form.getlist("end_user_type"))):
                    entry = {
                        "end_user_type": request.form.getlist("end_user_type")[i],
                        "country_of_origin": request.form.getlist("country_of_origin")[i],
                        "entity_type": request.form.getlist("entity_type")[i],
                        "legal_name": request.form.getlist("legal_name")[i],
                        "brand_trade_name": request.form.getlist("brand_trade_name")[i],
                        "address": request.form.getlist("address")[i],
                        "project_name": request.form.getlist("project_name")[i],
                        "satellite_name": request.form.getlist("satellite_name")[i],
                        "kml_file": form_data.get("kml_file", []),
                        "area_sq_km": request.form.getlist("area_sq_km")[i],
                        "data_provision_type": request.form.getlist("data_provision_type")[i],
                        "acquisition_date": request.form.getlist("acquisition_date")[i],
                        "acquisition_time": request.form.getlist("acquisition_time")[i],
                        "orbit_path_row": request.form.getlist("orbit_path_row")[i],
                        "payload_sensor": request.form.getlist("payload_sensor")[i],
                        "dissemination_date": request.form.getlist("dissemination_date")[i],
                        "dissemination_time": request.form.getlist("dissemination_time")[i],
                    }
                    dissemination_entries.append(entry)
                form_data["dissemination_entries"] = dissemination_entries
            elif step == "annexure_1_security":
                directors = []
                for i in range(len(request.form.getlist("director_full_name"))):
                    directors.append({
                        "full_name": request.form.getlist("director_full_name")[i],
                        "position_held": request.form.getlist("director_position_held")[i],
                        "date_of_birth": request.form.getlist("director_date_of_birth")[i],
                        "parentage": request.form.getlist("director_parentage")[i],
                        "present_address": request.form.getlist("director_present_address")[i],
                        "permanent_address": request.form.getlist("director_permanent_address")[i],
                        "nationality": request.form.getlist("director_nationality")[i],
                        "passport_no": request.form.getlist("director_passport_no")[i],
                        "contact_details": request.form.getlist("director_contact_details")[i],
                    })
                form_data["directors"] = directors
                shareholders = []
                for i in range(len(request.form.getlist("shareholder_full_name"))):
                    shareholders.append({
                        "full_name": request.form.getlist("shareholder_full_name")[i],
                        "parentage": request.form.getlist("shareholder_parentage")[i],
                        "date_of_birth": request.form.getlist("shareholder_date_of_birth")[i],
                        "permanent_address": request.form.getlist("shareholder_permanent_address")[i],
                        "present_address": request.form.getlist("shareholder_present_address")[i],
                        "position_held": request.form.getlist("shareholder_position_held")[i],
                        "nationality": request.form.getlist("shareholder_nationality")[i],
                        "share_percentage": request.form.getlist("shareholder_share_percentage")[i],
                    })
                form_data["shareholders"] = shareholders
                form_data["owners_directors"] = request.form.getlist("owners_directors")
            elif step == "annexure_4_hosted_payload":
                form_data["indian_payload_names"] = request.form.getlist("indian_payload_names")
                form_data["non_indian_payload_names"] = request.form.getlist("non_indian_payload_names")

        # Update module data
        module_data.data = form_data
        module_data.completed = True

        # Log field changes
        compare_form_data(old_data, form_data, app_id, "module_10", step)
        logger.debug(f"Logged field changes for step {step}, application {app_id}")

        db.session.commit()

        # Check if all steps are completed
        all_completed = True
        for s in STEPS:
            step_data = ModuleData.query.filter_by(
                application_id=app_id, module_name="module_10", step=s
            ).first()
            if not step_data or not step_data.completed:
                all_completed = False
                break

        if all_completed:
            try:
                # Check for EditRequest and ApplicationAssignment
                edit_request = EditRequest.query.filter_by(application_id=app_id, status="Active").first()
                assignment = ApplicationAssignment.query.filter_by(application_id=app_id).first()

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
                        content=f"Application #{app_id} (Module 10) has been resubmitted after edits. Please review.",
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(notification)

                    if secondary_verifier_id:
                        notification = Notification(
                            user_id=secondary_verifier_id,
                            content=f"Application #{app_id} (Module 10) has been resubmitted after edits. Please review.",
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
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error submitting application {app_id} in fill_step: {str(e)}")
                flash(f"Error submitting application: {str(e)}", "error")
                return redirect(url_for("module_10.fill_step", step="undertaking", application_id=app_id))

        if step == STEPS[-1]:
            return redirect(
                url_for("module_10.fill_step", step="summary", application_id=app_id)
            )
        next_step_idx = STEPS.index(step) + 1
        return redirect(
            url_for(
                "module_10.fill_step",
                step=STEPS[next_step_idx],
                application_id=app_id,
            )
        )

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(
            application_id=app_id, module_name="module_10"
        ).all()
        all_uploaded_files = UploadedFile.query.filter_by(
            application_id=app_id, module_name="module_10"
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
            "module_10/summary.html",
            all_module_data=processed_module_data,
            all_uploaded_files=all_uploaded_files,
            application_id=app_id,
            application=application,
            existing_files=existing_files,
        )

    all_module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_10"
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

    template_map = {
        "general_info": "module_10/general_info_module10.html",
        "space_object_part1": "module_10/space_object_part1.html",
        "space_object_part2": "module_10/space_object_part2.html",
        "undertaking": "module_10/undertaking_module10.html",
        "annexure_a": "module_10/annexure_a_module10.html",
        "annexure_1_security": "module_10/annexure_1_security.html",
        "annexure_2_ssa_satellite": "module_10/annexure_2_ssa_satellite.html",
        "annexure_3_ssa_launch": "module_10/annexure_3_ssa_launch.html",
        "annexure_4_hosted_payload": "module_10/annexure_4_hosted_payload.html",
    }
    return render_template(
        template_map.get(step, f"module_10/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files,
    )

@module_10.route("/save_undertaking/<int:application_id>", methods=["POST"])
@login_required
def save_undertaking(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        logger.warning(f"Unauthorized access for user {current_user.id}, app {application_id}")
        return (
            jsonify(
                {"status": "error", "message": "Unauthorized or already submitted"}
            ),
            403,
        )

    form_data = request.form.to_dict()
    for decl in [
        "authorization_affirmation",
        "compliance_laws",
        "dst_guidelines",
        "records_submission",
        "data_guidelines",
        "national_security_data",
        "registration_termination",
        "submission_authorization",
        "conformance_laws",
    ]:
        form_data[decl] = decl in request.form

    module_data = ModuleData.query.filter_by(
        application_id=application_id,
        module_name="module_10",
        step="undertaking",
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=application_id,
            module_name="module_10",
            step="undertaking",
            data={},
        )
        db.session.add(module_data)

    # Capture old data for audit logging
    old_data = module_data.data.copy() if module_data.data else {}

    # Update module data
    module_data.data = form_data
    module_data.completed = True

    # Log field changes
    compare_form_data(old_data, form_data, application_id, "module_10", "undertaking")
    logger.debug(f"Logged field changes for undertaking, application {application_id}")

    try:
        db.session.commit()
        logger.debug(f"Undertaking saved for application {application_id}")
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving undertaking for application {application_id}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@module_10.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        logger.warning(f"Unauthorized access for user {current_user.id}, app {application_id}")
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending" and not application.editable:
        logger.warning(f"Application {application_id} already submitted")
        flash("Application already submitted.", "warning")
        return redirect(url_for("module_10.fill_step", step="summary", application_id=application_id))

    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_10"
    ).all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(
        step in completed_steps for step in required_steps
    ):
        logger.warning(f"Application {application_id} has incomplete steps: {completed_steps}")
        flash("Please complete all required steps before submitting.", "error")
        return redirect(
            url_for(
                "module_10.fill_step",
                step="undertaking",
                application_id=application_id,
            )
        )

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
                content=f"Application #{application_id} (Module 10) has been resubmitted after edits. Please review.",
                timestamp=datetime.utcnow()
            )
            db.session.add(notification)

            if secondary_verifier_id:
                notification = Notification(
                    user_id=secondary_verifier_id,
                    content=f"Application #{application_id} (Module 10) has been resubmitted after edits. Please review.",
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
        logger.debug(f"Application {application_id} submitted successfully")
        return redirect(
            url_for("module_10.fill_step", step="summary", application_id=application_id)
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting application {application_id}: {str(e)}")
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(
            url_for(
                "module_10.fill_step",
                step="undertaking",
                application_id=application_id,
            )
        )

@module_10.route("/download_file/<int:file_id>", methods=["GET"])
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    application = Application.query.get_or_404(uploaded_file.application_id)
    assignment = ApplicationAssignment.query.filter_by(
        application_id=application.id
    ).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend(
            [assignment.primary_verifier_id, assignment.secondary_verifier_id]
        )

    if current_user.id not in allowed_users:
        logger.warning(f"Unauthorized file access by user {current_user.id}, file {file_id}")
        flash("Unauthorized.", "error")
        return redirect(url_for("applicant.home"))

    file_path = uploaded_file.filepath
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        flash("File not found.", "error")
        return redirect(url_for("applicant.home"))

    logger.debug(f"Downloading file {uploaded_file.filename} for application {application.id}")
    return send_file(
        file_path,
        as_attachment=True,
        download_name=uploaded_file.filename,
    )

@module_10.route("/progress/<int:application_id>", methods=["GET"])
@login_required
def progress(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        logger.warning(f"Unauthorized access for user {current_user.id}, app {application_id}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_10"
    ).all()
    progress = [
        {"step": md.step, "completed": md.completed}
        for md in all_module_data
        if md.step in STEPS
    ]
    completed_steps = sum(1 for p in progress if p["completed"])
    percentage = (completed_steps / len(STEPS)) * 100 if STEPS else 0

    logger.debug(f"Progress for application {application_id}: {percentage}%")
    return jsonify(
        {
            "status": "success",
            "progress": progress,
            "percentage": round(percentage, 2),
            "application_status": application.status,
        }
    )

@module_10.route("/create_application", methods=["POST"])
@login_required
def create_application():
    try:
        application = Application(
            user_id=current_user.id,
            module_name="module_10",
            status="Pending",
            editable=True,
        )
        db.session.add(application)
        db.session.commit()

        for step in STEPS:
            module_data = ModuleData(
                application_id=application.id,
                module_name="module_10",
                step=step,
                data={},
                completed=False,
            )
            db.session.add(module_data)
        db.session.commit()

        logger.debug(f"New application created: {application.id}")
        return jsonify(
            {
                "status": "success",
                "application_id": application.id,
                "redirect": url_for(
                    "module_10.fill_step",
                    step="general_info",
                    application_id=application.id,
                ),
            }
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating application: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500