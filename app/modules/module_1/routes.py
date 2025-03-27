# app/modules/module_1/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
import subprocess
import os

module_1 = Blueprint("module_1", __name__, url_prefix="/module_1", template_folder="templates")

STEPS = [
    "applicant_identity",
    "entity_details",
    "management_ownership",
    "financial_credentials",
    "operational_contact",
    "declarations_submission"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
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
    if application.user_id != current_user.id or (application.status != "Pending" and step != "summary"):
        return "Unauthorized or invalid application", 403

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_1", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_1", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_1", step=step).all()
    print(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST" and step != "declarations_submission":
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
                        relative_path = os.path.join("uploads", filename)
                        uploaded_file = UploadedFile(
                            application_id=app_id,
                            module_name="module_1",
                            step=step,
                            field_name=field,
                            filename=f.filename,
                            filepath=relative_path
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

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_1").all()
        processed_module_data = []
        for md in all_module_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc) for doc in value]
            processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})
        return render_template(
            "module_1/summary.html",
            all_module_data=processed_module_data,
            application_id=app_id,
            application=application
        )

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_1").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    template_map = {
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

@module_1.route("/save_declarations/<int:application_id>", methods=["POST"])
@login_required
def save_declarations(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return jsonify({"status": "error", "message": "Unauthorized or already submitted"}), 403

    form_data = request.form.to_dict()
    file_fields = ["security_clearance_doc", "authorization_submission_doc", "official_seal"]
    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = f"{application_id}_declarations_submission_{field}_{f.filename}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_1",
                    step="declarations_submission",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
            form_data[field] = file_paths
        else:
            form_data[field] = form_data.get(field, [])  # Retain existing if no new upload

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_1", step="declarations_submission").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_1", step="declarations_submission", data={})
        db.session.add(module_data)
    
    # Convert checkbox values to booleans
    for decl in ['compliance_laws', 'accuracy_info', 'criminal_declaration', 'financial_stability', 'change_notification']:
        form_data[decl] = decl in request.form

    module_data.data = form_data
    module_data.completed = True
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
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_1").all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(url_for("module_1.fill_step", step="declarations_submission", application_id=application_id))

    try:
        application.status = "Submitted"
        db.session.commit()
        flash("Application submitted successfully!", "success")
        return redirect(url_for("module_1.fill_step", step="summary", application_id=application_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for("module_1.fill_step", step="declarations_submission", application_id=application_id))

@module_1.route("/download_file/<int:file_id>")
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

@module_1.route("/download_pdf/<int:application_id>")
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Submitted":
        print(f"Debug: current_user.id = {current_user.id}, application.user_id = {application.user_id}, status = {application.status}")
        abort(403, "Unauthorized or invalid application")

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_1").all()
    uploaded_files = UploadedFile.query.filter_by(application_id=application_id, module_name="module_1").all()

    typst_content = """
    #set page(margin: 1in)
    #set text(font: "Arial", size: 12pt)
    #show heading: set text(size: 16pt, weight: "bold")

    = Application {{ application_id }} - Module 1 Summary
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

    typst_file = f"temp_{application_id}.typ"
    with open(typst_file, "w", encoding="utf-8") as f:
        f.write(typst_content.replace("{{ application_id }}", str(application_id)))

    base_pdf = f"temp_{application_id}.pdf"
    try:
        subprocess.run(["typst", "compile", typst_file, base_pdf], check=True, shell=True)
    except subprocess.CalledProcessError as e:
        os.remove(typst_file)
        abort(500, f"Typst compilation failed: {e}")

    pdf_files = [base_pdf]
    for uf in uploaded_files:
        full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", uf.filepath))
        if os.path.exists(full_path) and full_path.lower().endswith(".pdf"):
            pdf_files.append(full_path.replace("/", "\\"))
        else:
            print(f"Skipping {full_path}: Not found or not a PDF")

    final_pdf = f"final_{application_id}.pdf"
    try:
        cmd = ["pdftk"] + [f'"{pdf}"' for pdf in pdf_files] + ["cat", "output", f'"{final_pdf}"']
        subprocess.run(cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        os.remove(typst_file)
        os.remove(base_pdf)
        abort(500, f"PDF merging failed: {e}")

    os.remove(typst_file)
    os.remove(base_pdf)

    response = send_file(final_pdf, as_attachment=True, download_name=f"Module_1_Application_{application_id}.pdf")
    os.remove(final_pdf)
    return response

@module_1.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("module_1.fill_step", step=STEPS[0], application_id=application.id))
    return render_template("module_1/start_application.html")