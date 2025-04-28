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
    current_app,
)
from flask_login import login_required, current_user
from app import db
from app.models import Application, ModuleData, UploadedFile, ApplicationAssignment
from config import Config
import os
import tempfile
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as reportlab_letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, HRFlowable
from reportlab.pdfgen import canvas
from PIL import Image
import fitz  # PyMuPDF
from docx2pdf import convert

module_10 = Blueprint(
    "module_10", __name__, url_prefix="/module_10", template_folder="templates"
)

logo_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static/images/IN-SPACe_Logo.png"
)

STEPS = [
    "general_info",
    "space_object_part1",
    "space_object_part2",
    "undertaking",
    "annexure_a",
    "annexure_1_security",
    "annexure_2_ssa_satellite",
    "annexure_3_ssa_launch",
    "annexure_4_hosted_payload",
]

UPLOAD_FOLDER = Config.UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@module_10.route("/fill_step/<step>", methods=["GET", "POST"])
@login_required
def fill_step(step):
    if step not in STEPS and step != "summary":
        flash("Invalid step.", "error")
        return redirect(url_for("applicant.home"))

    app_id = request.args.get("application_id")
    if not app_id:
        flash("Application ID is required.", "error")
        return redirect(url_for("applicant.home"))

    application = Application.query.get_or_404(app_id)
    if application.user_id != current_user.id or (
        application.status != "Pending"
        and not application.editable
        and step != "summary"
    ):
        flash("Unauthorized or invalid application.", "error")
        return redirect(url_for("applicant.home"))

    # Ensure ModuleData exists for the current step
    module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_10", step=step
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=app_id, module_name="module_10", step=step, data={}
        )
        db.session.add(module_data)
        db.session.commit()

    existing_files = UploadedFile.query.filter_by(
        application_id=app_id, module_name="module_10", step=step
    ).all()

    if request.method == "POST":
        form_data = request.form.to_dict()
        if step == "undertaking":
            # Handle checkbox fields
            for decl in [
                "authorization_affirmation",
                "compliance_laws",
                "dst_guidelines",
                "records_submission",
                "data_guidelines",
                "national_security_data",
                "registration_termination",
                "submission_authorization",
                "conformance_laws",
            ]:
                form_data[decl] = decl in request.form
        else:
            # Handle file uploads for other steps
            file_fields = {
                "space_object_part2": ["consent_copy"],
                "annexure_a": ["kml_file"],
                "annexure_2_ssa_satellite": ["safety_report", "ground_segment_file"],
                "annexure_3_ssa_launch": ["hazardous_materials_file", "ground_station_file", "attachments"],
                "annexure_4_hosted_payload": [
                    "indian_agreement_copy",
                    "indian_operation_mechanism_file",
                    "non_indian_authorization_copy",
                    "non_indian_agreement_copy",
                    "non_indian_operation_mechanism_file",
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
                            if not os.path.exists(file_path):
                                current_app.logger.error(f"Failed to save file: {file_path}")
                                flash("Error saving file. Please try again.", "error")
                                return redirect(url_for("module_10.fill_step", step=step, application_id=app_id))
                            relative_path = os.path.join("Uploads", filename)
                            uploaded_file = UploadedFile(
                                application_id=app_id,
                                module_name="module_10",
                                step=step,
                                field_name=field,
                                filename=f.filename,
                                filepath=relative_path,
                            )
                            db.session.add(uploaded_file)
                            file_paths.append(relative_path)
                        form_data[field] = file_paths
                    else:
                        form_data[field] = module_data.data.get(field, [])

            # Handle dynamic fields for other steps
            if step == "space_object_part1":
                satellite_names = request.form.getlist("satellite_names")
                form_data["satellite_names"] = [name for name in satellite_names if name]
                form_data["payload_details"] = request.form.get("payload_details", "")
                form_data["owner_name"] = request.form.get("owner_name", "")
                form_data["contact_person"] = request.form.get("contact_person", "")
                form_data["owner_email"] = request.form.get("owner_email", "")
                form_data["owner_address"] = request.form.get("owner_address", "")
            elif step == "annexure_a":
                dissemination_entries = []
                for i in range(len(request.form.getlist("end_user_type"))):
                    entry = {
                        "end_user_type": request.form.getlist("end_user_type")[i],
                        "country_of_origin": request.form.getlist("country_of_origin")[i],
                        "entity_type": request.form.getlist("entity_type")[i],
                        "legal_name": request.form.getlist("legal_name")[i],
                        "brand_trade_name": request.form.getlist("brand_trade_name")[i],
                        "address": request.form.getlist("address")[i],
                        "project_name": request.form.getlist("project_name")[i],
                        "satellite_name": request.form.getlist("satellite_name")[i],
                        "kml_file": form_data.get("kml_file", []),
                        "area_sq_km": request.form.getlist("area_sq_km")[i],
                        "data_provision_type": request.form.getlist("data_provision_type")[i],
                        "acquisition_date": request.form.getlist("acquisition_date")[i],
                        "acquisition_time": request.form.getlist("acquisition_time")[i],
                        "orbit_path_row": request.form.getlist("orbit_path_row")[i],
                        "payload_sensor": request.form.getlist("payload_sensor")[i],
                        "dissemination_date": request.form.getlist("dissemination_date")[i],
                        "dissemination_time": request.form.getlist("dissemination_time")[i],
                    }
                    dissemination_entries.append(entry)
                form_data["dissemination_entries"] = dissemination_entries
            elif step == "annexure_1_security":
                directors = []
                for i in range(len(request.form.getlist("director_full_name"))):
                    directors.append({
                        "full_name": request.form.getlist("director_full_name")[i],
                        "position_held": request.form.getlist("director_position_held")[i],
                        "date_of_birth": request.form.getlist("director_date_of_birth")[i],
                        "parentage": request.form.getlist("director_parentage")[i],
                        "present_address": request.form.getlist("director_present_address")[i],
                        "permanent_address": request.form.getlist("director_permanent_address")[i],
                        "nationality": request.form.getlist("director_nationality")[i],
                        "passport_no": request.form.getlist("director_passport_no")[i],
                        "contact_details": request.form.getlist("director_contact_details")[i],
                    })
                form_data["directors"] = directors
                shareholders = []
                for i in range(len(request.form.getlist("shareholder_full_name"))):
                    shareholders.append({
                        "full_name": request.form.getlist("shareholder_full_name")[i],
                        "parentage": request.form.getlist("shareholder_parentage")[i],
                        "date_of_birth": request.form.getlist("shareholder_date_of_birth")[i],
                        "permanent_address": request.form.getlist("shareholder_permanent_address")[i],
                        "present_address": request.form.getlist("shareholder_present_address")[i],
                        "position_held": request.form.getlist("shareholder_position_held")[i],
                        "nationality": request.form.getlist("shareholder_nationality")[i],
                        "share_percentage": request.form.getlist("shareholder_share_percentage")[i],
                    })
                form_data["shareholders"] = shareholders
                form_data["owners_directors"] = request.form.getlist("owners_directors")
            elif step == "annexure_4_hosted_payload":
                form_data["indian_payload_names"] = request.form.getlist("indian_payload_names")
                form_data["non_indian_payload_names"] = request.form.getlist("non_indian_payload_names")

        module_data.data = form_data
        module_data.completed = True
        db.session.commit()

        # Check if all steps are completed
        all_completed = True
        for s in STEPS:
            step_data = ModuleData.query.filter_by(
                application_id=app_id, module_name="module_10", step=s
            ).first()
            if not step_data or not step_data.completed:
                all_completed = False
                break

        if all_completed:
            application.status = "Submitted"
            application.editable = False
            db.session.commit()
            flash("Application submitted successfully!", "success")

        if step == STEPS[-1]:
            return redirect(
                url_for("module_10.fill_step", step="summary", application_id=app_id)
            )
        next_step_idx = STEPS.index(step) + 1
        return redirect(
            url_for(
                "module_10.fill_step",
                step=STEPS[next_step_idx],
                application_id=app_id,
            )
        )

    if step == "summary":
        all_module_data = ModuleData.query.filter_by(
            application_id=app_id, module_name="module_10"
        ).all()
        all_uploaded_files = UploadedFile.query.filter_by(
            application_id=app_id, module_name="module_10"
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
            "module_10/summary.html",
            all_module_data=processed_module_data,
            all_uploaded_files=all_uploaded_files,
            application_id=app_id,
            application=application,
            existing_files=existing_files,
        )

    all_module_data = ModuleData.query.filter_by(
        application_id=app_id, module_name="module_10"
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

    template_map = {
        "general_info": "module_10/general_info_module10.html",
        "space_object_part1": "module_10/space_object_part1.html",
        "space_object_part2": "module_10/space_object_part2.html",
        "undertaking": "module_10/undertaking_module10.html",
        "annexure_a": "module_10/annexure_a_module10.html",
        "annexure_1_security": "module_10/annexure_1_security.html",
        "annexure_2_ssa_satellite": "module_10/annexure_2_ssa_satellite.html",
        "annexure_3_ssa_launch": "module_10/annexure_3_ssa_launch.html",
        "annexure_4_hosted_payload": "module_10/annexure_4_hosted_payload.html",
    }
    return render_template(
        template_map.get(step, f"module_10/{step}.html"),
        form_data=module_data.data,
        application_id=app_id,
        current_step=step,
        steps=STEPS,
        all_module_data=processed_module_data,
        application=application,
        existing_files=existing_files,
    )

@module_10.route("/save_undertaking/<int:application_id>", methods=["POST"])
@login_required
def save_undertaking(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id or application.status != "Pending":
        return (
            jsonify(
                {"status": "error", "message": "Unauthorized or already submitted"}
            ),
            403,
        )

    form_data = request.form.to_dict()
    for decl in [
        "authorization_affirmation",
        "compliance_laws",
        "dst_guidelines",
        "records_submission",
        "data_guidelines",
        "national_security_data",
        "registration_termination",
        "submission_authorization",
        "conformance_laws",
    ]:
        form_data[decl] = decl in request.form

    module_data = ModuleData.query.filter_by(
        application_id=application_id,
        module_name="module_10",
        step="undertaking",
    ).first()
    if not module_data:
        module_data = ModuleData(
            application_id=application_id,
            module_name="module_10",
            step="undertaking",
            data={},
        )
        db.session.add(module_data)

    module_data.data = form_data
    module_data.completed = True
    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Form saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@module_10.route("/submit_application/<int:application_id>", methods=["POST"])
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
        application_id=application_id, module_name="module_10"
    ).all()
    required_steps = STEPS
    completed_steps = [md.step for md in all_module_data if md.completed]
    if len(completed_steps) < len(required_steps) or not all(
        step in completed_steps for step in required_steps
    ):
        flash("Please complete all required steps before submitting.", "error")
        return redirect(
            url_for(
                "module_10.fill_step",
                step="undertaking",
                application_id=application_id,
            )
        )

    try:
        application.status = "Submitted"
        application.editable = False
        db.session.commit()
        flash("Application submitted successfully!", "success")
        return redirect(
            url_for("module_10.fill_step", step="summary", application_id=application_id)
        )
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting application: {str(e)}", "error")
        return redirect(
            url_for(
                "module_10.fill_step",
                step="undertaking",
                application_id=application_id,
            )
        )

@module_10.route("/download_pdf/<application_id>", methods=["GET"])
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
        flash("Unauthorized or invalid application.", "error")
        return redirect(url_for("applicant.home"))

    # Fetch module data
    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_10"
    ).all()
    processed_module_data = [
        {"step": md.step, "data": md.data.copy(), "completed": md.completed}
        for md in all_module_data
    ]

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
    story.append(Paragraph("Module 10 Application Summary", title_style))
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
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    story.append(
                        Paragraph(f"{key.replace('_', ' ').title()}:", label_style)
                    )
                    for file_path in value:
                        filename = os.path.basename(file_path)
                        attachment_positions[filename] = (len(story) + 1, f"• {filename}")
                        story.append(Paragraph(f"• {filename}", link_style))
                        attachment_files.append((filename, file_path))
                elif isinstance(value, list):
                    story.append(
                        Paragraph(f"{key.replace('_', ' ').title()}:", label_style)
                    )
                    for item in value:
                        if isinstance(item, dict):
                            for sub_key, sub_value in item.items():
                                story.append(
                                    Table(
                                        [
                                            [
                                                Paragraph(
                                                    f"{sub_key.replace('_', ' ').title()}:",
                                                    label_style
                                                ),
                                                Paragraph(str(sub_value), normal_style),
                                            ]
                                        ],
                                        colWidths=[150, 360],
                                    )
                                )
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
                    width="100%",
                    thickness=1,
                    color=colors.HexColor("#AED6F1"),
                    spaceAfter=0.2 * inch,
                )
            )

    # Build the summary PDF
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

    # Use PyMuPDF to assemble the final PDF with working links
    final_pdf = fitz.open()
    summary_pdf = fitz.open(summary_pdf_path)
    final_pdf.insert_pdf(summary_pdf)
    summary_pdf.close()

    # Dictionary to track attachment page numbers
    attachment_page_numbers = {}
    current_page = len(final_pdf)

    # Add attachment pages and track their positions
    for filename, file_path in attachment_files:
        absolute_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", file_path)
        )
        if not os.path.exists(absolute_path):
            current_app.logger.warning(f"File not found: {absolute_path}. Skipping in PDF generation.")
            continue

        # Add separator page
        separator_page = final_pdf.new_page(
            width=final_pdf[0].rect.width, height=final_pdf[0].rect.height
        )
        page_width = final_pdf[0].rect.width

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
            final_pdf.insert_pdf(src_doc)
            current_page += len(src_doc)
            src_doc.close()
        elif file_ext in [".doc", ".docx"]:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                convert(absolute_path, temp_pdf.name)
                src_doc = fitz.open(temp_pdf.name)
                final_pdf.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
                os.unlink(temp_pdf.name)
        elif file_ext in [".jpg", ".jpeg", ".png"]:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                img = Image.open(absolute_path)
                img_width, img_height = img.size
                aspect = img_height / img_width
                target_width = reportlab_letter[0] - 72
                target_height = target_width * aspect
                if target_height > reportlab_letter[1] - 72:
                    target_height = reportlab_letter[1] - 72
                    target_width = target_height / aspect
                c = canvas.Canvas(temp_pdf.name, pagesize=reportlab_letter)
                c.drawImage(
                    absolute_path,
                    (reportlab_letter[0] - target_width) / 2,
                    (reportlab_letter[1] - target_height) / 2,
                    width=target_width,
                    height=target_height,
                )
                c.showPage()
                c.save()
                src_doc = fitz.open(temp_pdf.name)
                final_pdf.insert_pdf(src_doc)
                current_page += len(src_doc)
                src_doc.close()
                os.unlink(temp_pdf.name)

    # Add links from summary to attachments
    for filename, (position, link_text) in attachment_positions.items():
        if filename in attachment_page_numbers:
            page_num = position // 40  # Estimate rows per page
            if page_num >= len(final_pdf):
                page_num = len(final_pdf) - 1

            page = final_pdf[page_num]

            # Search for the text on the page to get a more accurate position
            instances = page.search_for(link_text)
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
        if page_num < len(final_pdf):
            page = final_pdf[page_num]
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
    final_pdf.save(final_pdf_path)
    final_pdf.close()

    # Clean up temporary summary PDF
    os.unlink(summary_pdf_path)

    # Send the file
    response = send_file(
        final_pdf_path,
        as_attachment=True,
        download_name=f"module_10_application_{application_id}.pdf",
    )

    # Clean up final PDF after sending
    @response.call_on_close
    def cleanup():
        try:
            os.unlink(final_pdf_path)
        except Exception:
            pass

    return response

