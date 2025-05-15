from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_file,
    flash,
)
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, ApplicationAssignment, EditRequest, Notification
from app.utils import compare_form_data, log_file_upload
from datetime import datetime
import os
import re
from docx2pdf import convert
import tempfile

module_1 = Blueprint(
    "module_1", __name__, url_prefix="/module_1", template_folder="templates"
)

logo_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static/images/IN-SPACe_Logo.png"
)

STEPS = [
    "applicant_identity",
    "entity_details",
    "management_ownership",
    "financial_credentials",
    "operational_contact",
    "declarations_submission",
]

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "uploads"
)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_1.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS and step != "summary":
        return "Invalid step", 404

    app_id = request.args.get("application_id")
    if not app_id:
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (
        application.status != "Pending"
        and not application.editable
        and step != "summary"
    ):
        return "Unauthorized or invalid application", 403

    module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_1", step=step
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=app_id, module_name="module_1", step=step, data={}
        )
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(
        application_id=app_id, module_name="module_1", step=step
    ).all()

    if request.method == "POST" and step != "declarations_submission":
        form_data = request.form.to_dict()
        file_fields = {
            "entity_details": ["recognition_certificate"],
            "management_ownership": ["charter_document"],
            "financial_credentials": [
                "annual_report",
                "income_tax_returns",
                "gst_returns",
                "fdi_approval",
            ],
            "operational_contact": ["special_approvals_docs"],
            "declarations_submission": [
                "security_clearance_doc",
                "authorization_submission_doc",
                "official_seal",
            ],
        }

        # Server-side validation for applicant_identity
        if step == "applicant_identity":
            legal_name = form_data.get("legal_name", "").strip()
            if not re.match(r"^[a-zA-Z\s\-\'&]+$", legal_name):
                flash("Legal Name must contain only letters, spaces, hyphens, apostrophes, or ampersands.", "error")
                return render_template(
                    f"module_1/{step}.html",
                    form_data=module_data.data,
                    application_id=app_id,
                    current_step=step,
                    steps=STEPS,
                    all_module_data=[
                        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
                        for md in ModuleData.query.filter_by(application_id=app_id, module_name="module_1").all()
                    ],
                    application=application,
                    existing_files=existing_files,
                )

        # Get old data for comparison
        old_data = module_data.data.copy() if module_data.data else {}

        # Handle file uploads and log them
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
                            module_name="module_1",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path,
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                        # Log file upload
                        log_file_upload(app_id, "module_1", step, field, f.filename)
                    form_data[field] = file_paths
                else:
                    form_data[field] = old_data.get(field, [])

        # Update module data
        module_data.data = form_data
        module_data.completed = True

        # Log field changes
        compare_form_data(old_data, form_data, app_id, "module_1", step)

        db.session.commit()

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(
                url_for(
                    "module_1.fill_step",
                    step=STEPS[next_step_idx],
                    application_id=app_id,
                )
            )
        return redirect(
            url_for("module_1.fill_step", step="summary", application_id=app_id)
        )

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(
            application_id=app_id, module_name="module_1"
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
            "module_1/summary.html",
            all_module_data=processed_module_data,
            application_id=app_id,
            application=application,
        )

    all_module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_1"
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

    template_map = {"declarations_submission": "module_1/declarations_submission.html"}
    return render_template(
        template_map.get(step, f"module_1/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files,
    )

@module_1.route("/save_declarations/<int:application_id>", methods=["POST"])
@login_required
def save_declarations(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return (
            jsonify(
                {"status": "error", "message": "Unauthorized or already submitted"}
            ),
            403,
        )

    form_data = request.form.to_dict()
    file_fields = [
        "security_clearance_doc",
        "authorization_submission_doc",
        "official_seal",
    ]

    module_data = ModuleData.query.filter_by(
        application_id=application_id,
        module_name="module_1",
        step="declarations_submission",
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=application_id,
            module_name="module_1",
            step="declarations_submission",
            data={},
        )
        db.session.add(module_data)

    # Get old data for comparison
    old_data = module_data.data.copy() if module_data.data else {}

    # Handle file uploads
    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = (
                    f"{application_id}_declarations_submission_{field}_{f.filename}"
                )
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_1",
                    step="declarations_submission",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path,
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
                # Log file upload
                log_file_upload(application_id, "module_1", "declarations_submission", field, f.filename)
            form_data[field] = file_paths
        else:
            form_data[field] = old_data.get(field, [])

    # Update declarations
    for decl in [
        "compliance_laws",
        "accuracy_info",
        "criminal_declaration",
        "financial_stability",
        "change_notification",
    ]:
        form_data[decl] = decl in request.form

    # Update module data
    module_data.data = form_data
    module_data.completed = True

    # Log field changes
    compare_form_data(old_data, form_data, application_id, "module_1", "declarations_submission")

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_1.route("/submit_application/<int:application_id>", methods=["POST"])
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
        application_id=application_id, module_name="module_1"
    ).all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(
        step in completed_steps for step in required_steps
    ):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(
            url_for(
                "module_1.fill_step",
                step="declarations_submission",
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
                content=f"Application #{application_id} (Module 1) has been resubmitted after edits. Please review.",
                timestamp=datetime.utcnow()
            )
            db.session.add(notification)

            if secondary_verifier_id:
                notification = Notification(
                    user_id=secondary_verifier_id,
                    content=f"Application #{application_id} (Module 1) has been resubmitted after edits. Please review.",
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
        return redirect(
            url_for("module_1.fill_step", step="summary", application_id=application_id)
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(
            url_for(
                "module_1.fill_step",
                step="declarations_submission",
                application_id=application_id,
            )
        )

@module_1.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(
            url_for("module_1.fill_step", step=STEPS[0], application_id=application.id)
        )
    return render_template("module_1/start_application.html")

@module_1.route("/download_file/<int:file_id>")
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
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))

    full_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath
    )
    if not os.path.exists(full_path):
        flash(f"File not found: {uploaded_file.filename}", "error")
        return redirect(url_for("applicant.home"))

    return send_file(
        full_path, as_attachment=True, download_name=uploaded_file.filename
    )