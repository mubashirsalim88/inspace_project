# app/chat/routes.py
from flask import render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from app import db, mail
from app.models import Application, ChatMessage, Notification, ApplicationAssignment, User
from flask_mail import Message
import logging
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from . import chat  # Import the chat blueprint from __init__.py

logger = logging.getLogger(__name__)

# Ensure upload folder exists
UPLOAD_FOLDER = 'app/static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@chat.route("/chat/<int:application_id>", methods=["GET", "POST"])
@login_required
def chat_view(application_id):  # Renamed from 'chat' to 'chat_view' to avoid naming conflict
    logger.info(f"User {current_user.id} (role: {current_user.role}) accessing /chat/{application_id}")
    application = Application.query.get_or_404(application_id)
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()

    # Define allowed users
    allowed_users = [application.user_id, assignment.primary_verifier_id]
    if assignment.secondary_verifier_id:
        allowed_users.append(assignment.secondary_verifier_id)

    if current_user.id not in allowed_users:
        logger.warning(f"Unauthorized access attempt by user {current_user.id} to chat for application {application_id}")
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home" if current_user.role == "user" else "verifier.home"))

    # Mark message as read if message_id is provided
    message_id = request.args.get("message_id", type=int)
    if message_id:
        message = ChatMessage.query.get_or_404(message_id)
        if message.application_id == application_id and message.receiver_id == current_user.id and not message.read:
            logger.info(f"Marking message {message_id} as read for user {current_user.id}")
            message.read = True
            notification = Notification.query.filter_by(message_id=message_id, user_id=current_user.id).first()
            if notification and not notification.read:
                notification.read = True
            db.session.commit()

    if request.method == "POST":
        message = request.form.get("message")
        receiver_id = request.form.get("receiver_id", type=int)
        image = request.files.get("image")
        image_path = None

        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            image_path = os.path.join('uploads', filename)
            full_path = os.path.join(UPLOAD_FOLDER, filename)
            image.save(full_path)
            logger.info(f"Image uploaded: {image_path}")

        if not message and not image_path:
            flash("Message or image is required.", "error")
            return redirect(url_for("chat.chat_view", application_id=application_id))

        if not receiver_id or receiver_id not in allowed_users or receiver_id == current_user.id:
            flash("Invalid receiver.", "error")
            return redirect(url_for("chat.chat_view", application_id=application_id))

        chat_message = ChatMessage(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            application_id=application_id,
            message=message or "",
            image_path=image_path,
            read=False,
            timestamp=datetime.utcnow()
        )
        db.session.add(chat_message)

        notification = Notification(
            user_id=receiver_id,
            message_id=chat_message.id,
            content=f"New message from {current_user.username} regarding Application ID {application_id}",
            timestamp=datetime.utcnow(),
            read=False
        )
        db.session.add(notification)

        receiver = User.query.get(receiver_id)
        msg = Message(
            "New Chat Message - IN-SPACe Portal",
            sender="noreply@inspace.gov.in",
            recipients=[receiver.email]
        )
        msg.body = f"You have a new message regarding Application ID {application_id}:\n\n{message or 'Image sent'}\n\nLogin to respond: {url_for('auth.login', _external=True)}"
        try:
            mail.send(msg)
            logger.info(f"Email sent to {receiver.email} for new message on application {application_id}")
        except Exception as e:
            logger.error(f"Failed to send email to {receiver.email}: {str(e)}")

        db.session.commit()
        flash("Message sent successfully.", "success")
        return redirect(url_for("chat.chat_view", application_id=application_id))

    # Fetch all messages related to the application for the current user
    messages = ChatMessage.query.filter_by(application_id=application_id).filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id.in_(allowed_users))) |
        ((ChatMessage.sender_id.in_(allowed_users)) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc()).all()

    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id) if assignment.secondary_verifier_id else None
    applicant = User.query.get(application.user_id)

    # Determine available recipients
    recipients = []
    if current_user.id != applicant.id:
        recipients.append({"id": applicant.id, "username": applicant.username, "role": "Applicant"})
    if current_user.id != primary_verifier.id:
        recipients.append({"id": primary_verifier.id, "username": primary_verifier.username, "role": "Primary Verifier"})
    if secondary_verifier and current_user.id != secondary_verifier.id:
        recipients.append({"id": secondary_verifier.id, "username": secondary_verifier.username, "role": "Secondary Verifier"})

    logger.info(f"Rendering chat.html for application {application_id}")
    return render_template(
        "chat/chat.html",
        application=application,
        messages=messages,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier,
        applicant=applicant,
        assignment=assignment,
        message_id=message_id,
        recipients=recipients
    )

