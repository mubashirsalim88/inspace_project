# app/__init__.py
from flask import Flask, redirect, url_for, render_template, request
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

# Set up logging
logging.basicConfig(level=logging.INFO)
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
    app.register_blueprint(chat_bp)

    # Homepage route with role-based redirection
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

    # Test route to bypass potential middleware
    @app.route("/test_notifications")
    @login_required
    def test_notifications():
        logger.info(
            f"Test route accessed by user {current_user.id} (role: {current_user.role})"
        )
        return redirect(url_for("chat.notifications"))

    # Custom 403 handler to debug permission error
    @app.errorhandler(403)
    def forbidden(e):
        logger.error(
            f"403 error for user {current_user.id if current_user.is_authenticated else 'anonymous'} at {request.path}"
        )
        return (
            render_template(
                "403.html", message="You do not have permission to access this page."
            ),
            403,
        )

    return app


@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    return User.query.get(int(user_id))
