# app/modules/module_5/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, abort
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
import os
import logging
import subprocess


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_5 = Blueprint("module_5", __name__, url_prefix="/module_5", template_folder="templates")

# Define the steps specific to Module 5
STEPS = [
    "host_space_object_details",
    "hosted_payload_details",
    "host_space_object_ground_segment_details",
    "hosted_payload_ground_segment_details",
    "itu_filing_details",
    "information_on_space_situational_awareness",
    "launch_details",
    "regulatory_license_details_and_requirement",
    "miscellaneous",
    "undertaking_declaration"
]

# File upload directory setup
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_5.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    # Validate the requested step
    if step not in STEPS and step != "summary":
        logger.error(f"Invalid step requested: {step}")
        return "Invalid step", 404

    # Get application ID from query params
    app_id = request.args.get("application_id")
    if not app_id:
        logger.warning("No application_id provided, redirecting to dashboard")
        return redirect(url_for("applicant.home"))

    # Fetch the application and validate user access
    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (application.status != "Pending" and step != "summary"):
        flash("Unauthorized access or application not editable.", "error")
        return redirect(url_for("applicant.home"))

    # Fetch or create module data for the current step
    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_5", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_5", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    # Fetch any existing uploaded files for this step
    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_5", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[(f.id, f.filename) for f in existing_files]}")

    # Handle form submission (POST request)
    if request.method == "POST" and step != "undertaking_declaration":
        form_data = request.form.to_dict()
        # Define file upload fields for each step
        file_fields = {
            "host_space_object_details": ["authorization_copy", "agreement_copy", "schematic_diagram"],
            "hosted_payload_details": [],
            "host_space_object_ground_segment_details": [],
            "hosted_payload_ground_segment_details": ["mcc_inspace_authorization", "eo_ground_station_inspace_authorization"],
            "itu_filing_details": ["foreign_admin_authorization"],
            "information_on_space_situational_awareness": ["safety_data_sheet"],
            "launch_details": [],
            "regulatory_license_details_and_requirement": ["dot_license_copies"],
            "miscellaneous": [],
            "undertaking_declaration": ["official_signature"]  # Updated from signature_file to official_signature
        }

        # Handle file uploads for the current step
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
                            module_name="module_5",
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

        # Save the form data and mark the step as completed
        module_data.data = form_data
        module_data.completed = True
        db.session.commit()

        # Redirect to the next step or summary
        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(url_for("module_5.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_5.fill_step", step="summary", application_id=app_id))

    # Render the summary page if the step is "summary"
    if step == "summary":
        all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_5").all()
        processed_module_data = []
        for md in all_module_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc)     for doc in value]
            processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})
        return render_template(
            "module_5/summary.html",
            all_module_data=processed_module_data,
            application_id=app_id,
            application=application
        )

    # Render the form page for the current step
    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_5").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    return render_template(
        f"module_5/{step}.html",
        form_data=module_data.data,
        application_id=app_id,
        steps=STEPS,
        current_step=step,
        all_module_data=processed_module_data,
        existing_files=existing_files,
        application=application
    )

@module_5.route("/save_undertaking_declaration/<int:application_id>", methods=["POST"])
@login_required
def save_undertaking_declaration(application_id):
    # Validate user access and application status
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return jsonify({"status": "error", "message": "Unauthorized or already submitted"}), 403

    form_data = request.form.to_dict()
    file_fields = ["official_signature"]
    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = f"{application_id}_undertaking_declaration_{field}_{f.filename}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_5",
                    step="undertaking_declaration",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
            form_data[field] = file_paths
        else:
            form_data[field] = form_data.get(field, [])

    # Handle declarations
    for decl in ['declaration_g', 'declaration_h', 'declaration_f', 'declaration_i', 'declaration_j', 'declaration_k', 'declaration_l']:
        form_data[decl] = decl in request.form

    # Save the data for the undertaking/declaration step
    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_5", step="undertaking_declaration").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_5", step="undertaking_declaration", data={})
        db.session.add(module_data)

    module_data.data = form_data
    module_data.completed = True
    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_5.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    # Validate user access and application status
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    # Check if all required steps are completed
    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_5").all()
    required_steps = STEPS
    completed_steps = {md.step for md in all_module_data if md.completed}
    if not set(required_steps).issubset(completed_steps):
        flash("Please complete all required steps.", "error")
        return redirect(url_for("module_5.fill_step", step="undertaking_declaration", application_id=application_id))

    # Update application status to "Submitted"
    application.status = "Submitted"
    db.session.commit()
    flash("Application submitted successfully!", "success")
    return redirect(url_for("module_5.fill_step", step="summary", application_id=application_id))

