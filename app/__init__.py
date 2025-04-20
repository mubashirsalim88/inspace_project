# app/__init__.py
from flask import Flask, redirect, url_for, render_template, request, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_required
from flask_mail import Mail
from config import Config
import logging

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

# Set up logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"

    # Register blueprints
    from app.auth import auth as auth_bp
    from app.admin import admin as admin_bp
    from app.applicant import applicant as applicant_bp
    from app.assigner import assigner as assigner_bp
    from app.verifier import verifier as verifier_bp
    from app.director import director as director_bp
    from app.modules.module_1 import module_1 as module_1_bp
    from app.modules.module_2 import module_2 as module_2_bp
    from app.modules.module_3 import module_3 as module_3_bp
    from app.modules.module_4 import module_4 as module_4_bp
    from app.modules.module_9 import module_9 as module_9_bp
    from app.modules.module_10 import module_10 as module_10_bp
    from app.modules.module_11 import module_11 as module_11_bp
    from app.modules.module_12 import module_12 as module_12_bp
    from app.chat import chat as chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(applicant_bp)
    app.register_blueprint(assigner_bp)
    app.register_blueprint(verifier_bp)
    app.register_blueprint(director_bp)
    app.register_blueprint(module_1_bp)
    app.register_blueprint(module_2_bp)
    app.register_blueprint(module_3_bp)
    app.register_blueprint(module_4_bp)
    app.register_blueprint(module_9_bp)
    app.register_blueprint(module_10_bp)
    app.register_blueprint(module_11_bp)
    app.register_blueprint(module_12_bp)
    app.register_blueprint(chat_bp)

    # Log all requests
    @app.before_request
    def log_request():
        user_id = current_user.id if current_user.is_authenticated else "anonymous"
        role = current_user.role if current_user.is_authenticated else "N/A"
        logger.info(f"Request to {request.path} by user {user_id} (role: {role}, authenticated: {current_user.is_authenticated})")
        if request.path in ["/chat/notifications", "/chat/notifications_new"]:
            logger.info(f"Accessing notifications route - Session: {dict(session)}")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.role == "user":
                return redirect(url_for("applicant.home"))
            elif current_user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            elif current_user.role == "Assigner":
                return redirect(url_for("assigner.home"))
            elif current_user.role in ["Primary Verifier", "Secondary Verifier"]:
                return redirect(url_for("verifier.home"))
            else:
                return "Role not implemented yet", 501
        return redirect(url_for("auth.login"))

    @app.route("/test_notifications")
    @login_required
    def test_notifications():
        logger.info(f"Test route accessed by user {current_user.id} (role: {current_user.role})")
        return redirect(url_for("chat.notifications"))

    @app.route("/debug_session")
    @login_required
    def debug_session():
        logger.info(f"Debug session - User ID: {current_user.id}, Role: {current_user.role}, Authenticated: {current_user.is_authenticated}")
        logger.info(f"Session contents: {dict(session)}")
        try:
            from app.models import Notification
            notification_count = Notification.query.filter_by(user_id=current_user.id).count()
            logger.info(f"Notification count for user {current_user.id}: {notification_count}")
        except Exception as e:
            logger.error(f"Error querying notifications in debug_session: {str(e)}")
        return jsonify({
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
            "is_authenticated": current_user.is_authenticated,
            "notifications_url": url_for("chat.notifications"),
            "session": dict(session)
        })

    @app.errorhandler(403)
    def forbidden(e):
        user_id = current_user.id if current_user.is_authenticated else "anonymous"
        role = current_user.role if current_user.is_authenticated else "N/A"
        logger.error(f"403 error at {request.path} for user {user_id} (role: {role}, authenticated: {current_user.is_authenticated})")
        flash("You do not have permission to access this resource.", "error")
        if current_user.is_authenticated:
            if current_user.role == "user":
                return redirect(url_for("applicant.home"))
            elif current_user.role in ["Primary Verifier", "Secondary Verifier"]:
                return redirect(url_for("verifier.home"))
            elif current_user.role == "Assigner":
                return redirect(url_for("assigner.home"))
            elif current_user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            else:
                return redirect(url_for("index"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(500)
    def internal_error(e):
        user_id = current_user.id if current_user.is_authenticated else "anonymous"
        role = current_user.role if current_user.is_authenticated else "N/A"
        logger.error(f"500 error at {request.path} for user {user_id} (role: {role}, authenticated: {current_user.is_authenticated}): {str(e)}")
        flash("An internal server error occurred. Please try again later.", "error")
        return redirect(url_for("applicant.home" if current_user.is_authenticated and current_user.role == "user" else "verifier.home" if current_user.is_authenticated else "auth.login"))

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))