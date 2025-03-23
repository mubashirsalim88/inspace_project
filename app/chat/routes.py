# app/chat/routes.py
from flask import Blueprint

chat = Blueprint("chat", __name__)

@chat.route("/example")
def example():
    return "This is Chat"