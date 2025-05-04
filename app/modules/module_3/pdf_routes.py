# app/modules/module_3/pdf_routes.py
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

module_3_pdf = Blueprint(
    "module_3_pdf", __name__, url_prefix="/module_3", template_folder="templates"
)

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def clean_filename(filename):
    """Convert raw filename to a clean display name."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'^\d+_?', '', name)
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

@module_3_pdf.route("/download_pdf/<application_id>", methods=["GET"])
@login_required
def download_pdf(application_id):
    application = Application.query.get_or_404(application_id)

    # Authorization check
    assignment = ApplicationAssignment.query.filter_by(
        application_id=application_id
    ).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend(
            [assignment.primary_verifier_id, assignment.secondary_verifier_id]
        )

    if current_user.id not in allowed_users or application.status not in [
        "Submitted",
        "Under Review",
    ]:
        return "Unauthorized or invalid application", 403

    # Fetch Module 3 data
    module_3_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_3"
    ).all()
    processed_module_3_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in module_3_data
        if md.step.lower() != "summary"  # Exclude 'summary' step
    ]

    # Fetch uploaded files for Module 3
    uploaded_files_module_3 = UploadedFile.query.filter_by(
        application_id=application_id, module_name="module_3"
    ).all()
    attachment_files = [
        (f.filename, os.path.join(os.path.dirname(__file__), "..", f.filepath))
        for f in uploaded_files_module_3
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", f.filepath))
    ]

    # Create temporary files for Module 3 PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as summary_file:
        summary_pdf_path = summary_file.name
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_file:
        final_pdf_path = final_file.name

    # Styles setup (aligned with Modules 1 and 2)
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

    # Track attachment positions for Module 3
    attachment_positions = {}

    # PDF Document setup for Module 3
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

    # Combined Application Details and Table of Contents Page
    summary_flowables = []
    summary_flowables.append(Paragraph("Module 3: Non-Indian Satellite Authorization Summary", title_style))
    summary_flowables.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray, spaceBefore=15, spaceAfter=15))
    summary_data = [
        [Paragraph("Application ID:", label_style), Paragraph(str(application_id), detail_style)],
        [Paragraph("Status:", label_style), Paragraph(application.status, detail_style)],
        [Paragraph("Applicant:", label_style), Paragraph(current_user.username, detail_style)],
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
    # Add Module 3 TOC entries
    for md in processed_module_3_data:
        toc_items.append([f"{toc_index}.", md["step"].replace("_", " ").title(), ""])
        toc_index += 1
    toc_items.append(["", "Uploaded Documents (Module 3)", ""])
    toc_table = Table(toc_items, colWidths=[30, 360, 50])
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

    # Module 3 Section
    section_index = 1
    for i, md in enumerate(processed_module_3_data):
        section_flowables = []
        step_title = md["step"].replace("_", " ").title()
        section_flowables.append(Paragraph(f"{section_index}. {step_title}", heading_style))
        data_table = []
        for key, value in md["data"].items():
            if key not in ["documents", "document_names"] and value:
                key_clean = key.replace("_", " ").title()
                if isinstance(value, list):
                    for file_path in value:
                        filename = os.path.basename(file_path)
                        display_name = clean_filename(filename)
                        attachment_positions[filename] = len(story) + len(section_flowables)
                        label_text = f"{key_clean}:"
                        link_text = display_name
                        data_table.append([
                            Paragraph(label_text, label_style),
                            Paragraph(link_text, link_style),
                        ])
                else:
                    data_table.append([
                        Paragraph(f"{key_clean}:", label_style),
                        Paragraph(str(value), normal_style),
                    ])
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
        if i < len(processed_module_3_data) - 1:
            section_flowables.append(
                HRFlowable(
                    width="100%", thickness=0.5, color=colors.gray, spaceBefore=10, spaceAfter=10
                )
            )
        story.append(KeepTogether(section_flowables))
        section_index += 1

    # Uploaded Documents Section (Module 3 only)
    uploaded_flowables = []
    uploaded_flowables.append(Paragraph("Uploaded Documents (Module 3)", heading_style))
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

    # Build the initial Module 3 PDF with ReportLab
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

    # Use PyMuPDF to add attachments and links
    final_doc = fitz.open(summary_pdf_path)

    # Track page count for Module 3 content
    module_3_page_count = len(final_doc)

    # Add Module 3 attachment pages
    attachment_page_numbers = {}
    current_page = module_3_page_count  # Start after Module 3 content

    for filename, file_path in attachment_files:
        absolute_path = os.path.abspath(file_path)
        if not os.path.exists(absolute_path):
            logger.warning(f"Attachment file not found: {absolute_path}")
            continue

        # Add separator page
        separator_page = final_doc.new_page(
            width=final_doc[0].rect.width, height=final_doc[0].rect.height
        )
        page_width = final_doc[0].rect.width
        display_name = clean_filename(filename)
        separator_page.insert_text(
            (page_width / 2 - fitz.get_text_length("Attachment (Module 3)", fontname="helv", fontsize=14) / 2, 100),
            "Attachment (Module 3)",
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

        attachment_page_numbers[filename] = current_page
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
        elif file_ext == ".docx":
            temp_pdf = tempfile.mktemp(suffix=".pdf")
            try:
                convert(absolute_path, temp_pdf)
                src_doc = fitz.open(temp_pdf)
                final_doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            except Exception as e:
                logger.error(f"Error converting DOCX {absolute_path}: {e}")
            finally:
                if os.path.exists(temp_pdf):
                    os.unlink(temp_pdf)
        elif file_ext in [".jpg", ".png", ".jpeg", ".gif"]:
            try:
                img = Image.open(absolute_path)
                temp_pdf = tempfile.mktemp(suffix=".pdf")
                img_width, img_height = img.size
                c = canvas.Canvas(temp_pdf, pagesize=reportlab_letter)
                page_width, page_height = reportlab_letter
                scale = min((page_width - 72) / img_width, (page_height - 150) / img_height)
                c.drawImage(absolute_path, 36, 150, img_width * scale, img_height * scale)
                c.save()
                src_doc = fitz.open(temp_pdf)
                final_doc.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
            except Exception as e:
                logger.error(f"Error processing image {absolute_path}: {e}")
            finally:
                if os.path.exists(temp_pdf):
                    os.unlink(temp_pdf)

    # Add links for Module 3
    for filename in attachment_positions:
        if filename in attachment_page_numbers:
            display_name = clean_filename(filename)
            page_num = 0
            while page_num < module_3_page_count:  # Only in Module 3 content pages
                page = final_doc[page_num]
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

    # Add back links for Module 3 attachments
    for filename, page_num in attachment_page_numbers.items():
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
    final_doc.save(final_pdf_path)
    final_doc.close()

    # Clean up temporary files
    if os.path.exists(summary_pdf_path):
        os.unlink(summary_pdf_path)

    # Serve the file
    try:
        response = send_file(
            final_pdf_path,
            as_attachment=True,
            download_name=f"application_{application_id}_module_3_summary.pdf",
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

@module_3_pdf.route("/test_pdf")
def test_pdf():
    return "module_3_pdf Blueprint is working!"