# app/modules/module_2/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, ApplicationAssignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os
import logging
import tempfile
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
    create_string_object,
)
from reportlab.lib.pagesizes import letter as reportlab_letter
from PIL import Image
import io
from docx2pdf import convert

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_2 = Blueprint("module_2", __name__, url_prefix="/module_2", template_folder="templates")

STEPS = [
    "satellite_overview",
    "satellite_configuration",
    "safety_and_manufacturing",
    "payload_details",
    "ground_segment",
    "itu_and_regulatory",
    "misc_and_declarations"
]

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_2.route("/fill_step/<step>", methods=["GET", "POST"])
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
        application.status != "Pending" and not application.editable and step != "summary"
    ):
        logger.warning(f"Unauthorized access or invalid application status for user {current_user.id}, app {app_id}")
        return "Unauthorized or invalid application", 403

    # Check Module 1 completion
    all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
    module_1_complete = False
    required_module_1_steps = ["applicant_identity", "entity_details", "management_ownership", "financial_credentials", "operational_contact", "declarations_submission"]
    for app in all_user_apps:
        module_1_data = ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all()
        if all(any(md.step == rs and md.completed for md in module_1_data) for rs in required_module_1_steps):
            module_1_complete = True
            break

    if not module_1_complete:
        flash("Please complete Module 1 (Basic Details) for at least one application before starting Module 2.", "error")
        logger.info(f"User {current_user.id} redirected to Module 1 due to incomplete Module 1 data")
        existing_module_2_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2").first()
        if existing_module_2_data and not existing_module_2_data.completed:
            db.session.delete(existing_module_2_data)
            db.session.commit()
        return redirect(url_for("module_1.fill_step", step="applicant_identity", application_id=app_id))

    module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2", step=step).first()
    if not module_data:
        module_data = ModuleData(application_id=app_id, module_name="module_2", step=step, data={})
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(application_id=app_id, module_name="module_2", step=step).all()
    logger.debug(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST" and step != "misc_and_declarations":
        form_data = request.form.to_dict()
        file_fields = {
            "safety_and_manufacturing": ["safety_assessment_report", "consent_document"],
            "payload_details": ["annexure_4"],
            "ground_segment": [],
            "itu_and_regulatory": ["interference_analysis_indian", "interference_analysis_non_indian", "annexure_2", "launch_service_agreement", "insurance_details", "dot_license_copies"],
            "misc_and_declarations": ["official_seal"]
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
                            module_name="module_2",
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
            return redirect(url_for("module_2.fill_step", step=STEPS[next_step_idx], application_id=app_id))
        return redirect(url_for("module_2.fill_step", step="summary", application_id=app_id))

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2").all()
        processed_module_data = []
        for md in all_module_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc) for doc in value]
            processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})
        return render_template(
            "module_2/summary.html",
            all_module_data=processed_module_data,
            application_id=app_id,
            application=application
        )

    all_module_data = ModuleData.query.filter_by(application_id=app_id, module_name="module_2").all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append({"step": md.step, "data": data_copy, "completed": md.completed})

    template_map = {
        "misc_and_declarations": "module_2/misc_and_declarations.html"
    }
    return render_template(
        template_map.get(step, f"module_2/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files
    )

@module_2.route("/save_misc_and_declarations/<int:application_id>", methods=["POST"])
@login_required
def save_misc_and_declarations(application_id):
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
                filename = f"{application_id}_misc_and_declarations_{field}_{f.filename}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_2",
                    step="misc_and_declarations",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
            form_data[field] = file_paths
        else:
            form_data[field] = form_data.get(field, [])

    for decl in ['coord_agreement', 'cease_emission', 'change_notification', 'govt_control', 'app_submission', 'compliance_affirmation', 'hosted_payload_undertaking']:
        form_data[decl] = decl in request.form

    module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_2", step="misc_and_declarations").first()
    if not module_data:
        module_data = ModuleData(application_id=application_id, module_name="module_2", step="misc_and_declarations", data={})
        db.session.add(module_data)

    module_data.data = form_data
    module_data.completed = True
    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_2.route("/submit_application/<int:application_id>", methods=["POST"])
@login_required
def submit_application(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))
    if application.status != "Pending" and not application.editable:
        flash("Application already submitted.", "warning")
        return redirect(url_for("applicant.home"))

    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_2").all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(step in completed_steps for step in required_steps):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(url_for("module_2.fill_step", step="misc_and_declarations", application_id=application_id))

    try:
        application.status = "Submitted"
        application.editable = False
        db.session.commit()
        flash("Application submitted successfully!", "success")
        return redirect(url_for("module_2.fill_step", step="summary", application_id=application_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for("module_2.fill_step", step="misc_and_declarations", application_id=application_id))
    
@module_2.route("/download_file/<int:file_id>")
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

@module_2.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("module_2.fill_step", step=STEPS[0], application_id=application.id))
    return render_template("module_2/start_application.html")

