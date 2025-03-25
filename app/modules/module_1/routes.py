# app/modules/module_1/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
import os
from PIL import Image as PILImage

module_1 = Blueprint("module_1", __name__, url_prefix="/module_1", template_folder="templates")

STEPS = [
    "applicant_identity",
    "entity_details",
    "management_ownership",
    "financial_credentials",
    "operational_contact",
    "declarations_submission",
    "summary"
]

# Define UPLOAD_FOLDER as a relative path from the app root
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_1.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS:
        return "Invalid step", 404

    app_id = request.args.get("application_id")
    if not app_id:
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (application.status != "Pending" and step != "summary"):
        return "Unauthorized or invalid application", 403

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_1", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_1", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_1", step=step).all()
    print(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")  # Debugging

    if request.method == "POST":
        form_data = request.form.to_dict()

        file_fields = {
            "entity_details": ["recognition_certificate"],
            "management_ownership": ["charter_document"],
            "financial_credentials": ["annual_report", "income_tax_returns", "gst_returns", "fdi_approval"],
            "operational_contact": ["special_approvals_docs"],
            "declarations_submission": ["security_clearance_doc", "authorization_submission_doc", "official_seal"]
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
                        # Store relative path in the database
                        relative_path = os.path.join("uploads", filename)
                        uploaded_file = UploadedFile(
                            application_id=app_id,
                            module_name="module_1",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path  # Store relative path
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                    form_data[field] = file_paths
                    print(f"Uploaded {field}: {[f.filename for f in files]} to {file_path}")
                else:
                    form_data[field] = module_data.data.get(field, [])
                    print(f"No new upload for {field}, retaining: {form_data[field]}")

        module_data.data = form_data
        module_data.completed = True
        db.session.commit()

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(url_for("module_1.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_1.fill_step", step="summary", application_id=app_id))

    if step == "summary" and not module_data.completed:
        module_data.completed = True
        db.session.commit()

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_1").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    template_map = {
        "summary": "module_1/summary.html",
        "declarations_submission": "module_1/declarations_submission.html"
    }
    return render_template(
        template_map.get(step, f"module_1/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

@module_1.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    application = Application.query.get_or_404(uploaded_file.application_id)
    if application.user_id != current_user.id:
        return "Unauthorized", 403
    # Reconstruct full path from relative path
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath)
    print(f"Attempting to download: {full_path}")  # Debugging
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    return send_file(full_path, as_attachment=True, download_name=uploaded_file.filename)

@module_1.route("/submit_application/<application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_1").all()
    required_steps = [s for s in STEPS if s != "summary"]
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(url_for("module_1.fill_step", step="summary", application_id=application_id))

    try:
        application.status = "Submitted"
        db.session.commit()
        flash("Application submitted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for("module_1.fill_step", step="summary", application_id=application_id))

    return redirect(url_for("applicant.home"))

@module_1.route("/download_pdf/<int:application_id>")
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Submitted":
        return "Unauthorized or invalid application", 403

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Information and Credentials of the Applicant", styles["Title"]))
    story.append(Spacer(1, 12))

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_1").all()
    for md in module_data:
        data = md.data
        story.append(Paragraph(f"<b>{md.step.replace('_', ' ').title()}</b>", styles["Heading2"]))
        for key, value in data.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                story.append(Paragraph(f"{key.replace('_', ' ').title()}:", styles["Normal"]))
                for doc_path in value:
                    story.append(Paragraph(f"- {os.path.basename(doc_path)}", styles["Normal"]))
            else:
                story.append(Paragraph(f"{key.replace('_', ' ').title()}: {value}", styles["Normal"]))
        story.append(Spacer(1, 12))

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"module_1_application_{application_id}.pdf", mimetype="application/pdf")

@module_1.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, module_name="module_1", status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("module_1.fill_step", step=STEPS[0], application_id=application.id))
    return render_template("module_1/start_application.html")