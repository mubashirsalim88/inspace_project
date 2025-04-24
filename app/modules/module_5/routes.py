# app/modules/module_5/routes.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, abort
)
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, ApplicationAssignment
import os
import logging
import tempfile
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as reportlab_letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from PIL import Image
import fitz  # PyMuPDF
from docx2pdf import convert
from reportlab.pdfgen import canvas

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

module_5 = Blueprint("module_5", __name__, url_prefix="/module_5", template_folder="templates")

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

@module_5.route("/download_pdf/<int:application_id>", methods=["GET"])
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)

    # Authorization check
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend([assignment.primary_verifier_id, assignment.secondary_verifier_id])
    
    if current_user.id not in allowed_users or application.status not in ["Submitted", "Under Review"]:
        return "Unauthorized or invalid application", 403

    # Fetch module data and uploaded files
    all_module_data = ModuleData.query.filter_by(application_id=application_id, module_name="module_5").all()
    processed_module_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in all_module_data
    ]
    uploaded_files = UploadedFile.query.filter_by(application_id=application_id, module_name="module_5").all()

    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as summary_file:
        summary_pdf_path = summary_file.name
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_file:
        final_pdf_path = final_file.name

    # Styles setup
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
    link_style = ParagraphStyle(
        "Link",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#2E86C1"),
        fontName="Helvetica",
    )

    # Track attachment positions and file paths
    attachment_positions = {}
    attachment_files = []

    # PDF Document setup
    doc = SimpleDocTemplate(
        summary_pdf_path,
        pagesize=reportlab_letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=72,
        bottomMargin=36,
    )

    def header_footer(canvas, doc):
        canvas.saveState()
        width, height = reportlab_letter
        logo_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static/images/IN-SPACe_Logo.png"
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
            canvas.drawString(36, height - 36, "IN-SPACe")

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
        canvas.drawRightString(width - 36, 20, f"Page {doc.page}")
        canvas.line(36, 30, width - 36, 30)
        canvas.restoreState()

    story = []
    story.append(Paragraph("Module 5: Host Space Object Details", title_style))
    story.append(Spacer(1, 0.25 * inch))

    # Metadata table
    metadata_content = [
        ["Application ID:", application_id],
        ["Status:", application.status],
        [
            "Applicant:",
            (
                f"{current_user.first_name} {current_user.last_name}"
                if hasattr(current_user, "first_name")
                else current_user.username
            ),
        ],
    ]
    metadata_table = Table(metadata_content, colWidths=[120, 300])
    metadata_table.setStyle(
        [
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EBF5FB")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#2874A6")),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6EAF8")),
        ]
    )
    story.append(metadata_table)
    story.append(Spacer(1, 0.3 * inch))

    # TOC
    toc_items = [
        [f"{i+1}.", md["step"].replace("_", " ").title()]
        for i, md in enumerate(processed_module_data)
    ]
    toc_table = Table(toc_items, colWidths=[30, 390])
    toc_table.setStyle(
        [
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (1, 0), (1, -1), 5),
        ]
    )
    story.append(Paragraph("Table of Contents", heading_style))
    story.append(toc_table)
    story.append(Spacer(1, 0.3 * inch))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#AED6F1"),
            spaceAfter=0.2 * inch,
        )
    )

    # Content with attachment links
    for i, md in enumerate(processed_module_data):
        story.append(
            Paragraph(f"{i+1}. {md['step'].replace('_', ' ').title()}", heading_style)
        )
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and value:
                if isinstance(value, list):
                    story.append(
                        Paragraph(f"{key.replace('_', ' ').title()}:", label_style)
                    )
                    for file_path in value:
                        filename = os.path.basename(file_path)
                        attachment_positions[filename] = (len(story) + 1, f"{filename}")
                        story.append(Paragraph(f"• {filename}", link_style))
                        attachment_files.append((filename, file_path))
                else:
                    story.append(
                        Table(
                            [
                                [
                                    Paragraph(
                                        f"{key.replace('_', ' ').title()}:", label_style
                                    ),
                                    Paragraph(str(value), normal_style),
                                ]
                            ],
                            colWidths=[150, 360],
                        )
                    )
        story.append(Spacer(1, 0.2 * inch))
        if i < len(processed_module_data) - 1:
            story.append(
                HRFlowable(
                    width="100%", thickness=0.5, color=colors.HexColor("#D6EAF8")
                )
            )

    # Build the initial PDF with ReportLab
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

    # Use PyMuPDF to assemble the final PDF with working links
    doc = fitz.open(summary_pdf_path)

    # Dictionary to track attachment page numbers
    attachment_page_numbers = {}
    current_page = len(doc)

    # Add attachment pages and track their positions
    for filename, file_path in attachment_files:
        absolute_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", file_path)
        )
        if not os.path.exists(absolute_path):
            logger.warning(f"Attachment file not found: {absolute_path}")
            continue

        # Add separator page
        separator_page = doc.new_page(
            width=doc[0].rect.width, height=doc[0].rect.height
        )
        page_width = doc[0].rect.width

        # Center "Attachment" text
        text = "Attachment"
        text_width = fitz.get_text_length(text, fontname="helv", fontsize=14)
        separator_page.insert_text(
            (page_width / 2 - text_width / 2, 100),
            text,
            fontname="helv",
            fontsize=14,
            color=(26 / 255, 82 / 255, 118 / 255),
        )

        # Center filename text
        text = filename
        text_width = fitz.get_text_length(text, fontname="helv", fontsize=12)
        separator_page.insert_text(
            (page_width / 2 - text_width / 2, 120),
            text,
            fontname="helv",
            fontsize=12,
            color=(0, 0, 0),
        )

        # Left-aligned "Back to Summary" text
        separator_page.insert_text(
            (36, 80),
            "← Back to Summary",
            fontname="helv",
            fontsize=10,
            color=(46 / 255, 134 / 255, 193 / 255),
        )

        # Save the page number for this attachment
        attachment_page_numbers[filename] = current_page
        current_page += 1

        # Add file content
        file_ext = os.path.splitext(absolute_path)[1].lower()
        if file_ext == ".pdf":
            src_doc = fitz.open(absolute_path)
            doc.insert_pdf(src_doc)
            current_page += len(src_doc)
            src_doc.close()
        elif file_ext == ".docx":
            temp_pdf = tempfile.mktemp(suffix=".pdf")
            convert(absolute_path, temp_pdf)
            src_doc = fitz.open(temp_pdf)
            doc.insert_pdf(src_doc)
            current_page += len(src_doc)
            src_doc.close()
            os.unlink(temp_pdf)
        elif file_ext in [".jpg", ".png", ".jpeg", ".gif"]:
            img = Image.open(absolute_path)
            temp_pdf = tempfile.mktemp(suffix=".pdf")
            img_width, img_height = img.size
            c = canvas.Canvas(temp_pdf, pagesize=reportlab_letter)
            page_width, page_height = reportlab_letter
            scale = min((page_width - 72) / img_width, (page_height - 150) / img_height)
            c.drawImage(absolute_path, 36, 150, img_width * scale, img_height * scale)
            c.save()
            src_doc = fitz.open(temp_pdf)
            doc.insert_pdf(src_doc)
            current_page += len(src_doc)
            src_doc.close()
            os.unlink(temp_pdf)

    # Add links from summary to attachments with enhanced logging
    for filename, (position, link_text) in attachment_positions.items():
        if filename in attachment_page_numbers:
            # Try searching all pages to ensure text is found
            found = False
            for page_num in range(len(doc)):
                page = doc[page_num]
                instances = page.search_for(f"• {filename}")
                if instances:
                    rect = instances[0]
                    logger.debug(
                        f"Found '• {filename}' on page {page_num}, adding link to page {attachment_page_numbers[filename]}"
                    )
                    page.insert_link(
                        {
                            "kind": fitz.LINK_GOTO,
                            "from": rect,
                            "to": fitz.Point(0, 0),
                            "page": attachment_page_numbers[filename],
                        }
                    )
                    found = True
                    break
            if not found:
                logger.error(f"Text '• {filename}' not found in PDF for linking")

    # Add back links from attachments to summary
    for filename, page_num in attachment_page_numbers.items():
        if page_num < len(doc):
            page = doc[page_num]
            instances = page.search_for("← Back to Summary")
            if instances:
                rect = instances[0]
                logger.debug(
                    f"Found '← Back to Summary' on page {page_num}, adding link to page 0"
                )
                page.insert_link(
                    {
                        "kind": fitz.LINK_GOTO,
                        "from": rect,
                        "to": fitz.Point(0, 0),
                        "page": 0,
                    }
                )
            else:
                logger.error(f"Text '← Back to Summary' not found on page {page_num}")

    # Save the final PDF
    try:
        doc.save(final_pdf_path)
    except Exception as e:
        logger.error(f"Error saving final PDF: {e}")
        doc.close()
        os.unlink(summary_pdf_path)
        raise e
    doc.close()

    # Clean up the temporary summary PDF
    os.unlink(summary_pdf_path)

    # Serve the file and ensure cleanup after response
    try:
        response = send_file(
            final_pdf_path,
            as_attachment=True,
            download_name=f"application_{application_id}_summary.pdf",
            mimetype="application/pdf",
        )
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(final_pdf_path)
            except Exception as e:
                logger.error(f"Error deleting {final_pdf_path}: {e}")
        return response
    except Exception as e:
        os.unlink(final_pdf_path)
        raise e