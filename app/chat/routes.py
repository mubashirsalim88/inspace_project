# app/chat/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from app import db, mail
from app.models import Application, ChatMessage, Notification, ApplicationAssignment, User
from flask_mail import Message
import logging
from datetime import datetime

chat = Blueprint("chat", __name__, template_folder="templates")

logger = logging.getLogger(__name__)

@chat.route("/verifier_chat/<int:application_id>", methods=["GET", "POST"])
@login_required
def verifier_chat(application_id):
    application = Application.query.get_or_404(application_id)
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    
    if current_user.id not in [assignment.primary_verifier_id, assignment.secondary_verifier_id]:
        flash("Unauthorized access.", "error")
        return redirect(url_for("verifier.home"))

    other_verifier_id = assignment.secondary_verifier_id if current_user.id == assignment.primary_verifier_id else assignment.primary_verifier_id
    if not other_verifier_id:
        flash("No other verifier assigned to chat with.", "error")
        return redirect(url_for("verifier.review", application_id=application_id))

    message_id = request.args.get("message_id", type=int)
    if message_id:
        message = ChatMessage.query.get_or_404(message_id)
        if message.application_id == application_id and message.receiver_id == current_user.id and not message.read:
            message.read = True
            notification = Notification.query.filter_by(message_id=message_id, user_id=current_user.id).first()
            if notification and not notification.read:
                notification.read = True
            db.session.commit()

    if request.method == "POST":
        message = request.form.get("message")
        if not message:
            flash("Message is required.", "error")
            return redirect(url_for("chat.verifier_chat", application_id=application_id))

        chat_message = ChatMessage(
            sender_id=current_user.id,
            receiver_id=other_verifier_id,
            application_id=application_id,
            message=message,
            read=False
        )
        db.session.add(chat_message)

        notification = Notification(
            user_id=other_verifier_id,
            message_id=chat_message.id,
            content=f"New message from {current_user.username} regarding Application ID {application_id}",
            timestamp=db.func.now(),
            read=False
        )
        db.session.add(notification)

        receiver = User.query.get(other_verifier_id)
        msg = Message(
            "New Chat Message - IN-SPACe Portal",
            sender="noreply@inspace.gov.in",
            recipients=[receiver.email]
        )
        msg.body = f"You have a new message regarding Application ID {application_id}:\n\n{message}\n\nLogin to respond: {url_for('auth.login', _external=True)}"
        try:
            mail.send(msg)
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

        db.session.commit()
        flash("Message sent successfully.", "success")
        return redirect(url_for("chat.verifier_chat", application_id=application_id))

    messages = ChatMessage.query.filter_by(application_id=application_id).filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == other_verifier_id)) |
        ((ChatMessage.sender_id == other_verifier_id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc()).all()

    other_verifier = User.query.get(other_verifier_id)
    return render_template(
        "chat/verifier_chat.html",
        application=application,
        messages=messages,
        other_verifier=other_verifier,
        assignment=assignment,
        message_id=message_id
    )

@chat.route("/applicant_chat/<int:application_id>", methods=["GET", "POST"])
@login_required
def applicant_chat(application_id):
    application = Application.query.get_or_404(application_id)
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()
    
    allowed_users = [application.user_id, assignment.primary_verifier_id]
    if assignment.secondary_verifier_id:
        allowed_users.append(assignment.secondary_verifier_id)
    
    if current_user.id not in allowed_users:
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home" if current_user.role == "user" else "verifier.home"))

    message_id = request.args.get("message_id", type=int)
    if message_id:
        message = ChatMessage.query.get_or_404(message_id)
        if message.application_id == application_id and message.receiver_id == current_user.id and not message.read:
            message.read = True
            notification = Notification.query.filter_by(message_id=message_id, user_id=current_user.id).first()
            if notification and not notification.read:
                notification.read = True
            db.session.commit()

    if request.method == "POST":
        message = request.form.get("message")
        receiver_id = int(request.form.get("receiver_id"))
        
        if not message or receiver_id not in allowed_users or receiver_id == current_user.id:
            flash("Invalid message or receiver.", "error")
            return redirect(url_for("chat.applicant_chat", application_id=application_id))

        chat_message = ChatMessage(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            application_id=application_id,
            message=message,
            read=False
        )
        db.session.add(chat_message)

        notification = Notification(
            user_id=receiver_id,
            message_id=chat_message.id,
            content=f"New message from {current_user.username} regarding Application ID {application_id}",
            timestamp=db.func.now(),
            read=False
        )
        db.session.add(notification)

        receiver = User.query.get(receiver_id)
        msg = Message(
            "New Chat Message - IN-SPACe Portal",
            sender="noreply@inspace.gov.in",
            recipients=[receiver.email]
        )
        msg.body = f"You have a new message regarding Application ID {application_id}:\n\n{message}\n\nLogin to respond: {url_for('auth.login', _external=True)}"
        try:
            mail.send(msg)
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

        db.session.commit()
        flash("Message sent successfully.", "success")
        return redirect(url_for("chat.applicant_chat", application_id=application_id))

    verifier_ids = [assignment.primary_verifier_id]
    if assignment.secondary_verifier_id:
        verifier_ids.append(assignment.secondary_verifier_id)
    
    if current_user.role == "user":
        messages = ChatMessage.query.filter_by(application_id=application_id).filter(
            ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id.in_(verifier_ids))) |
            ((ChatMessage.sender_id.in_(verifier_ids)) & (ChatMessage.receiver_id == current_user.id))
        ).order_by(ChatMessage.timestamp.asc()).all()
    else:
        messages = ChatMessage.query.filter_by(application_id=application_id).filter(
            ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == application.user_id)) |
            ((ChatMessage.sender_id == application.user_id) & (ChatMessage.receiver_id == current_user.id))
        ).order_by(ChatMessage.timestamp.asc()).all()

    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id) if assignment.secondary_verifier_id else None
    applicant = User.query.get(application.user_id)

    return render_template(
        "chat/applicant_chat.html",
        application=application,
        messages=messages,
        primary_verifier=primary_verifier,
        secondary_verifier=secondary_verifier,
        applicant=applicant,
        assignment=assignment,
        message_id=message_id
    )

@chat.route("/enable_edit/<int:application_id>", methods=["POST"])
@login_required
def enable_edit(application_id):
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
            timestamp=db.func.now(),
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

        db.session.commit()
        return jsonify({"status": "success", "message": "Edit enabled for applicant."})
    except Exception as e:
        logger.error(f"Error enabling edit for application {application_id}: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@chat.route("/notifications")
@login_required
def notifications():
    logger.info(f"User {current_user.id} (role: {current_user.role}, authenticated: {current_user.is_authenticated}) accessing /chat/notifications")
    if not current_user.is_authenticated:
        logger.error("User not authenticated despite @login_required")
        flash("Please log in to view notifications.", "error")
        return redirect(url_for("auth.login"))
    
    try:
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
        logger.info(f"Retrieved {len(notifications)} notifications for user {current_user.id}")
    except Exception as e:
        logger.error(f"Error fetching notifications for user {current_user.id}: {str(e)}")
        flash("An error occurred while loading notifications.", "error")
        return redirect(url_for("applicant.home" if current_user.role == "user" else "verifier.home"))

    return render_template("chat/notifications.html", notifications=notifications)

@chat.route("/mark_notification_read/<int:notification_id>", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    if notification.message_id and not notification.read:
        notification.read = True
        notification.message.read = True
        db.session.commit()
    return jsonify({"status": "success", "message": "Notification marked as read"})