@module_2.route("/download_pdf/<application_id>", methods=["GET"])
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)
    
    # Allow Applicant or Verifiers assigned to the application
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend([assignment.primary_verifier_id, assignment.secondary_verifier_id])
    
    if current_user.id not in allowed_users or application.status not in ["Submitted", "Under Review"]:
        return "Unauthorized or invalid application", 403

    # Fetch all module data
    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_2"
    ).all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = value  # Keep full paths for PDF generation
        processed_module_data.append(
            {"step": md.step, "data": data_copy, "completed": md.completed}
        )

    # Create a temporary file for the PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        pdf_path = temp_file.name

        # Define custom styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontSize=18,
            textColor=colors.HexColor("#1A5276"),
            spaceAfter=16,
            alignment=1,
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#2874A6"),
            spaceBefore=12,
            spaceAfter=6,
        )
        normal_style = ParagraphStyle(
            "CustomNormal",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            spaceBefore=2,
            spaceAfter=2,
        )
        label_style = ParagraphStyle(
            "CustomLabel",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#34495E"),
            fontName="Helvetica-Bold",
        )
        attachment_style = ParagraphStyle(
            "AttachmentLink",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#2E86C1"),
            fontName="Helvetica",
        )

        # Generate the summary PDF
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=72,
            bottomMargin=36,
        )

        def header_footer(canvas, doc):
            canvas.saveState()
            width, height = letter
            logo_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "static/images/company_logo.png",
            )
            if os.path.exists(logo_path):
                canvas.drawImage(
                    logo_path,
                    36,
                    height - 54,
                    width=120,
                    height=40,
                    preserveAspectRatio=True,
                )
            else:
                canvas.setFont("Helvetica-Bold", 12)
                canvas.setFillColor(colors.HexColor("#1A5276"))
                canvas.drawString(36, height - 36, "Company Name")

            canvas.setStrokeColor(colors.HexColor("#AED6F1"))
            canvas.line(36, height - 60, width - 36, height - 60)
            canvas.setFont("Helvetica", 10)
            canvas.setFillColor(colors.HexColor("#34495E"))
            canvas.drawRightString(
                width - 36, height - 36, f"Application ID: {application_id}"
            )
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.gray)
            canvas.drawCentredString(width / 2, 20, "CONFIDENTIAL")
            canvas.drawRightString(width - 36, 20, "Page %d" % doc.page)
            canvas.setStrokeColor(colors.HexColor("#AED6F1"))
            canvas.line(36, 30, width - 36, 30)
            canvas.restoreState()

        story = []
        story.append(Paragraph("Module 2: Satellite Form Summary", title_style))
        story.append(Spacer(1, 0.25 * inch))

        metadata_content = [
            ["Application ID:", application_id],
            ["Date Submitted:", application.submitted_date.strftime("%B %d, %Y") if hasattr(application, "submitted_date") and application.submitted_date else "N/A"],
            ["Status:", application.status],
            ["Applicant:", current_user.username],
        ]
        metadata_table = Table(metadata_content, colWidths=[120, 300])
        metadata_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EBF5FB")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#2874A6")),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (0, -1), 10),
                ("RIGHTPADDING", (0, 0), (0, -1), 10),
                ("LEFTPADDING", (1, 0), (1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6EAF8")),
            ])
        )
        story.append(metadata_table)
        story.append(Spacer(1, 0.3 * inch))

        story.append(Paragraph("Table of Contents", heading_style))
        toc_items = []
        for i, md in enumerate(processed_module_data):
            toc_items.append([f"{i+1}.", md["step"].replace("_", " ").title()])
        toc_table = Table(toc_items, colWidths=[30, 390])
        toc_table.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ("LEFTPADDING", (1, 0), (1, -1), 5),
            ])
        )
        story.append(toc_table)
        story.append(Spacer(1, 0.3 * inch))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#AED6F1"), spaceAfter=0.2 * inch))

        attachment_files = []
        attachment_positions = {}
        for i, md in enumerate(processed_module_data):
            story.append(Paragraph(f"{i+1}. {md['step'].replace('_', ' ').title()}", heading_style))
            data_items = []
            for key, value in md["data"].items():
                if key not in ["documents", "document_names"] and value:
                    if isinstance(value, list):
                        story.append(Paragraph(f"{key.replace('_', ' ').title()}:", label_style))
                        for idx, file_path in enumerate(value):
                            filename = os.path.basename(file_path)
                            attachment_positions[filename] = len(story)
                            story.append(Paragraph(f"• Attachment: {filename} (Click to view)", attachment_style))
                            attachment_files.append((filename, file_path))
                    else:
                        data_items.append([Paragraph(f"{key.replace('_', ' ').title()}:", label_style), Paragraph(f"{value}", normal_style)])
            if data_items:
                data_table = Table(data_items, colWidths=[150, 360])
                data_table.setStyle(
                    TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (0, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ])
                )
                story.append(data_table)
            story.append(Spacer(1, 0.2 * inch))
            if i < len(processed_module_data) - 1:
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#D6EAF8"), spaceBefore=0.1 * inch, spaceAfter=0.1 * inch))

        doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

        writer = PdfWriter()
        summary_pdf = PdfReader(pdf_path)
        for page in summary_pdf.pages:
            writer.add_page(page)

        page_height = reportlab_letter[1]
        attachment_destinations = {}
        for filename, file_path in attachment_files:
            absolute_file_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", file_path))
            if not os.path.exists(absolute_file_path):
                print(f"File not found: {absolute_file_path}")
                continue

            attachment_page = len(writer.pages)
            attachment_destinations[filename] = attachment_page

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as separator_file:
                c = canvas.Canvas(separator_file.name, pagesize=reportlab_letter)
                width, height = reportlab_letter
                logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static/images/company_logo.png")
                if os.path.exists(logo_path):
                    c.drawImage(logo_path, 36, height - 54, width=120, height=40, preserveAspectRatio=True)
                else:
                    c.setFont("Helvetica-Bold", 12)
                    c.setFillColorRGB(0.1, 0.32, 0.46)
                    c.drawString(36, height - 36, "Company Name")
                c.setStrokeColorRGB(0.68, 0.85, 0.95)
                c.line(36, height - 60, width - 36, height - 60)
                c.setFont("Helvetica", 10)
                c.setFillColorRGB(0.18, 0.47, 0.7)
                c.drawString(36, height - 80, "← Back to Summary")
                c.setStrokeColorRGB(0.18, 0.47, 0.7)
                c.rect(32, height - 92, 105, 20, stroke=1, fill=0)
                c.setFillColorRGB(0.95, 0.95, 0.95)
                c.rect(36, height - 150, width - 72, 50, stroke=0, fill=1)
                c.setFillColorRGB(0.1, 0.32, 0.46)
                c.setFont("Helvetica-Bold", 14)
                c.drawCentredString(width / 2, height - 120, "Attachment:")
                c.setFont("Helvetica", 12)
                c.drawCentredString(width / 2, height - 140, filename)
                c.setFont("Helvetica", 8)
                c.setFillColorRGB(0.5, 0.5, 0.5)
                c.drawCentredString(width / 2, 20, "CONFIDENTIAL")
                c.drawRightString(width - 36, 20, f"Application ID: {application_id}")
                c.setStrokeColorRGB(0.68, 0.85, 0.95)
                c.line(36, 30, width - 36, 30)
                c.save()

                separator_pdf = PdfReader(separator_file.name)
                writer.add_page(separator_pdf.pages[0])

            file_ext = os.path.splitext(absolute_file_path)[1].lower()
            if file_ext == ".pdf":
                try:
                    attachment_pdf = PdfReader(absolute_file_path)
                    for page in attachment_pdf.pages:
                        writer.add_page(page)
                except Exception as e:
                    print(f"Error reading PDF {absolute_file_path}: {str(e)}")
                    continue
            elif file_ext == ".docx":
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                    try:
                        convert(absolute_file_path, temp_pdf.name)
                        attachment_pdf = PdfReader(temp_pdf.name)
                        for page in attachment_pdf.pages:
                            writer.add_page(page)
                        os.remove(temp_pdf.name)
                    except Exception as e:
                        print(f"Error converting DOCX {absolute_file_path}: {str(e)}")
                        continue
            elif file_ext in [".jpg", ".jpeg", ".png"]:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_img_pdf:
                        img = Image.open(absolute_file_path)
                        c = canvas.Canvas(temp_img_pdf.name, pagesize=reportlab_letter)
                        width, height = reportlab_letter
                        c.setFont("Helvetica-Bold", 10)
                        c.setFillColorRGB(0.1, 0.32, 0.46)
                        c.drawString(36, height - 30, f"Attachment: {filename}")
                        img_width, img_height = img.size
                        max_width = width - 72
                        max_height = height - 120
                        if img_width > max_width or img_height > max_height:
                            ratio = min(max_width / img_width, max_height / img_height)
                            display_width = img_width * ratio
                            display_height = img_height * ratio
                        else:
                            display_width = img_width
                            display_height = img_height
                        x_pos = (width - display_width) / 2
                        y_pos = (height - display_height) / 2
                        c.setStrokeColorRGB(0.8, 0.8, 0.8)
                        c.rect(x_pos - 5, y_pos - 5, display_width + 10, display_height + 10, stroke=1, fill=0)
                        c.drawImage(absolute_file_path, x_pos, y_pos, width=display_width, height=display_height)
                        c.setFont("Helvetica", 8)
                        c.setFillColorRGB(0.5, 0.5, 0.5)
                        c.drawString(36, 20, f"File: {filename}")
                        c.drawRightString(width - 36, 20, f"Application ID: {application_id}")
                        c.save()

                        img_pdf = PdfReader(temp_img_pdf.name)
                        for page in img_pdf.pages:
                            writer.add_page(page)
                        os.remove(temp_img_pdf.name)
                except Exception as e:
                    print(f"Error processing image {absolute_file_path}: {str(e)}")
                    continue
            else:
                print(f"Unsupported file type: {absolute_file_path}")
                continue

        for filename, page_position in attachment_positions.items():
            if filename not in attachment_destinations:
                continue
            items_per_page = 25
            page_index = min(page_position // items_per_page, len(summary_pdf.pages) - 1)
            page = writer.pages[page_index]
            position_on_page = page_position % items_per_page
            y_offset = page_height - 180 - (position_on_page * 20)
            action = DictionaryObject({
                NameObject("/S"): NameObject("/GoTo"),
                NameObject("/D"): ArrayObject([NumberObject(attachment_destinations[filename]), NameObject("/Fit")]),
            })
            link = DictionaryObject({
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject([NumberObject(60), NumberObject(y_offset - 10), NumberObject(450), NumberObject(y_offset + 10)]),
                NameObject("/A"): action,
                NameObject("/Border"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)]),
            })
            if NameObject("/Annots") not in page:
                page[NameObject("/Annots")] = ArrayObject()
            annots = page[NameObject("/Annots")]
            annots.append(writer._add_object(link))

        for filename, page_num in attachment_destinations.items():
            page = writer.pages[page_num]
            return_action = DictionaryObject({
                NameObject("/S"): NameObject("/GoTo"),
                NameObject("/D"): ArrayObject([NumberObject(0), NameObject("/Fit")]),
            })
            back_link = DictionaryObject({
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject([NumberObject(32), NumberObject(page_height - 92), NumberObject(137), NumberObject(page_height - 72)]),
                NameObject("/A"): return_action,
                NameObject("/Border"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)]),
            })
            if NameObject("/Annots") not in page:
                page[NameObject("/Annots")] = ArrayObject()
            annots = page[NameObject("/Annots")]
            annots.append(writer._add_object(back_link))

        with open(pdf_path, "wb") as f:
            writer.write(f)

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"application_{application_id}_module_2_summary.pdf",
            mimetype="application/pdf",
        )