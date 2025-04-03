# app/pdf_generator.py
import os
import subprocess
import shutil
import logging
from flask import send_file, abort

logger = logging.getLogger(__name__)
TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
if not os.path.exists(TEMP_FOLDER):
    os.makedirs(TEMP_FOLDER)

def generate_pdf(application_id, module_name, module_data, uploaded_files, applicant_name, submission_date):
    """
    Generate a PDF for the given application and module.
    
    Args:
        application_id (int): The ID of the application.
        module_name (str): Name of the module (e.g., "Module_1").
        module_data (list): List of ModuleData objects.
        uploaded_files (list): List of UploadedFile objects.
        applicant_name (str): Name of the applicant.
        submission_date (str): Date of submission.
    
    Returns:
        Flask response with the generated PDF.
    """
    # Typst content generation
    typst_content = """
    #set page(margin: 1in, numbering: "1")
    #set text(font: "Arial", size: 12pt)
    #show heading: set text(size: 16pt, weight: "bold")

    = Application {{ application_id }} - {{ module_name }} Summary
    *Applicant:* {{ applicant_name }}  
    *Submission Date:* {{ submission_date }}  
    #outline(title: "Table of Contents", indent: 1em)
    """
    typst_content = typst_content.replace("{{ application_id }}", str(application_id))
    typst_content = typst_content.replace("{{ module_name }}", module_name)
    typst_content = typst_content.replace("{{ applicant_name }}", applicant_name)
    typst_content = typst_content.replace("{{ submission_date }}", submission_date)

    for md in module_data:
        step_title = md.step.replace('_', ' ').title()
        typst_content += f"\n== {step_title}\n"
        for key, value in md.data.items():
            key_title = key.replace('_', ' ').title()
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                typst_content += f"- *{key_title}*: "
                if value:
                    typst_content += ", ".join([f"[{os.path.basename(v)}](#ref('appendix'))" for v in value])
                else:
                    typst_content += "None uploaded"
                typst_content += "\n"
            else:
                typst_content += f"- *{key_title}*: {str(value) if value is not None else 'N/A'}\n"

    typst_content += "\n#pagebreak()\n= Appendix: Uploaded Files <appendix>\n"
    valid_pdf_files = []
    base_path = os.path.dirname(os.path.abspath(__file__))
    for i, uf in enumerate(uploaded_files, 1):
        full_path = os.path.abspath(os.path.join(base_path, uf.filepath))
        if os.path.exists(full_path) and full_path.lower().endswith(".pdf"):
            valid_pdf_files.append((uf, full_path))
            typst_content += f"- {uf.field_name.replace('_', ' ').title()}: [{uf.filename}]\n"
        else:
            logger.warning(f"Skipping {full_path}: Not found or not a PDF")
            typst_content += f"- {uf.field_name.replace('_', ' ').title()}: {uf.filename} (Not available)\n"

    # Write Typst file
    typst_file = os.path.join(TEMP_FOLDER, f"{module_name.lower().replace(' ', '_')}_{application_id}.typ")
    try:
        with open(typst_file, "w", encoding="utf-8") as f:
            f.write(typst_content)
        logger.debug(f"Typst file written to {typst_file}")
    except IOError as e:
        logger.error(f"Failed to write Typst file {typst_file}: {e}")
        abort(500, f"Failed to generate PDF: {e}")

    # Compile Typst to PDF
    base_pdf = os.path.join(TEMP_FOLDER, f"{module_name.lower().replace(' ', '_')}_{application_id}.pdf")
    try:
        if not shutil.which("typst"):
            raise FileNotFoundError("Typst is not installed or not in PATH")
        subprocess.run(["typst", "compile", typst_file, base_pdf], check=True, shell=False)
        if not os.path.exists(base_pdf):
            raise FileNotFoundError(f"Typst compilation succeeded but {base_pdf} was not created")
        logger.debug(f"Typst compiled to {base_pdf}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Typst compilation failed for {typst_file}: {e}")
        if os.path.exists(typst_file):
            os.remove(typst_file)
        abort(500, f"PDF generation failed: {e}")

    # Merge with uploaded PDFs
    final_pdf = os.path.join(TEMP_FOLDER, f"{module_name.lower().replace(' ', '_')}_final_{application_id}.pdf")
    pdf_files = [base_pdf] + [path for _, path in valid_pdf_files]
    try:
        if not shutil.which("pdftk"):
            raise FileNotFoundError("PDFtk is not installed or not in PATH")
        if len(pdf_files) > 1:
            cmd = ["pdftk"] + pdf_files + ["cat", "output", final_pdf]
            subprocess.run(cmd, check=True, shell=False)
            output_file = final_pdf
            logger.debug(f"PDFs merged into {final_pdf}")
        else:
            output_file = base_pdf
            logger.debug("No uploaded PDFs to merge, using base PDF")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"PDF merging failed: {e}")
        for file in [typst_file, base_pdf]:
            if os.path.exists(file):
                os.remove(file)
        abort(500, f"PDF merging failed: {e}")

    # Send file and clean up
    try:
        response = send_file(output_file, as_attachment=True, download_name=f"{module_name}_Application_{application_id}.pdf")
        logger.info(f"PDF successfully generated and sent for application {application_id}")
        return response
    finally:
        for file in [typst_file, base_pdf, final_pdf]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logger.debug(f"Cleaned up temporary file: {file}")
                except OSError as e:
                    logger.warning(f"Failed to remove temporary file {file}: {e}")