# module 2 pdf
from flask import Blueprint, send_file, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, ApplicationAssignment, UploadedFile
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as reportlab_letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    HRFlowable,
    PageBreak,
    KeepTogether,
)
from reportlab.pdfgen import canvas
import os
import tempfile
from PIL import Image
from docx2pdf import convert
import fitz  # PyMuPDF
import re
import logging

module_2_pdf = Blueprint(
    "module_2_pdf", __name__, url_prefix="/module_2", template_folder="templates"
)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def clean_filename(filename):
    """Convert raw filename to a clean display name."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r"^\d+_?", "", name)
    name = " ".join(word.capitalize() for word in name.split("_"))
    if len(name) > 80:
        name = name[:77] + "..."
    return name


def ensure_white_background(image_path):
    """Ensure the image has a white background by removing transparency."""
    try:
        img = Image.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        white_background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white_background, img)
        img = img.convert("RGB")
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(temp_file.name, "PNG")
        return temp_file.name
    except Exception as e:
        logger.error(f"Error processing logo background: {e}")
        return image_path


@module_2_pdf.route("/download_pdf/<application_id>", methods=["GET"])
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

    # Allow Directors to access the PDF
    if current_user.role == "Director":
        allowed_users.append(current_user.id)

    # Allow access for relevant application statuses
    allowed_statuses = [
        "Submitted",
        "Under Review",
        "Pending Secondary Approval",
        "Pending Director Approval",
        "Approved",
        "Rejected",
    ]
    if (
        current_user.id not in allowed_users
        or application.status not in allowed_statuses
    ):
        logger.warning(
            f"Unauthorized access to PDF for application {application_id} by user {current_user.id}, status: {application.status}"
        )
        return "Unauthorized or invalid application", 403

    # Fetch latest completed Module 1 data
    all_user_apps = Application.query.filter_by(user_id=current_user.id).all()
    latest_module_1_data = []
    latest_app_id = None
    latest_submission_date = None
    required_module_1_steps = [
        "applicant_identity",
        "entity_details",
        "management_ownership",
        "financial_credentials",
        "operational_contact",
        "declarations_submission",
    ]
    for app in all_user_apps:
        module_1_data = ModuleData.query.filter_by(
            application_id=app.id, module_name="module_1"
        ).all()
        if all(
            any(md.step == rs and md.completed for md in module_1_data)
            for rs in required_module_1_steps
        ):
            if not latest_submission_date or app.created_at > latest_submission_date:
                latest_submission_date = app.created_at
                latest_app_id = app.id
                latest_module_1_data = module_1_data

    # Process Module 1 data
    processed_module_1_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in latest_module_1_data
        if md.step.lower() != "summary"
    ]

    # Fetch Module 2 data
    module_2_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_2"
    ).all()
    processed_module_2_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in module_2_data
        if md.step.lower() != "summary"
    ]

    # Fetch uploaded files for both modules
    uploaded_files_module_1 = (
        UploadedFile.query.filter_by(
            application_id=latest_app_id, module_name="module_1"
        ).all()
        if latest_app_id
        else []
    )
    uploaded_files_module_2 = UploadedFile.query.filter_by(
        application_id=application_id, module_name="module_2"
    ).all()
    attachment_files_module_1 = [
        (f.filename, os.path.join(os.path.dirname(__file__), "..", f.filepath))
        for f in uploaded_files_module_1
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", f.filepath))
    ]
    attachment_files_module_2 = [
        (f.filename, os.path.join(os.path.dirname(__file__), "..", f.filepath))
        for f in uploaded_files_module_2
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", f.filepath))
    ]
    # Combine attachment files, ensuring unique filenames
    attachment_files = attachment_files_module_1 + attachment_files_module_2
    unique_attachments = {}
    for filename, filepath in attachment_files:
        if filename not in unique_attachments:
            unique_attachments[filename] = filepath
    attachment_files = [
        (filename, filepath) for filename, filepath in unique_attachments.items()
    ]

    # Log attachment files
    for filename, file_path in attachment_files:
        absolute_path = os.path.abspath(file_path)
        logger.debug(
            f"Checking attachment: {filename}, Path: {absolute_path}, Exists: {os.path.exists(absolute_path)}"
        )
        if not os.path.exists(absolute_path):
            logger.warning(f"Attachment file missing: {absolute_path}")

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

    # Track attachment positions and file paths
    attachment_positions = {}

    # PDF Document setup
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
        logo_path = os.path.join(
            current_app.static_folder, "images", "IN-SPACe_Logo.png"
        )
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

    # Combined Application Details and Table of Contents Page
    summary_flowables = []
    summary_flowables.append(Paragraph("Application Summary", title_style))
    summary_flowables.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.gray,
            spaceBefore=15,
            spaceAfter=15,
        )
    )
    summary_data = [
        [
            Paragraph("Application ID:", label_style),
            Paragraph(str(application_id), detail_style),
        ],
        [
            Paragraph("Status:", label_style),
            Paragraph(application.status, detail_style),
        ],
        [
            Paragraph("Applicant:", label_style),
            Paragraph(current_user.username, detail_style),
        ],
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
    # Add Module 1 TOC entries
    toc_items.append([f"{toc_index}.", "Basic Details (Module 1)", ""])
    toc_index += 1
    for md in processed_module_1_data:
        toc_items.append([f"  {toc_index}.", md["step"].replace("_", " ").title(), ""])
        toc_index += 1
    # Add Module 2 TOC entries
    toc_items.append([f"{toc_index}.", "Satellite Details (Module 2)", ""])
    toc_index += 1
    for md in processed_module_2_data:
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

    # Basic Details (Module 1) Section
    section_index = 1
    module_flowables = []
    module_flowables.append(
        Paragraph(f"{section_index}. Basic Details (Module 1)", heading_style)
    )
    module_flowables.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.gray,
            spaceBefore=10,
            spaceAfter=10,
        )
    )
    story.append(KeepTogether(module_flowables))
    section_index += 1

    for i, md in enumerate(processed_module_1_data):
        section_flowables = []
        step_title = md["step"].replace("_", " ").title()
        section_flowables.append(
            Paragraph(f"{section_index}. {step_title}", heading_style)
        )
        data_table = []
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and value:
                key_clean = key.replace("_", " ").title()
                if isinstance(value, list):
                    for file_path in value:
                        filename = os.path.basename(file_path)
                        display_name = clean_filename(filename)
                        attachment_positions[filename] = len(story) + len(
                            section_flowables
                        )
                        label_text = f"{key_clean}:"
                        link_text = display_name
                        data_table.append(
                            [
                                Paragraph(label_text, label_style),
                                Paragraph(link_text, link_style),
                            ]
                        )
                else:
                    data_table.append(
                        [
                            Paragraph(f"{key_clean}:", label_style),
                            Paragraph(str(value), normal_style),
                        ]
                    )
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
        if i < len(processed_module_1_data) - 1 or processed_module_2_data:
            section_flowables.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.gray,
                    spaceBefore=10,
                    spaceAfter=10,
                )
            )
        story.append(KeepTogether(section_flowables))
        section_index += 1

    # Satellite Details (Module 2) Section
    module_flowables = []
    module_flowables.append(
        Paragraph(f"{section_index}. Satellite Details (Module 2)", heading_style)
    )
    module_flowables.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.gray,
            spaceBefore=10,
            spaceAfter=10,
        )
    )
    story.append(KeepTogether(module_flowables))
    section_index += 1

    for i, md in enumerate(processed_module_2_data):
        section_flowables = []
        step_title = md["step"].replace("_", " ").title()
        section_flowables.append(
            Paragraph(f"{section_index}. {step_title}", heading_style)
        )
        data_table = []
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and value:
                key_clean = key.replace("_", " ").title()
                if isinstance(value, list):
                    for file_path in value:
                        filename = os.path.basename(file_path)
                        display_name = clean_filename(filename)
                        attachment_positions[filename] = len(story) + len(
                            section_flowables
                        )
                        label_text = f"{key_clean}:"
                        link_text = display_name
                        data_table.append(
                            [
                                Paragraph(label_text, label_style),
                                Paragraph(link_text, link_style),
                            ]
                        )
                else:
                    data_table.append(
                        [
                            Paragraph(f"{key_clean}:", label_style),
                            Paragraph(str(value), normal_style),
                        ]
                    )
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
        if i < len(processed_module_2_data) - 1:
            section_flowables.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.gray,
                    spaceBefore=10,
                    spaceAfter=10,
                )
            )
        story.append(KeepTogether(section_flowables))
        section_index += 1

    # Uploaded Documents Section (clickable links for both modules)
    uploaded_flowables = []
    uploaded_flowables.append(
        Paragraph(f"{section_index}. Uploaded Documents", heading_style)
    )
    doc_list = []
    for filename, _ in attachment_files:
        display_name = clean_filename(filename)
        attachment_positions[filename] = len(story) + len(uploaded_flowables)
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

    # Build the initial PDF with ReportLab
    logger.debug(f"Building PDF at {summary_pdf_path}")
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    logger.debug(f"PDF built. Checking if file exists: {summary_pdf_path}")
    if not os.path.exists(summary_pdf_path):
        logger.error(f"Summary PDF file does not exist: {summary_pdf_path}")
        raise FileNotFoundError(f"Summary PDF file not found: {summary_pdf_path}")
    if os.path.getsize(summary_pdf_path) == 0:
        logger.error(f"Summary PDF file is empty: {summary_pdf_path}")
        raise ValueError(f"Summary PDF file is empty: {summary_pdf_path}")

    # Use PyMuPDF to assemble the final PDF with working links
    logger.debug(f"Attempting to open PDF with PyMuPDF: {summary_pdf_path}")
    try:
        doc = fitz.open(summary_pdf_path)
    except fitz.FileDataError as e:
        logger.error(f"PyMuPDF FileDataError: {e}")
        raise ValueError(f"Invalid or corrupted PDF file: {summary_pdf_path}")
    except fitz.EmptyFileError as e:
        logger.error(f"PyMuPDF EmptyFileError: {e}")
        raise ValueError(f"PDF file is empty: {summary_pdf_path}")
    except Exception as e:
        logger.error(f"Unexpected PyMuPDF error: {e}")
        raise

    attachment_page_numbers = {}
    current_page = len(doc)

    # Add attachment pages
    for filename, file_path in attachment_files:
        absolute_path = os.path.abspath(file_path)
        if not os.path.exists(absolute_path):
            continue

        # Add separator page
        separator_page = doc.new_page(
            width=doc[0].rect.width, height=doc[0].rect.height
        )
        page_width = doc[0].rect.width
        display_name = clean_filename(filename)
        separator_page.insert_text(
            (
                page_width / 2
                - fitz.get_text_length("Attachment", fontname="helv", fontsize=14) / 2,
                100,
            ),
            "Attachment",
            fontname="helv",
            fontsize=14,
            color=(0, 0, 0),
        )
        separator_page.insert_text(
            (
                page_width / 2
                - fitz.get_text_length(display_name, fontname="helv", fontsize=12) / 2,
                120,
            ),
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
            try:
                convert(absolute_path, temp_pdf)
                src_doc = fitz.open(temp_pdf)
                doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            finally:
                if os.path.exists(temp_pdf):
                    os.unlink(temp_pdf)
        elif file_ext in [".jpg", ".png", ".jpeg", ".gif"]:
            img = Image.open(absolute_path)
            temp_pdf = tempfile.mktemp(suffix=".pdf")
            try:
                img_width, img_height = img.size
                c = canvas.Canvas(temp_pdf, pagesize=reportlab_letter)
                page_width, page_height = reportlab_letter
                scale = min(
                    (page_width - 72) / img_width, (page_height - 150) / img_height
                )
                c.drawImage(
                    absolute_path, 36, 150, img_width * scale, img_height * scale
                )
                c.save()
                src_doc = fitz.open(temp_pdf)
                doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            finally:
                if os.path.exists(temp_pdf):
                    os.unlink(temp_pdf)

    # Add links to both sections
    for filename in attachment_positions:
        if filename in attachment_page_numbers:
            display_name = clean_filename(filename)
            page_num = 0
            while page_num < len(doc):
                page = doc[page_num]
                instances = page.search_for(display_name)
                if instances:
                    for rect in instances:
                        page.insert_link(
                            {
                                "kind": fitz.LINK_GOTO,
                                "from": rect,
                                "to": fitz.Point(0, 0),
                                "page": attachment_page_numbers[filename],
                            }
                        )
                page_num += 1

    # Add back links
    for filename, page_num in attachment_page_numbers.items():
        if page_num < len(doc):
            page = doc[page_num]
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
    doc.save(final_pdf_path)
    doc.close()

    # Clean up the temporary summary PDF
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
        if os.path.exists(final_pdf_path):
            os.unlink(final_pdf_path)
        raise e
