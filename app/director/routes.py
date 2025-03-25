# app/director/routes.py
from flask import Blueprint

director = Blueprint("director", __name__, url_prefix="/director", template_folder="templates")

# Placeholder for now
@director.route("/review")
def review():
    return "Director review dashboard - TBD", 501