# app/modules/module_4/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, abort
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
import os
import logging
import subprocess


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_4 = Blueprint("module_4", __name__, url_prefix="/module_4", template_folder="templates")

STEPS = [
    "extension_and_orbit",
    "satellite_details",
    "configuration_and_safety",
    "manufacturing_and_procurement",
    "payload_details",
    "ground_segment",
    "itu_and_regulatory",
    "launch_and_insurance",
    "miscellaneous_and_declarations"
]  # Removed "summary"

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
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
    if application.user_id != current_user.id or (application.status != "Pending" and step != "summary"):
        flash("Unauthorized access or application not editable.", "error")
        return redirect(url_for("applicant.home"))

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_4", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_4", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_4", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[(f.id, f.filename) for f in existing_files]}")

    if request.method == "POST" and step != "miscellaneous_and_declarations":
        form_data = request.form.to_dict()
        file_fields = {
            "extension_and_orbit": [],
            "satellite_details": [],
            "configuration_and_safety": [],
            "manufacturing_and_procurement": [],
            "payload_details": [],
            "ground_segment": [],
            "itu_and_regulatory": [],
            "launch_and_insurance": [],
            "miscellaneous_and_declarations": ["official_seal"]  # Assuming a seal upload here; adjust as needed
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
                            module_name="module_4",
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

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(url_for("module_4.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_4.fill_step", step="summary", application_id=app_id))

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_4").all()
        processed_module_data = []
        for md in all_module_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc) for doc in value]
            processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})
        return render_template(
            "module_4/summary.html",
            all_module_data=processed_module_data,
            application_id=app_id,
            application=application
        )

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_4").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    return render_template(
        f"module_4/{step}.html",
        form_data=module_data.data,
        application_id=app_id,
        steps=STEPS,
        current_step=step,
        all_module_data=processed_module_data,
        existing_files=existing_files,
        application=application
    )

@module_4.route("/save_miscellaneous_and_declarations/<int:application_id>", methods=["POST"])
@login_required
def save_miscellaneous_and_declarations(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return jsonify({"status": "error", "message": "Unauthorized or already submitted"}), 403

    form_data = request.form.to_dict()
    file_fields = ["official_seal"]  # Adjust if Module 4 has specific uploads
    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = f"{application_id}_miscellaneous_and_declarations_{field}_{f.filename}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_4",
                    step="miscellaneous_and_declarations",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
            form_data[field] = file_paths
        else:
            form_data[field] = form_data.get(field, [])

    for decl in ['coord_agreement', 'cease_emission', 'dst_compliance', 'change_notification', 'gov_control', 'app_submission', 'compliance_affirmation']:
        form_data[decl] = decl in request.form

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_4", step="miscellaneous_and_declarations").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_4", step="miscellaneous_and_declarations", data={})
        db.session.add(module_data)

    module_data.data = form_data
    module_data.completed = True
    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_4.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending":
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_4").all()
    required_steps = STEPS
    completed_steps = {md.step for md in all_module_data if md.completed}
    if not set(required_steps).issubset(completed_steps):
        flash("Please complete all required steps.", "error")
        return redirect(url_for("module_4.fill_step", step="miscellaneous_and_declarations", application_id=application_id))

    application.status = "Submitted"
    db.session.commit()
    flash("Application submitted successfully!", "success")
    return redirect(url_for("module_4.fill_step", step="summary", application_id=application_id))

@module_4.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    if uploaded_file.application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath)
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    return send_file(full_path, as_attachment=True, download_name=uploaded_file.filename)

@module_4.route("/download_pdf/<int:application_id>")
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Submitted":
        abort(403, "Unauthorized or invalid application")

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_4").all()
    uploaded_files = UploadedFile.query.filter_by(application_id=application_id, module_name="module_4").all()

    typst_content = """
    #set page(margin: 1in)
    #set text(font: "Arial", size: 12pt)
    #show heading: set text(size: 16pt, weight: "bold")

    = Application {{ application_id }} - Module 4 Summary
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

    response = send_file(final_pdf, as_attachment=True, download_name=f"Module_4_Application_{application_id}.pdf")
    os.remove(final_pdf)
    return response