@module_10.route("/download_file/<int:file_id>", methods=["GET"])
@login_required
def download_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    application = Application.query.get_or_404(uploaded_file.application_id)
    assignment = ApplicationAssignment.query.filter_by(
        application_id=application.id
    ).first()
    allowed_users = [application.user_id]
    if assignment:
        allowed_users.extend(
            [assignment.primary_verifier_id, assignment.secondary_verifier_id]
        )

    if current_user.id not in allowed_users:
        flash("Unauthorized.", "error")
        return redirect(url_for("applicant.home"))

    file_path = uploaded_file.filepath
    if not os.path.exists(file_path):
        flash("File not found.", "error")
        return redirect(url_for("applicant.home"))

    return send_file(
        file_path,
        as_attachment=True,
        download_name=uploaded_file.filename,
    )

@module_10.route("/progress/<int:application_id>", methods=["GET"])
@login_required
def progress(application_id):
    application = Application.query.get_or_404(application_id)
    if application.user_id != current_user.id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    all_module_data = ModuleData.query.filter_by(
        application_id=application_id, module_name="module_10"
    ).all()
    progress = [
        {"step": md.step, "completed": md.completed}
        for md in all_module_data
        if md.step in STEPS
    ]
    completed_steps = sum(1 for p in progress if p["completed"])
    percentage = (completed_steps / len(STEPS)) * 100 if STEPS else 0

    return jsonify(
        {
            "status": "success",
            "progress": progress,
            "percentage": round(percentage, 2),
            "application_status": application.status,
        }
    )

@module_10.route("/create_application", methods=["POST"])
@login_required
def create_application():
    try:
        application = Application(
            user_id=current_user.id,
            module_name="module_10",
            status="Pending",
            editable=True,
        )
        db.session.add(application)
        db.session.commit()

        for step in STEPS:
            module_data = ModuleData(
                application_id=application.id,
                module_name="module_10",
                step=step,
                data={},
                completed=False,
            )
            db.session.add(module_data)
        db.session.commit()

        return jsonify(
            {
                "status": "success",
                "application_id": application.id,
                "redirect": url_for(
                    "module_10.fill_step",
                    step="general_info",
                    application_id=application.id,
                ),
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500