from flask import Blueprint, send_file, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, ApplicationAssignment, UploadedFile
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as reportlab_letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, HRFlowable, PageBreak, KeepTogether
from reportlab.pdfgen import canvas
import os
import tempfile
from PIL import Image
from docx2pdf import convert
import fitz  # PyMuPDF
import re
import logging

module_10_pdf = Blueprint(
    "module_10_pdf", __name__, url_prefix="/module_10", template_folder="templates"
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def clean_filename(filename):
    """Convert raw filename to a clean display name."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'^\d+_?', '', name)
    name = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_?', '', name)
    parts = name.split('_')
    if len(parts) > 2:
        step = ' '.join(word.capitalize() for word in parts[0].split('_'))
        field = ' '.join(word.capitalize() for word in '_'.join(parts[1:-1]).split('_'))
        filename_part = ' '.join(word.capitalize() for word in parts[-1].split('_'))
        name = f"{step} {field} {filename_part}"
    else:
        name = ' '.join(word.capitalize() for word in name.split('_'))
    if len(name) > 80:
        name = name[:77] + "..."
    return name

def ensure_white_background(image_path):
    """Ensure the image has a white background by removing transparency."""
    try:
        img = Image.open(image_path)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        white_background = Image.new('RGBA', img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white_background, img)
        img = img.convert('RGB')
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        img.save(temp_file.name, 'PNG')
        return temp_file.name
    except Exception as e:
        logger.error(f"Error processing logo background: {e}")
        return image_path

@module_10_pdf.route("/download_pdf/<int:application_id>", methods=["GET"])
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)

    # Authorization check
    assignment = ApplicationAssignment.query.filter_by(
        application_id=application_id
    ).first()
    allowed_users = [application.user_id]
    if assignment:
        if assignment.primary_verifier_id:
            allowed_users.append(assignment.primary_verifier_id)
        if assignment.secondary_verifier_id:
            allowed_users.append(assignment.secondary_verifier_id)

    if current_user.role == "Director":
        allowed_users.append(current_user.id)

    allowed_statuses = ["Submitted", "Under Review", "Pending Secondary Approval", "Pending Director Approval", "Approved", "Rejected"]
    if current_user.id not in allowed_users or application.status not in allowed_statuses:
        logger.warning(f"Unauthorized access to PDF for application {application_id} by user {current_user.id}, status: {application.status}")
        return "Unauthorized or invalid application", 403

    # Fetch Module 1 data (latest completed application)
    all_user_apps = Application.query.filter_by(user_id=application.user_id).all()
    latest_module_1_data = []
    latest_app_id = None
    latest_submission_date = None
    required_module_1_steps = [
        "applicant_identity", "entity_details", "management_ownership",
        "financial_credentials", "operational_contact", "declarations_submission"
    ]
    for app in all_user_apps:
        module_1_data = ModuleData.query.filter_by(application_id=app.id, module_name="module_1").all()
        if all(
            any(md.step == rs and md.completed for md in module_1_data)
            for rs in required_module_1_steps
        ):
            if not latest_submission_date or app.created_at > latest_submission_date:
                latest_submission_date = app.created_at
                latest_app_id = app.id
                latest_module_1_data = module_1_data

    processed_module_1_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in latest_module_1_data
        if md.step.lower() != "summary"
    ]

    # Fetch Module 10 data
    module_10_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_10"
    ).all()
    processed_module_10_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in module_10_data
        if md.step.lower() != "summary"
    ]

    # Fetch uploaded files
    uploaded_files_module_1 = UploadedFile.query.filter_by(
        application_id=latest_app_id, module_name="module_1"
    ).all() if latest_app_id else []
    uploaded_files_module_10 = UploadedFile.query.filter_by(
        application_id=application_id, module_name="module_10"
    ).all()
    uploaded_file_paths = {}
    for f in uploaded_files_module_1 + uploaded_files_module_10:
        absolute_path = os.path.join(os.path.dirname(__file__), "..", f.filepath)
        if os.path.exists(absolute_path):
            uploaded_file_paths[absolute_path] = (f.filename, absolute_path)
        logger.debug(f"UploadedFile: {f.filename}, Step: {f.step}, Field: {f.field_name}, Path: {absolute_path}, Exists: {os.path.exists(absolute_path)}")

    # Fetch file paths from ModuleData.data
    module_data_file_paths = {}
    for md in processed_module_1_data + processed_module_10_data:
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and isinstance(value, list) and all(isinstance(v, str) for v in value):
                for file_path in value:
                    absolute_path = os.path.join(os.path.dirname(__file__), "..", file_path)
                    if os.path.exists(absolute_path):
                        module_data_file_paths[absolute_path] = (os.path.basename(file_path), absolute_path)
                    logger.debug(f"ModuleData: Step: {md['step']}, Field: {key}, File: {os.path.basename(file_path)}, Path: {absolute_path}, Exists: {os.path.exists(absolute_path)}")

    # Combine and deduplicate file paths
    all_file_paths = {**uploaded_file_paths, **module_data_file_paths}
    attachment_files = list(all_file_paths.values())
    logger.debug(f"Combined attachment files: {attachment_files}")

    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as summary_file:
        summary_pdf_path = summary_file.name
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_file:
        final_pdf_path = final_file.name

    # Styles setup
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontSize=24,
        fontName="Helvetica-Bold",
        textColor=colors.black,
        spaceAfter=30,
        spaceBefore=20,
        alignment=1,
    )
    detail_style = ParagraphStyle(
        "Detail",
        parent=styles["Normal"],
        fontSize=12,
        fontName="Helvetica",
        textColor=colors.black,
        spaceAfter=8,
        alignment=0,
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading1"],
        fontSize=14,
        fontName="Helvetica-Bold",
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=10,
    )
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica",
        leading=14,
        textColor=colors.black,
        spaceBefore=6,
        spaceAfter=6,
    )
    label_style = ParagraphStyle(
        "CustomLabel",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        leading=14,
        textColor=colors.black,
        spaceBefore=6,
        spaceAfter=6,
    )
    link_style = ParagraphStyle(
        "Link",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica",
        textColor=colors.HexColor("#0000FF"),
        spaceBefore=6,
        spaceAfter=6,
    )

    attachment_positions = {}

    doc = SimpleDocTemplate(
        summary_pdf_path,
        pagesize=reportlab_letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=80,
        bottomMargin=36,
    )

    def header_footer(canvas, doc):
        canvas.saveState()
        width, height = reportlab_letter
        logo_path = os.path.join(current_app.static_folder, "images", "IN-SPACe_Logo.png")
        logo_to_use = logo_path
        temp_logo = None
        if os.path.exists(logo_path):
            temp_logo_path = ensure_white_background(logo_path)
            logo_to_use = temp_logo_path
            canvas.drawImage(
                logo_to_use,
                40,
                height - 50,
                width=100,
                height=35,
                preserveAspectRatio=True,
            )
            if temp_logo_path != logo_path:
                temp_logo = temp_logo_path
        else:
            logger.warning(f"Logo not found at {logo_path}")
            canvas.setFont("Helvetica-Bold", 12)
            canvas.setFillColor(colors.black)
            canvas.drawString(40, height - 36, "IN-SPACe")

        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.black)
        canvas.drawRightString(
            width - 36, height - 50, f"Application ID: {application_id}"
        )

        canvas.setStrokeColor(colors.gray)
        canvas.line(36, height - 60, width - 36, height - 60)

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.gray)
        canvas.drawRightString(width - 36, 24, f"Page {doc.page}")
        canvas.line(36, 24, width - 36, 24)

        canvas.restoreState()
        if temp_logo and os.path.exists(temp_logo):
            os.unlink(temp_logo)

    story = []

    # Summary and Table of Contents
    summary_flowables = []
    summary_flowables.append(Paragraph("Application Summary", title_style))
    summary_flowables.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray, spaceBefore=15, spaceAfter=15))
    summary_data = [
        [Paragraph("Application ID:", label_style), Paragraph(str(application_id), detail_style)],
        [Paragraph("Status:", label_style), Paragraph(application.status, detail_style)],
        [Paragraph("Applicant:", label_style), Paragraph(
            f"{current_user.first_name} {current_user.last_name}" if hasattr(current_user, "first_name") else current_user.username,
            detail_style
        )],
        [Paragraph("Date Submitted:", label_style), Paragraph(
            application.submitted_date.strftime("%B %d, %Y") if hasattr(application, "submitted_date") and application.submitted_date else "N/A",
            detail_style
        )],
    ]
    summary_table = Table(summary_data, colWidths=[150, 360])
    summary_table.setStyle(
        [
            ("FONTSIZE", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.gray),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ]
    )
    summary_flowables.append(summary_table)
    summary_flowables.append(Spacer(1, 0.5 * inch))
    summary_flowables.append(Paragraph("Table of Contents", heading_style))
    toc_items = []
    toc_index = 1
    toc_items.append([f"{toc_index}.", "Basic Details (Module 1)", ""])
    toc_index += 1
    for md in processed_module_1_data:
        toc_items.append([f"  {toc_index}.", md["step"].replace("_", " ").title(), ""])
        toc_index += 1
    toc_items.append([f"{toc_index}.", "Module 10: Space Object Registration", ""])
    toc_index += 1
    for md in processed_module_10_data:
        toc_items.append([f"  {toc_index}.", md["step"].replace("_", " ").title(), ""])
        toc_index += 1
    toc_items.append([f"{toc_index}.", "Uploaded Documents", ""])
    toc_table = Table(toc_items, colWidths=[50, 340, 50])
    toc_table.setStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (1, 0), (1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.gray),
        ]
    )
    summary_flowables.append(toc_table)
    summary_flowables.append(Spacer(1, 0.3 * inch))
    story.append(KeepTogether(summary_flowables))
    story.append(PageBreak())

    # Module 1 Section
    section_index = 1
    story.append(Paragraph(f"{section_index}. Basic Details (Module 1)", heading_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray, spaceBefore=10, spaceAfter=10))
    section_index += 1
    for i, md in enumerate(processed_module_1_data):
        section_flowables = []
        step_title = md["step"].replace("_", " ").title()
        section_flowables.append(Paragraph(f"{section_index}. {step_title}", heading_style))
        data_table = []
        files_added = set()
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and value:
                key_clean = key.replace("_", " ").title()
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    for file_path in value:
                        absolute_path = os.path.join(os.path.dirname(__file__), "..", file_path)
                        if absolute_path not in files_added and os.path.exists(absolute_path):
                            filename = os.path.basename(file_path)
                            display_name = clean_filename(filename)
                            attachment_positions[absolute_path] = len(story) + len(section_flowables)
                            data_table.append([
                                Paragraph(f"{key_clean}:", label_style),
                                Paragraph(display_name, link_style),
                            ])
                            files_added.add(absolute_path)
                            logger.debug(f"Added {filename} from ModuleData.data[{key}] for Module 1 step {md['step']}")
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            for sub_key, sub_value in item.items():
                                data_table.append([
                                    Paragraph(f"{sub_key.replace('_', ' ').title()}:", label_style),
                                    Paragraph(str(sub_value), normal_style),
                                ])
                else:
                    data_table.append([
                        Paragraph(f"{key_clean}:", label_style),
                        Paragraph(str(value), normal_style),
                    ])
        step_files = [f for f in uploaded_files_module_1 if f.step == md["step"]]
        for f in step_files:
            absolute_path = os.path.join(os.path.dirname(__file__), "..", f.filepath)
            if absolute_path not in files_added and os.path.exists(absolute_path):
                field_name = f.field_name.replace('_', ' ').title()
                display_name = clean_filename(f.filename)
                attachment_positions[absolute_path] = len(story) + len(section_flowables)
                data_table.append([
                    Paragraph(f"{field_name}:", label_style),
                    Paragraph(display_name, link_style),
                ])
                files_added.add(absolute_path)
                logger.debug(f"Added {f.filename} from UploadedFile for Module 1 step {md['step']}, field {f.field_name}")
        if data_table:
            table = Table(data_table, colWidths=[150, 360])
            table.setStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.gray),
                ]
            )
            section_flowables.append(table)
        section_flowables.append(Spacer(1, 0.3 * inch))
        if i < len(processed_module_1_data) - 1:
            section_flowables.append(
                HRFlowable(
                    width="100%", thickness=0.5, color=colors.gray, spaceBefore=10, spaceAfter=10
                )
            )
        story.append(KeepTogether(section_flowables))
        section_index += 1

    # Module 10 Section
    story.append(Paragraph(f"{section_index}. Module 10: Space Object Registration", heading_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray, spaceBefore=10, spaceAfter=10))
    section_index += 1
    for i, md in enumerate(processed_module_10_data):
        section_flowables = []
        step_title = md["step"].replace("_", " ").title()
        section_flowables.append(Paragraph(f"{section_index}. {step_title}", heading_style))
        data_table = []
        files_added = set()
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and value:
                key_clean = key.replace("_", " ").title()
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    for file_path in value:
                        absolute_path = os.path.join(os.path.dirname(__file__), "..", file_path)
                        if absolute_path not in files_added and os.path.exists(absolute_path):
                            filename = os.path.basename(file_path)
                            display_name = clean_filename(filename)
                            attachment_positions[absolute_path] = len(story) + len(section_flowables)
                            data_table.append([
                                Paragraph(f"{key_clean}:", label_style),
                                Paragraph(display_name, link_style),
                            ])
                            files_added.add(absolute_path)
                            logger.debug(f"Added {filename} from ModuleData.data[{key}] for Module 10 step {md['step']}")
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            for sub_key, sub_value in item.items():
                                data_table.append([
                                    Paragraph(f"{sub_key.replace('_', ' ').title()}:", label_style),
                                    Paragraph(str(sub_value), normal_style),
                                ])
                else:
                    data_table.append([
                        Paragraph(f"{key_clean}:", label_style),
                        Paragraph(str(value), normal_style),
                    ])
        step_files = [f for f in uploaded_files_module_10 if f.step == md["step"]]
        for f in step_files:
            absolute_path = os.path.join(os.path.dirname(__file__), "..", f.filepath)
            if absolute_path not in files_added and os.path.exists(absolute_path):
                field_name = f.field_name.replace('_', ' ').title()
                display_name = clean_filename(f.filename)
                attachment_positions[absolute_path] = len(story) + len(section_flowables)
                data_table.append([
                    Paragraph(f"{field_name}:", label_style),
                    Paragraph(display_name, link_style),
                ])
                files_added.add(absolute_path)
                logger.debug(f"Added {f.filename} from UploadedFile for Module 10 step {md['step']}, field {f.field_name}")
        if data_table:
            table = Table(data_table, colWidths=[150, 360])
            table.setStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.gray),
                ]
            )
            section_flowables.append(table)
        section_flowables.append(Spacer(1, 0.3 * inch))
        if i < len(processed_module_10_data) - 1:
            section_flowables.append(
                HRFlowable(
                    width="100%", thickness=0.5, color=colors.gray, spaceBefore=10, spaceAfter=10
                )
            )
        story.append(KeepTogether(section_flowables))
        section_index += 1

    # Uploaded Documents Section
    uploaded_flowables = []
    uploaded_flowables.append(Paragraph(f"{section_index}. Uploaded Documents", heading_style))
    doc_list = []
    for _, file_path in attachment_files:
        absolute_path = file_path
        filename = os.path.basename(file_path)
        display_name = clean_filename(filename)
        attachment_positions[absolute_path] = len(story) + len(uploaded_flowables)
        doc_list.append([Paragraph(display_name, link_style)])
    if doc_list:
        doc_table = Table(doc_list, colWidths=[510])
        doc_table.setStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.gray),
            ]
        )
        uploaded_flowables.append(doc_table)
    else:
        uploaded_flowables.append(Paragraph("No documents uploaded.", normal_style))
    uploaded_flowables.append(Spacer(1, 0.3 * inch))
    story.append(KeepTogether(uploaded_flowables))

    # Build the initial PDF
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

    # Add attachments and links with PyMuPDF
    final_doc = fitz.open(summary_pdf_path)
    content_page_count = len(final_doc)
    attachment_page_numbers = {}
    current_page = content_page_count

    for _, file_path in attachment_files:
        absolute_path = file_path
        if not os.path.exists(absolute_path):
            logger.warning(f"Attachment file not found: {absolute_path}")
            continue

        # Add separator page
        separator_page = final_doc.new_page(
            width=final_doc[0].rect.width, height=final_doc[0].rect.height
        )
        page_width = final_doc[0].rect.width
        display_name = clean_filename(os.path.basename(absolute_path))
        separator_page.insert_text(
            (page_width / 2 - fitz.get_text_length("Attachment", fontname="helv", fontsize=14) / 2, 100),
            "Attachment",
            fontname="helv",
            fontsize=14,
            color=(0, 0, 0),
        )
        separator_page.insert_text(
            (page_width / 2 - fitz.get_text_length(display_name, fontname="helv", fontsize=12) / 2, 120),
            display_name,
            fontname="helv",
            fontsize=12,
            color=(0, 0, 0),
        )
        separator_page.insert_text(
            (36, 80),
            "Back to Summary",
            fontname="helv",
            fontsize=10,
            color=(0, 0, 1),
        )

        attachment_page_numbers[absolute_path] = current_page
        current_page += 1

        # Add file content
        file_ext = os.path.splitext(absolute_path)[1].lower()
        if file_ext == ".pdf":
            try:
                src_doc = fitz.open(absolute_path)
                final_doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            except Exception as e:
                logger.error(f"Error attaching PDF {absolute_path}: {e}")
                continue
        elif file_ext in [".doc", ".docx"]:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                temp_pdf_path = temp_pdf.name
            try:
                convert(absolute_path, temp_pdf_path)
                src_doc = fitz.open(temp_pdf_path)
                final_doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            except Exception as e:
                logger.error(f"Error converting DOC/DOCX {absolute_path}: {e}")
            finally:
                if os.path.exists(temp_pdf_path):
                    os.unlink(temp_pdf_path)
        elif file_ext in [".jpg", ".png", ".jpeg"]:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                temp_pdf_path = temp_pdf.name
            try:
                img = Image.open(absolute_path)
                img_width, img_height = img.size
                c = canvas.Canvas(temp_pdf_path, pagesize=reportlab_letter)
                page_width, page_height = reportlab_letter
                scale = min((page_width - 72) / img_width, (page_height - 150) / img_height)
                c.drawImage(absolute_path, 36, 150, img_width * scale, img_height * scale)
                c.save()
                src_doc = fitz.open(temp_pdf_path)
                final_doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            except Exception as e:
                logger.error(f"Error processing image {absolute_path}: {e}")
            finally:
                if os.path.exists(temp_pdf_path):
                    os.unlink(temp_pdf_path)

    # Add file links
    for file_path in attachment_positions:
        if file_path in attachment_page_numbers:
            display_name = clean_filename(os.path.basename(file_path))
            page_num = 0
            while page_num < content_page_count:
                page = final_doc[page_num]
                instances = page.search_for(display_name)
                if instances:
                    for rect in instances:
                        page.insert_link(
                            {
                                "kind": fitz.LINK_GOTO,
                                "from": rect,
                                "to": fitz.Point(0, 0),
                                "page": attachment_page_numbers[file_path],
                            }
                        )
                page_num += 1

    # Add back links
    for file_path, page_num in attachment_page_numbers.items():
        if page_num < len(final_doc):
            page = final_doc[page_num]
            instances = page.search_for("Back to Summary")
            if instances:
                rect = instances[0]
                page.insert_link(
                    {
                        "kind": fitz.LINK_GOTO,
                        "from": rect,
                        "to": fitz.Point(0, 0),
                        "page": 0,
                    }
                )

    # Save the final PDF
    try:
        final_doc.save(final_pdf_path)
    except Exception as e:
        logger.error(f"Error saving final PDF: {e}")
        final_doc.close()
        if os.path.exists(summary_pdf_path):
            os.unlink(summary_pdf_path)
        raise e
    final_doc.close()

    # Clean up temporary files
    if os.path.exists(summary_pdf_path):
        os.unlink(summary_pdf_path)

    # Serve the file
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
                if os.path.exists(final_pdf_path):
                    os.unlink(final_pdf_path)
            except Exception as e:
                logger.error(f"Error deleting {final_pdf_path}: {e}")
        return response
    except Exception as e:
        logger.error(f"Error serving PDF for application {application_id}: {e}")
        if os.path.exists(final_pdf_path):
            os.unlink(final_pdf_path)
        raise e

@module_10_pdf.route("/test_pdf")
def test_pdf():
    return "module_10_pdf Blueprint is working!"