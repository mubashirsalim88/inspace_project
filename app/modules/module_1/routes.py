# app/modules/module_1/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, ApplicationAssignment
import subprocess
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from pypdf import PdfReader, PdfWriter
from docx2pdf import convert
import tempfile
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter as reportlab_letter
from PIL import Image
import io
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph, SimpleDocTemplate, Spacer, PageBreak, HRFlowable
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from datetime import datetime

module_1 = Blueprint(
    "module_1", __name__, url_prefix="/module_1", template_folder="templates"
)

logo_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static/images/IN-SPACe_Logo.png"
)

STEPS = [
    "applicant_identity",
    "entity_details",
    "management_ownership",
    "financial_credentials",
    "operational_contact",
    "declarations_submission",
]

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "uploads"
)
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
    if application.user_id != current_user.id or (
        application.status != "Pending" and not application.editable and step != "summary"
    ):
        return "Unauthorized or invalid application", 403

    module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_1", step=step
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=app_id, module_name="module_1", step=step, data={}
        )
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(
        application_id=app_id, module_name="module_1", step=step
    ).all()
    print(f"Step: {step}, Existing Files: {[f.filename for f in existing_files]}")

    if request.method == "POST" and step != "declarations_submission":
        form_data = request.form.to_dict()
        file_fields = {
            "entity_details": ["recognition_certificate"],
            "management_ownership": ["charter_document"],
            "financial_credentials": [
                "annual_report",
                "income_tax_returns",
                "gst_returns",
                "fdi_approval",
            ],
            "operational_contact": ["special_approvals_docs"],
            "declarations_submission": [
                "security_clearance_doc",
                "authorization_submission_doc",
                "official_seal",
            ],
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
                            filepath=relative_path,
                        )
                        db.session.add(uploaded_file)
                        file_paths.append(relative_path)
                    form_data[field] = file_paths
                    print(
                        f"Uploaded {field}: {[f.filename for f in files]} to {file_path}"
                    )
                else:
                    form_data[field] = module_data.data.get(field, [])
                    print(f"No new upload for {field}, retaining: {form_data[field]}")

        module_data.data = form_data
        module_data.completed = True
        db.session.commit()

        next_step_idx = STEPS.index(step) + 1
        if next_step_idx < len(STEPS):
            return redirect(
                url_for(
                    "module_1.fill_step",
                    step=STEPS[next_step_idx],
                    application_id=app_id,
                )
            )
        return redirect(
            url_for("module_1.fill_step", step="summary", application_id=app_id)
        )

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(
            application_id=app_id, module_name="module_1"
        ).all()
        processed_module_data = []
        for md in all_module_data:
            data_copy = md.data.copy()
            for key, value in data_copy.items():
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    data_copy[key] = [os.path.basename(doc) for doc in value]
            processed_module_data.append(
                {"step": md.step, "data": data_copy, "completed": md.completed}
            )
        return render_template(
            "module_1/summary.html",
            all_module_data=processed_module_data,
            application_id=app_id,
            application=application,
        )

    all_module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_1"
    ).all()
    processed_module_data = []
    for md in all_module_data:
        data_copy = md.data.copy()
        for key, value in data_copy.items():
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                data_copy[key] = [os.path.basename(doc) for doc in value]
        processed_module_data.append(
            {"step": md.step, "data": data_copy, "completed": md.completed}
        )

    template_map = {"declarations_submission": "module_1/declarations_submission.html"}
    return render_template(
        template_map.get(step, f"module_1/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files,
    )

@module_1.route("/save_declarations/<int:application_id>", methods=["POST"])
@login_required
def save_declarations(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return (
            jsonify(
                {"status": "error", "message": "Unauthorized or already submitted"}
            ),
            403,
        )

    form_data = request.form.to_dict()
    file_fields = [
        "security_clearance_doc",
        "authorization_submission_doc",
        "official_seal",
    ]
    for field in file_fields:
        files = request.files.getlist(field)
        if files and files[0].filename:
            file_paths = []
            for f in files:
                filename = (
                    f"{application_id}_declarations_submission_{field}_{f.filename}"
                )
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(file_path)
                relative_path = os.path.join("uploads", filename)
                uploaded_file = UploadedFile(
                    application_id=application_id,
                    module_name="module_1",
                    step="declarations_submission",
                    field_name=field,
                    filename=f.filename,
                    filepath=relative_path,
                )
                db.session.add(uploaded_file)
                file_paths.append(relative_path)
            form_data[field] = file_paths
        else:
            form_data[field] = form_data.get(
                field, []
            )  # Retain existing if no new upload

    module_data = ModuleData.query.filter_by(
        application_id=application_id,
        module_name="module_1",
        step="declarations_submission",
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=application_id,
            module_name="module_1",
            step="declarations_submission",
            data={},
        )
        db.session.add(module_data)

    # Convert checkbox values to booleans
    for decl in [
        "compliance_laws",
        "accuracy_info",
        "criminal_declaration",
        "financial_stability",
        "change_notification",
    ]:
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
    if application.status != "Pending" and not application.editable:
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
        application.editable = False
        db.session.commit()
        flash("Application submitted successfully!", "success")
        return redirect(url_for("module_1.fill_step", step="summary", application_id=application_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(url_for("module_1.fill_step", step="declarations_submission", application_id=application_id))

@module_1.route("/download_pdf/<application_id>", methods=["GET"])
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
        application_id=application_id, module_name="module_1"
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

        # Create custom styles for a more professional look
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontSize=18,
            textColor=colors.HexColor("#1A5276"),  # Dark blue color
            spaceAfter=16,
            alignment=1,  # Center alignment
        )

        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#2874A6"),  # Medium blue color
            spaceBefore=12,
            spaceAfter=6,
            borderPadding=(0, 0, 1, 0),  # Bottom padding
            borderWidth=0,
            borderColor=colors.HexColor("#AED6F1"),  # Light blue
            borderRadius=None,
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
            textColor=colors.HexColor("#34495E"),  # Dark gray
            fontName="Helvetica-Bold",
        )

        attachment_style = ParagraphStyle(
            "AttachmentLink",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#2E86C1"),  # Bright blue for links
            fontName="Helvetica",
        )

        # Step 1: Generate the summary PDF without links initially
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=72,
            bottomMargin=36,
        )

        # Define a header and footer function
        def header_footer(canvas, doc):
            canvas.saveState()

            # Define width and height
            width, height = letter

            # Add company logo
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

            # Add header line
            canvas.setStrokeColor(colors.HexColor("#AED6F1"))
            canvas.line(36, height - 60, width - 36, height - 60)

            # Add application ID in the header right side
            canvas.setFont("Helvetica", 10)
            canvas.setFillColor(colors.HexColor("#34495E"))
            canvas.drawRightString(
                width - 36, height - 36, f"Application ID: {application_id}"
            )

            # Add footer
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.gray)
            canvas.drawCentredString(width / 2, 20, "CONFIDENTIAL")
            canvas.drawRightString(width - 36, 20, "Page %d" % doc.page)

            # Add footer line
            canvas.setStrokeColor(colors.HexColor("#AED6F1"))
            canvas.line(36, 30, width - 36, 30)

            canvas.restoreState()

        story = []

        # Add title
        story.append(Paragraph(f"Application Summary", title_style))
        story.append(Spacer(1, 0.25 * inch))

        # Add application metadata in a stylish box
        metadata_content = [
            ["Application ID:", application_id],
            [
                "Date Submitted:",
                (
                    application.submitted_date.strftime("%B %d, %Y")
                    if hasattr(application, "submitted_date")
                    and application.submitted_date
                    else "N/A"
                ),
            ],
            ["Status:", application.status],
            [
                "Applicant:",
                (
                    f"{current_user.first_name} {current_user.last_name}"
                    if hasattr(current_user, "first_name")
                    and hasattr(current_user, "last_name")
                    else current_user.username
                ),
            ],
        ]

        metadata_table = Table(metadata_content, colWidths=[120, 300])
        metadata_table.setStyle(
            TableStyle(
                [
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
                ]
            )
        )

        story.append(metadata_table)
        story.append(Spacer(1, 0.3 * inch))

        # Add table of contents header
        story.append(Paragraph("Table of Contents", heading_style))
        toc_items = []
        for i, md in enumerate(processed_module_data):
            toc_items.append([f"{i+1}.", md["step"].replace("_", " ").title()])

        toc_table = Table(toc_items, colWidths=[30, 390])
        toc_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                    ("LEFTPADDING", (1, 0), (1, -1), 5),
                ]
            )
        )

        story.append(toc_table)
        story.append(Spacer(1, 0.3 * inch))

        # Add a divider before content
        story.append(
            HRFlowable(
                width="100%",
                thickness=1,
                color=colors.HexColor("#AED6F1"),
                spaceAfter=0.2 * inch,
            )
        )

        # Dictionary to store attachment files and their positions in the summary
        attachment_files = []
        attachment_positions = {}

        # Add summary content with improved formatting
        for i, md in enumerate(processed_module_data):
            story.append(
                Paragraph(
                    f"{i+1}. {md['step'].replace('_', ' ').title()}", heading_style
                )
            )

            data_items = []
            for key, value in md["data"].items():
                if key not in ["documents", "document_names"] and value:
                    if isinstance(value, list):
                        story.append(
                            Paragraph(f"{key.replace('_', ' ').title()}:", label_style)
                        )
                        for idx, file_path in enumerate(value):
                            filename = os.path.basename(file_path)
                            attachment_positions[filename] = len(story)
                            story.append(
                                Paragraph(
                                    f"• Attachment: {filename} (Click to view)",
                                    attachment_style,
                                )
                            )
                            attachment_files.append((filename, file_path))
                    else:
                        data_items.append(
                            [
                                Paragraph(
                                    f"{key.replace('_', ' ').title()}:", label_style
                                ),
                                Paragraph(f"{value}", normal_style),
                            ]
                        )

            if data_items:
                data_table = Table(data_items, colWidths=[150, 360])
                data_table.setStyle(
                    TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (0, -1), 0),
                            ("RIGHTPADDING", (0, 0), (0, -1), 10),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                story.append(data_table)

            story.append(Spacer(1, 0.2 * inch))
            if i < len(processed_module_data) - 1:
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=colors.HexColor("#D6EAF8"),
                        spaceBefore=0.1 * inch,
                        spaceAfter=0.1 * inch,
                    )
                )

        # Build the initial summary PDF
        doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

        # Step 2: Add attachments and create final PDF with links
        writer = PdfWriter()
        summary_pdf = PdfReader(pdf_path)
        for page in summary_pdf.pages:
            writer.add_page(page)

        page_height = reportlab_letter[1]
        attachment_destinations = {}

        for filename, file_path in attachment_files:
            absolute_file_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "..", file_path
                )
            )

            if not os.path.exists(absolute_file_path):
                print(f"File not found: {absolute_file_path}")
                continue

            attachment_page = len(writer.pages)
            attachment_destinations[filename] = attachment_page

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as separator_file:
                c = canvas.Canvas(separator_file.name, pagesize=reportlab_letter)
                width, height = reportlab_letter

                logo_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "static/images/company_logo.png",
                )
                if os.path.exists(logo_path):
                    c.drawImage(
                        logo_path,
                        36,
                        height - 54,
                        width=120,
                        height=40,
                        preserveAspectRatio=True,
                    )
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
                        c.rect(
                            x_pos - 5,
                            y_pos - 5,
                            display_width + 10,
                            display_height + 10,
                            stroke=1,
                            fill=0,
                        )
                        c.drawImage(
                            absolute_file_path,
                            x_pos,
                            y_pos,
                            width=display_width,
                            height=display_height,
                        )

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

        # Create links from summary to attachments
        for filename, page_position in attachment_positions.items():
            if filename not in attachment_destinations:
                continue

            items_per_page = 25
            page_index = min(page_position // items_per_page, len(summary_pdf.pages) - 1)
            page = writer.pages[page_index]
            position_on_page = page_position % items_per_page
            y_offset = page_height - 180 - (position_on_page * 20)

            action = DictionaryObject(
                {
                    NameObject("/S"): NameObject("/GoTo"),
                    NameObject("/D"): ArrayObject(
                        [NumberObject(attachment_destinations[filename]), NameObject("/Fit")]
                    ),
                }
            )

            link = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Link"),
                    NameObject("/Rect"): ArrayObject(
                        [
                            NumberObject(60),
                            NumberObject(y_offset - 10),
                            NumberObject(450),
                            NumberObject(y_offset + 10),
                        ]
                    ),
                    NameObject("/A"): action,
                    NameObject("/Border"): ArrayObject(
                        [NumberObject(0), NumberObject(0), NumberObject(0)]
                    ),
                }
            )

            if NameObject("/Annots") not in page:
                page[NameObject("/Annots")] = ArrayObject()
            annots = page[NameObject("/Annots")]
            annots.append(writer._add_object(link))

        # Add back button on each attachment page
        for filename, page_num in attachment_destinations.items():
            page = writer.pages[page_num]
            return_action = DictionaryObject(
                {
                    NameObject("/S"): NameObject("/GoTo"),
                    NameObject("/D"): ArrayObject(
                        [NumberObject(0), NameObject("/Fit")]
                    ),
                }
            )

            back_link = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Link"),
                    NameObject("/Rect"): ArrayObject(
                        [
                            NumberObject(32),
                            NumberObject(page_height - 92),
                            NumberObject(137),
                            NumberObject(page_height - 72),
                        ]
                    ),
                    NameObject("/A"): return_action,
                    NameObject("/Border"): ArrayObject(
                        [NumberObject(0), NumberObject(0), NumberObject(0)]
                    ),
                }
            )

            if NameObject("/Annots") not in page:
                page[NameObject("/Annots")] = ArrayObject()
            annots = page[NameObject("/Annots")]
            annots.append(writer._add_object(back_link))

        # Write the final PDF
        with open(pdf_path, "wb") as f:
            writer.write(f)

        # Serve the PDF for download
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"application_{application_id}_summary.pdf",
            mimetype="application/pdf",
        )

@module_1.route("/start_application", methods=["GET", "POST"])
@login_required
def start_application():
    if request.method == "POST":
        application = Application(user_id=current_user.id, status="Pending")
        db.session.add(application)
        db.session.commit()
        return redirect(
            url_for("module_1.fill_step", step=STEPS[0], application_id=application.id)
        )
    return render_template("module_1/start_application.html")

@module_1.route("/download_file/<int:file_id>")
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    application = Application.query.get_or_404(uploaded_file.application_id)
    
    # Allow Applicant or Verifiers assigned to the application
    assignment = ApplicationAssignment.query.filter_by(application_id=application.id).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend([assignment.primary_verifier_id, assignment.secondary_verifier_id])
    
    if current_user.id not in allowed_users:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))

    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath)
    if not os.path.exists(full_path):
        flash(f"File not found: {uploaded_file.filename}", "error")
        return redirect(url_for("applicant.home"))
    
    return send_file(
        full_path,
        as_attachment=True,
        download_name=uploaded_file.filename
    )