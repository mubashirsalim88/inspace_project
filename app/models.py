# app/models.py
from flask_login import UserMixin
from app import db
from datetime import datetime

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)
    name = db.Column(db.String(100), nullable=False)
    # Relationships
    applications = db.relationship("Application", backref="user", lazy=True)
    assigned_applications = db.relationship("ApplicationAssignment", foreign_keys="ApplicationAssignment.assigner_id", backref="assigner", lazy=True)
    primary_verifications = db.relationship("ApplicationAssignment", foreign_keys="ApplicationAssignment.primary_verifier_id", backref="primary_verifier", lazy=True)
    secondary_verifications = db.relationship("ApplicationAssignment", foreign_keys="ApplicationAssignment.secondary_verifier_id", backref="secondary_verifier", lazy=True)
    sent_messages = db.relationship("ChatMessage", foreign_keys="ChatMessage.sender_id", backref="sender", lazy=True)
    received_messages = db.relationship("ChatMessage", foreign_keys="ChatMessage.receiver_id", backref="receiver", lazy=True)
    notifications = db.relationship("Notification", backref="user", lazy=True)

class Application(db.Model):
    __tablename__ = "applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(50), default="Pending", nullable=False)  # Increased from 20 to 50
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    editable = db.Column(db.Boolean, default=False)  # Added for edit permission
    module_data = db.relationship("ModuleData", backref="application", lazy=True)
    assignment = db.relationship("ApplicationAssignment", uselist=False, cascade="all, delete-orphan")
    files = db.relationship("UploadedFile", backref="application", lazy=True, cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="application", lazy=True)
    comments = db.Column(db.Text, nullable=True)

class ModuleData(db.Model):
    __tablename__ = "module_data"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    module_name = db.Column(db.String(50), nullable=False)
    step = db.Column(db.String(50), nullable=False)
    data = db.Column(db.JSON, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    abandoned = db.Column(db.Boolean, default=False)

class ApplicationAssignment(db.Model):
    __tablename__ = "application_assignments"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    assigner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    primary_verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    secondary_verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

class UploadedFile(db.Model):
    __tablename__ = "uploaded_files"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    module_name = db.Column(db.String(50), nullable=False)
    step = db.Column(db.String(50), nullable=False)
    field_name = db.Column(db.String(50), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(200), nullable=False)

class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    notifications = db.relationship("Notification", backref="message", lazy=True)

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("chat_messages.id"), nullable=True)  # Nullable for non-chat notifications
    content = db.Column(db.Text, nullable=True)  # For custom messages like "Edit enabled"
    read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)