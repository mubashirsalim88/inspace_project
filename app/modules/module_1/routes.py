# app/modules/module_1/routes.py
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_file,
    flash,
    abort,
)
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
from reportlab.platypus import (
    Table,
    TableStyle,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    PageBreak,
    HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from datetime import datetime
import fitz  # PyMuPDF

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
        application.status != "Pending"
        and not application.editable
        and step != "summary"
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

    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_1"
    ).all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(
        step in completed_steps for step in required_steps
    ):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(
            url_for(
                "module_1.fill_step",
                step="declarations_submission",
                application_id=application_id,
            )
        )

    try:
        application.status = "Submitted"
        application.editable = False
        db.session.commit()
        flash("Application submitted successfully!", "success")
        return redirect(
            url_for("module_1.fill_step", step="summary", application_id=application_id)
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(
            url_for(
                "module_1.fill_step",
                step="declarations_submission",
                application_id=application_id,
            )
        )


from flask import send_file
from flask_login import login_required, current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as reportlab_letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, HRFlowable
from reportlab.pdfgen import canvas


@module_1.route("/download_pdf/<application_id>", methods=["GET"])
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

    # Fetch module data
    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_1"
    ).all()
    processed_module_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in all_module_data
    ]

    # Create temporary files with NamedTemporaryFile
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
            os.path.dirname(os.path.abspath(__file__)), "static/images/company_logo.png"
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
        canvas.drawRightString(width - 36, 20, f"Page {doc.page}")
        canvas.line(36, 30, width - 36, 30)
        canvas.restoreState()

    story = []
    story.append(Paragraph("Application Summary", title_style))
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

    # Add links from summary to attachments
    for filename, (position, link_text) in attachment_positions.items():
        if filename in attachment_page_numbers:
            page_num = position // 40  # Estimate rows per page
            if page_num >= len(doc):
                page_num = len(doc) - 1

            page = doc[page_num]

            # Search for the text on the page to get a more accurate position
            instances = page.search_for(f"• {filename}")
            if instances:
                rect = instances[0]
                page.insert_link(
                    {
                        "kind": fitz.LINK_GOTO,
                        "from": rect,
                        "to": fitz.Point(0, 0),
                        "page": attachment_page_numbers[filename],
                    }
                )

    # Add back links from attachments to summary
    for filename, page_num in attachment_page_numbers.items():
        if page_num < len(doc):
            page = doc[page_num]
            instances = page.search_for("← Back to Summary")
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
                print(f"Error deleting {final_pdf_path}: {e}")
        return response
    except Exception as e:
        os.unlink(final_pdf_path)
        raise e


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
    assignment = ApplicationAssignment.query.filter_by(
        application_id=application.id
    ).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend(
            [assignment.primary_verifier_id, assignment.secondary_verifier_id]
        )

    if current_user.id not in allowed_users:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home"))

    full_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", uploaded_file.filepath
    )
    if not os.path.exists(full_path):
        flash(f"File not found: {uploaded_file.filename}", "error")
        return redirect(url_for("applicant.home"))

    return send_file(
        full_path, as_attachment=True, download_name=uploaded_file.filename
    )