# app/modules/module_2/routes.py
from flask import Blueprint, render_template
from flask_login import login_required

module_2 = Blueprint("module_2", __name__, url_prefix="/module_2", template_folder="templates")

@module_2.route("/example")
def example():
    return "This is Module 2"

@module_2.route("/fill_step/<step>")
@login_required
def fill_step(step):
    # Placeholder for Module 2 steps (e.g., Satellite Communication form)
    steps = ["applicant_details", "technical_details"]  # Customize as needed
    if step not in steps:
        return "Invalid step", 404
    return render_template("module_2/fill_step.html", step=step)