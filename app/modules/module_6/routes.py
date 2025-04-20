# app/modules/module_6/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, abort
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile
import os
import logging
import subprocess

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

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
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
    if application.user_id != current_user.id or (application.status != "Pending" and step != "summary"):
        logger.warning(f"Unauthorized access or invalid status for user {current_user.id}, app {app_id}")
        flash("Unauthorized or application not editable.", "error")
        return redirect(url_for("applicant.home"))

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
                            module_name="module_6",
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
            return redirect(url_for("module_6.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_6.fill_step", step="summary", application_id=app_id))

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_6").all()
        processed_module_data = []
        for md in all_module_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(v) for v in value]
            processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})
        return render_template(
            "module_6/summary.html",
            all_module_data=processed_module_data,
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
        f"module_6/{step}.html",  # Simplified, removed template_map
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

# Rest of the routes unchanged
@module_6.route("/save_undertaking_declaration/<int:application_id>", methods=["POST"])
@login_required
def save_undertaking_declaration(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return jsonify({"status": "error", "message": "Unauthorized or already submitted"}), 403

    form_data = request.form.to_dict()
    file_fields = ["official_seal"]
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
            form_data[field] = file_paths
        else:
            form_data[field] = form_data.get(field, [])

    for decl in ['apply_for_itu_filing', 'conformity_with_laws']:
        form_data[decl] = decl in request.form

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_6", step="undertaking_declaration").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_6", step="undertaking_declaration", data={})
        db.session.add(module_data)

    module_data.data = form_data
    module_data.completed = True
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
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_6").all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps.", "error")
        return redirect(url_for("module_6.fill_step", step="undertaking_declaration", application_id=application_id))

    try:
        application.status = "Submitted"
        db.session.commit()
        flash("Application submitted successfully!", "success")
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

@module_6.route("/download_pdf/<int:application_id>")
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Submitted":
        abort(403, "Unauthorized or invalid application")

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_6").all()
    uploaded_files = UploadedFile.query.filter_by(application_id=application_id, module_name="module_6").all()

    typst_content = """
    #set page(margin: 1in)
    #set text(font: "Arial", size: 12pt)
    #show heading: set text(size: 16pt, weight: "bold")

    = Application {{ application_id }} - Module 6 Summary
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
        subprocess.run(["typst", "compile", typst_file, base_pdf], check=True)
    except subprocess.CalledProcessError as e:
        os.remove(typst_file)
        abort(500, f"Typst compilation failed: {e}")

    pdf_files = [base_pdf]
    for uf in uploaded_files:
        full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", uf.filepath))
        if os.path.exists(full_path) and full_path.lower().endswith(".pdf"):
            pdf_files.append(full_path)
        else:
            logger.warning(f"Skipping {full_path}: Not found or not a PDF")

    final_pdf = f"final_{application_id}.pdf"
    try:
        cmd = ["pdftk"] + pdf_files + ["cat", "output", final_pdf]
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        os.remove(typst_file)
        os.remove(base_pdf)
        abort(500, f"PDF merging failed: {e}")

    os.remove(typst_file)
    os.remove(base_pdf)

    response = send_file(final_pdf, as_attachment=True, download_name=f"Module_6_Application_{application_id}.pdf")
    os.remove(final_pdf)
    return response