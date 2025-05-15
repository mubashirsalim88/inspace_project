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
    applications = db.relationship("Application", back_populates="user", lazy=True)
    assigned_applications = db.relationship("ApplicationAssignment", foreign_keys="ApplicationAssignment.assigner_id", back_populates="assigner", lazy=True)
    primary_verifications = db.relationship("ApplicationAssignment", foreign_keys="ApplicationAssignment.primary_verifier_id", back_populates="primary_verifier", lazy=True)
    secondary_verifications = db.relationship("ApplicationAssignment", foreign_keys="ApplicationAssignment.secondary_verifier_id", back_populates="secondary_verifier", lazy=True)
    sent_messages = db.relationship("ChatMessage", foreign_keys="ChatMessage.sender_id", back_populates="sender", lazy=True)
    received_messages = db.relationship("ChatMessage", foreign_keys="ChatMessage.receiver_id", back_populates="receiver", lazy=True)
    notifications = db.relationship("Notification", back_populates="user", lazy=True)
    edit_requests = db.relationship("EditRequest", foreign_keys="EditRequest.verifier_id", back_populates="verifier", lazy=True)
    audit_logs = db.relationship("AuditLog", back_populates="user", lazy=True)

class Application(db.Model):
    __tablename__ = "applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(50), default="Pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    editable = db.Column(db.Boolean, default=False)
    comments = db.Column(db.Text, nullable=True)
    # Relationships
    user = db.relationship("User", back_populates="applications")
    module_data = db.relationship("ModuleData", back_populates="application", lazy=True)
    assignment = db.relationship("ApplicationAssignment", uselist=False, back_populates="application", cascade="all, delete-orphan")
    files = db.relationship("UploadedFile", back_populates="application", lazy=True, cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", back_populates="application", lazy=True)
    edit_requests = db.relationship("EditRequest", back_populates="application", lazy=True, cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", back_populates="application", lazy=True, cascade="all, delete-orphan")

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
    # Relationship
    application = db.relationship("Application", back_populates="module_data")

class ApplicationAssignment(db.Model):
    __tablename__ = "application_assignments"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    assigner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    primary_verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    secondary_verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    # Relationships
    application = db.relationship("Application", back_populates="assignment")
    assigner = db.relationship("User", foreign_keys=[assigner_id], back_populates="assigned_applications")
    primary_verifier = db.relationship("User", foreign_keys=[primary_verifier_id], back_populates="primary_verifications")
    secondary_verifier = db.relationship("User", foreign_keys=[secondary_verifier_id], back_populates="secondary_verifications")

class UploadedFile(db.Model):
    __tablename__ = "uploaded_files"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    module_name = db.Column(db.String(50), nullable=False)
    step = db.Column(db.String(50), nullable=False)
    field_name = db.Column(db.String(50), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(200), nullable=False)
    # Relationship
    application = db.relationship("Application", back_populates="files")

class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(200), nullable=True)
    annotations = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    # Relationships
    application = db.relationship("Application", back_populates="chat_messages")
    sender = db.relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    receiver = db.relationship("User", foreign_keys=[receiver_id], back_populates="received_messages")
    notifications = db.relationship("Notification", back_populates="message", lazy=True)

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("chat_messages.id"), nullable=True)
    content = db.Column(db.Text, nullable=True)
    read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationships
    user = db.relationship("User", back_populates="notifications")
    message = db.relationship("ChatMessage", back_populates="notifications")

class EditRequest(db.Model):
    __tablename__ = "edit_requests"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    comments = db.Column(db.Text, nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="Active")
    # Relationships
    application = db.relationship("Application", back_populates="edit_requests")
    verifier = db.relationship("User", back_populates="edit_requests")

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    module_name = db.Column(db.String(50), nullable=False)
    step = db.Column(db.String(50), nullable=False)
    change_type = db.Column(db.String(50), nullable=False)  # e.g., 'field_update', 'file_upload'
    change_details = db.Column(db.JSON, nullable=False)  # e.g., {'field': 'legal_name', 'old_value': 'Old', 'new_value': 'New'}
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Relationships
    application = db.relationship("Application", back_populates="audit_logs")
    user = db.relationship("User", back_populates="audit_logs")