@module_5.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    # Allow downloading of uploaded files
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    if uploaded_file.application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath)
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    return send_file(full_path, as_attachment=True, download_name=uploaded_file.filename)

@module_5.route("/download_pdf/<int:application_id>")
@login_required
def download_pdf(application_id):
    # Validate user access and application status
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Submitted":
        abort(403, "Unauthorized or invalid application")

    # Fetch module data and uploaded files
    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_5").all()
    uploaded_files = UploadedFile.query.filter_by(application_id=application_id, module_name="module_5").all()

    # Generate Typst content for PDF
    typst_content = """
    #set page(margin: 1in)
    #set text(font: "Arial", size: 12pt)
    #show heading: set text(size: 16pt, weight: "bold")

    = Application {{ application_id }} - Module 5 Summary
    #outline(title: "Table of Contents", indent: true)

    """
    for md in module_data:
        step_title = md.step.replace('_', ' ').title()
        typst_content += f"\n== {step_title}\n"
        for key, value in md.data.items():
            key_title = key.replace('_', ' ').title()
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                typst_content += f"- *{key_title}*: "
                if value:
                    typst_content += ", ".join([f"[{os.path.basename(v)}](#appendix)" for v in value])
                else:
                    typst_content += "None uploaded"
                typst_content += "\n"
            else:
                typst_content += f"- *{key_title}*: {value}\n"

    typst_content += "\n#pagebreak()\n= Appendix: Uploaded Files\n"
    for i, uf in enumerate(uploaded_files, 1):
        typst_content += f"[#set anchor({uf.filename})]\n- {uf.field_name.replace('_', ' ').title()}: {uf.filename} (Page {i})\n"

    # Write Typst content to a temporary file
    typst_file = f"temp_{application_id}.typ"
    with open(typst_file, "w", encoding="utf-8") as f:
        f.write(typst_content.replace("{{ application_id }}", str(application_id)))

    # Compile Typst to PDF
    base_pdf = f"temp_{application_id}.pdf"
    try:
        subprocess.run(["typst", "compile", typst_file, base_pdf], check=True, shell=True)
    except subprocess.CalledProcessError as e:
        os.remove(typst_file)
        abort(500, f"Typst compilation failed: {e}")

    # Collect PDFs for merging
    pdf_files = [base_pdf]
    for uf in uploaded_files:
        full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", uf.filepath))
        if os.path.exists(full_path) and full_path.lower().endswith(".pdf"):
            pdf_files.append(full_path.replace("/", "\\"))
        else:
            print(f"Skipping {full_path}: Not found or not a PDF")

    # Merge PDFs using pdftk
    final_pdf = f"final_{application_id}.pdf"
    try:
        cmd = ["pdftk"] + [f'"{pdf}"' for pdf in pdf_files] + ["cat", "output", f'"{final_pdf}"']
        subprocess.run(cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        os.remove(typst_file)
        os.remove(base_pdf)
        abort(500, f"PDF merging failed: {e}")

    # Clean up temporary files
    os.remove(typst_file)
    os.remove(base_pdf)

    # Send the final PDF to the user
    response = send_file(final_pdf, as_attachment=True, download_name=f"Module_5_Application_{application_id}.pdf")
    os.remove(final_pdf)
    return response