from flask import render_template, request, redirect, url_for, jsonify, flash, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from app import db, mail
from app.models import Application, ChatMessage, Notification, ApplicationAssignment, User
from flask_mail import Message
import logging
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from PIL import Image
import io
import base64
from . import chat

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the upload folder dynamically using current_app
def get_upload_folder():
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        logger.info(f"Created upload folder: {upload_folder}")
    logger.info(f"Upload folder resolved to: {upload_folder}")
    return upload_folder

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image_file(filename):
    return filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))

def save_annotated_image(data_url, output_path):
    try:
        # Remove the data URL prefix (e.g., "data:image/png;base64,")
        base64_string = data_url.split(',')[1]
        img_data = base64.b64decode(base64_string)
        img = Image.open(io.BytesIO(img_data))
        img.save(output_path, 'PNG')
        logger.info(f"Annotated image saved to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save annotated image to {output_path}: {str(e)}")
        raise

@chat.route("/chat/<int:application_id>", methods=["GET", "POST"])
@login_required
def chat_view(application_id):
    logger.info(f"User {current_user.id} (role: {current_user.role}) accessing /chat/{application_id}")
    application = Application.query.get_or_404(application_id)
    assignment = ApplicationAssignment.query.filter_by(application_id=application_id).first_or_404()

    # Define allowed users: Applicant, Primary Verifier, Secondary Verifier, and Directors (if Pending Director Approval)
    allowed_users = [application.user_id, assignment.primary_verifier_id]
    if assignment.secondary_verifier_id:
        allowed_users.append(assignment.secondary_verifier_id)
    if application.status == "Pending Director Approval":
        directors = User.query.filter_by(role="Director").all()
        for director in directors:
            if director.id not in allowed_users:
                allowed_users.append(director.id)

    if current_user.id not in allowed_users:
        logger.warning(
            f"Unauthorized access attempt by user {current_user.id} to chat for application {application_id}")
        flash("Unauthorized access.", "error")
        return redirect(url_for("applicant.home" if current_user.role == "user" else "verifier.home" if current_user.role in ["Primary Verifier", "Secondary Verifier"] else "director.home"))

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
        file = request.files.get("file")
        annotated_image = request.form.get("annotated_image")
        file_path = None

        if file and allowed_file(file.filename):
            UPLOAD_FOLDER = get_upload_folder()
            original_filename = file.filename
            filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{original_filename}")
            file_path = filename
            full_path = os.path.join(UPLOAD_FOLDER, filename)

            if annotated_image and is_image_file(original_filename):
                # Save the annotated image directly
                annotated_filename = f"annotated_{filename}"
                annotated_path = os.path.join(UPLOAD_FOLDER, annotated_filename)
                save_annotated_image(annotated_image, annotated_path)
                file_path = annotated_filename
            else:
                # Save the original file
                try:
                    file.save(full_path)
                    logger.info(
                        f"Successfully saved file: {full_path} (original: {original_filename}, stored as: {file_path})")
                except Exception as e:
                    logger.error(f"Failed to save file {original_filename} to {full_path}: {str(e)}")
                    flash("Error saving file.", "error")
                    return redirect(url_for("chat.chat_view", application_id=application_id))

        if not message and not file_path:
            flash("Message or file is required.", "error")
            return redirect(url_for("chat.chat_view", application_id=application_id))

        if not receiver_id or receiver_id not in allowed_users or receiver_id == current_user.id:
            flash("Invalid receiver.", "error")
            return redirect(url_for("chat.chat_view", application_id=application_id))

        chat_message = ChatMessage(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            application_id=application_id,
            message=message or "",
            image_path=file_path if file else None,
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
        msg.body = f"You have a new message regarding Application ID {application_id}:\n\n{message or 'File sent'}\n\nLogin to respond: {url_for('auth.login', _external=True)}"
        try:
            mail.send(msg)
            logger.info(f"Email sent to {receiver.email} for new message on application {application_id}")
        except Exception as e:
            logger.error(f"Failed to send email to {receiver.email}: {str(e)}")

        db.session.commit()
        flash("Message sent successfully.", "success")
        return redirect(url_for("chat.chat_view", application_id=application_id))

    messages = ChatMessage.query.filter_by(application_id=application_id).filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id.in_(allowed_users))) |
        ((ChatMessage.sender_id.in_(allowed_users)) & (ChatMessage.receiver_id == current_user.id))
    ).filter(ChatMessage.message != '', ChatMessage.message.isnot(None)).order_by(ChatMessage.timestamp.asc()).all()

    for msg in messages:
        if msg.image_path:
            msg.is_image = is_image_file(msg.image_path)
            logger.info(f"Message {msg.id} image_path: {msg.image_path}, is_image: {msg.is_image}")

    primary_verifier = User.query.get(assignment.primary_verifier_id)
    secondary_verifier = User.query.get(assignment.secondary_verifier_id) if assignment.secondary_verifier_id else None
    applicant = User.query.get(application.user_id)
    directors = User.query.filter_by(role="Director").all()

    recipients = []
    if current_user.role == "Director":
        # Director can only chat with verifiers
        if current_user.id != primary_verifier.id:
            recipients.append({"id": primary_verifier.id, "username": primary_verifier.username, "role": "Primary Verifier"})
        if secondary_verifier and current_user.id != secondary_verifier.id:
            recipients.append({"id": secondary_verifier.id, "username": secondary_verifier.username, "role": "Secondary Verifier"})
    else:
        # Applicant and verifiers can chat with each other, and verifiers can chat with directors if Pending Director Approval
        if current_user.id != applicant.id:
            recipients.append({"id": applicant.id, "username": applicant.username, "role": "Applicant"})
        if current_user.id != primary_verifier.id:
            recipients.append({"id": primary_verifier.id, "username": primary_verifier.username, "role": "Primary Verifier"})
        if secondary_verifier and current_user.id != secondary_verifier.id:
            recipients.append({"id": secondary_verifier.id, "username": secondary_verifier.username, "role": "Secondary Verifier"})
        if application.status == "Pending Director Approval":
            for director in directors:
                if current_user.id != director.id:
                    recipients.append({"id": director.id, "username": director.username, "role": "Director"})

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
        recipients=recipients,
        role=current_user.role
    )

@chat.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    UPLOAD_FOLDER = get_upload_folder()
    filename = filename.replace('/', os.sep)
    full_path = os.path.join(UPLOAD_FOLDER, filename)
    logger.info(f"Attempting to serve file: {full_path} (requested filename: {filename})")

    if not os.path.exists(full_path):
        dir_contents = os.listdir(UPLOAD_FOLDER)
        matching_file = None
        for f in dir_contents:
            if f.lower() == filename.lower():
                matching_file = f
                break
        if matching_file:
            full_path = os.path.join(UPLOAD_FOLDER, matching_file)
            logger.info(f"Found matching file (case-insensitive): {full_path}")
        else:
            logger.error(f"File not found at: {full_path}. Directory contents: {dir_contents}")
            abort(404)

    logger.info(f"Serving file: {full_path}")
    return send_from_directory(UPLOAD_FOLDER, os.path.basename(full_path))

@chat.route("/enable_edit/<int:application_id>", methods=["POST"])
@login_required
def enable_edit(application_id):
    logger.info(
        f"User {current_user.id} (role: {current_user.role}) attempting to enable edit for application {application_id}")
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