@chat.route("/enable_edit/<int:application_id>", methods=["POST"])
@login_required
def enable_edit(application_id):
    logger.info(f"User {current_user.id} (role: {current_user.role}) attempting to enable edit for application {application_id}")
    application = Application.query.get_or_404(application_id)
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    
    if current_user.id not in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
        logger.error(f"Unauthorized attempt by user {current_user.id} to enable edit for application {application_id}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    try:
        application.status = "Pending"
        db.session.commit()

        notification = Notification(
            user_id=application.user_id,
            content=f"Application ID {application_id} is now editable by request of {current_user.username}.",
            timestamp=datetime.utcnow(),
            read=False
        )
        db.session.add(notification)

        msg = Message(
            "Application Edit Enabled - IN-SPACe Portal",
            sender="noreply@inspace.gov.in",
            recipients=[application.user.email]
        )
        msg.body = f"Your application (ID: {application_id}) is now editable. Please make the necessary changes and resubmit.\n\nLogin: {url_for('auth.login', _external=True)}"
        mail.send(msg)
        logger.info(f"Edit enabled and email sent to {application.user.email} for application {application_id}")

        db.session.commit()
        return jsonify({"status": "success", "message": "Edit enabled for applicant."})
    except Exception as e:
        logger.error(f"Error enabling edit for application {application_id}: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@chat.route("/notifications")
@login_required
def notifications():
    logger.info(f"START /chat/notifications - User ID: {current_user.id}, Role: {current_user.role}, Authenticated: {current_user.is_authenticated}")
    try:
        logger.info(f"User details - Username: {current_user.username}, Email: {current_user.email}")
        logger.info("Rendering notifications.html with empty notifications list")
        return render_template("chat/notifications.html", notifications=[])
    except Exception as e:
        logger.error(f"ERROR in /chat/notifications for user {current_user.id}: {str(e)}")
        flash("Failed to load notifications. Please try again.", "error")
        return redirect(url_for("applicant.home" if current_user.role == "user" else "verifier.home"))

@chat.route("/notifications_new")
@login_required
def notifications_new():
    logger.info(f"START /notifications_new - User ID: {current_user.id}, Role: {current_user.role}, Authenticated: {current_user.is_authenticated}")
    try:
        logger.info(f"Querying notifications for user {current_user.id}")
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
        logger.info(f"Retrieved {len(notifications)} notifications for user {current_user.id}")
        return render_template("chat/notifications.html", notifications=notifications)
    except Exception as e:
        logger.error(f"ERROR in /notifications_new for user {current_user.id}: {str(e)}")
        flash("Unable to load notifications.", "error")
        return redirect(url_for("applicant.home" if current_user.role == "user" else "verifier.home"))

@chat.route("/mark_notification_read/<int:notification_id>", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    logger.info(f"User {current_user.id} marking notification {notification_id} as read")
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        logger.warning(f"Unauthorized attempt by user {current_user.id} to mark notification {notification_id}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    if not notification.read:
        notification.read = True
        if notification.message_id:
            notification.message.read = True
        db.session.commit()
        logger.info(f"Notification {notification_id} marked as read for user {current_user.id}")
    return jsonify({"status": "success", "message": "Notification marked as read"})