from flask import render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from app import db
from app.models import Notification, ChatMessage
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from . import notification

@notification.route("/notifications")
@login_required
def notifications():
    logger.info(f"START /notification/notifications - User ID: {current_user.id}, Role: {current_user.role}, Authenticated: {current_user.is_authenticated}")
    try:
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
        unread_count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
        logger.info(f"Retrieved {len(notifications)} notifications for user {current_user.id}, {unread_count} unread")
        return render_template("notification/notifications.html", notifications=notifications, unread_count=unread_count)
    except Exception as e:
        logger.error(f"ERROR in /notification/notifications for user {current_user.id}: {str(e)}")
        return render_template("notification/notifications.html", notifications=[], unread_count=0, error="Unable to load notifications. Please try again.")

@notification.route("/mark_notification_read/<int:notification_id>", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    logger.info(f"User {current_user.id} marking notification {notification_id} as read")
    try:
        notification = Notification.query.get_or_404(notification_id)
        if notification.user_id != current_user.id:
            logger.warning(f"Unauthorized attempt by user {current_user.id} to mark notification {notification_id}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        if not notification.read:
            notification.read = True
            if notification.message_id:
                message = ChatMessage.query.get(notification.message_id)
                if message:
                    message.read = True
            db.session.commit()
            logger.info(f"Notification {notification_id} marked as read for user {current_user.id}")
        return jsonify({"status": "success", "message": "Notification marked as read"})
    except Exception as e:
        logger.error(f"ERROR marking notification {notification_id} for user {current_user.id}: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@notification.route("/unread_count")
@login_required
def unread_count():
    try:
        unread_count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
        logger.info(f"User {current_user.id} has {unread_count} unread notifications")
        return jsonify({"unread_count": unread_count})
    except Exception as e:
        logger.error(f"Error fetching unread count for user {current_user.id}: {str(e)}")
        return jsonify({"unread_count": 0}), 500