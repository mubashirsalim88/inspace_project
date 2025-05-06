from flask import Blueprint

chat = Blueprint("chat", __name__, template_folder="templates")

from . import routes