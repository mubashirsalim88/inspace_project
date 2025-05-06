from flask import Blueprint

notification = Blueprint("notification", __name__, template_folder="templates")

from . import routes