import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_mail import Mail
from config import Config  # Import Config from root config.py

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['TEMPLATES_AUTO_RELOAD'] = True  # Enable template auto-reload for development

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"

    # Register custom Jinja filter
    app.jinja_env.filters['basename'] = lambda x: os.path.basename(x)

    # Register blueprints
    from app.auth import auth as auth_bp
    from app.applicant import applicant as applicant_bp
    from app.assigner import assigner as assigner_bp
    from app.verifier import verifier as verifier_bp
    from app.director import director as director_bp
    from app.admin import admin as admin_bp
    from app.modules.module_1.routes import module_1 as module_1_bp
    from app.modules.module_1.pdf_routes import module_1_pdf as module_1_pdf_bp
    from app.modules.module_2.routes import module_2 as module_2_bp
    from app.modules.module_2.pdf_routes import module_2_pdf as module_2_pdf_bp
    from app.modules.module_3 import module_3 as module_3_bp
    from app.modules.module_3.pdf_routes import module_3_pdf as module_3_pdf_bp
    from app.modules.module_4 import module_4 as module_4_bp
    from app.modules.module_4.pdf_routes import module_4_pdf as module_4_pdf_bp
    from app.modules.module_5 import module_5 as module_5_bp
    from app.modules.module_5.pdf_routes import module_5_pdf as module_5_pdf_bp
    from app.modules.module_6 import module_6 as module_6_bp
    from app.modules.module_6.pdf_routes import module_6_pdf as module_6_pdf_bp
    from app.modules.module_7 import module_7 as module_7_bp
    from app.modules.module_7.pdf_routes import module_7_pdf as module_7_pdf_bp
    from app.modules.module_8 import module_8 as module_8_bp
    from app.modules.module_8.pdf_routes import module_8_pdf as module_8_pdf_bp
    from app.modules.module_9 import module_9 as module_9_bp
    from app.modules.module_9.pdf_routes import module_9_pdf as module_9_pdf_bp
    from app.modules.module_10 import module_10 as module_10_bp
    from app.modules.module_10.pdf_routes import module_10_pdf as module_10_pdf_bp
    from app.chat import chat as chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(applicant_bp)
    app.register_blueprint(assigner_bp)
    app.register_blueprint(verifier_bp)
    app.register_blueprint(director_bp)  # Added Director blueprint
    app.register_blueprint(admin_bp)
    app.register_blueprint(module_1_bp)
    app.register_blueprint(module_1_pdf_bp)
    app.register_blueprint(module_2_bp)
    app.register_blueprint(module_2_pdf_bp)
    app.register_blueprint(module_3_bp)
    app.register_blueprint(module_3_pdf_bp)
    app.register_blueprint(module_4_bp)
    app.register_blueprint(module_4_pdf_bp)
    app.register_blueprint(module_5_bp)
    app.register_blueprint(module_5_pdf_bp)
    app.register_blueprint(module_6_bp)
    app.register_blueprint(module_6_pdf_bp)
    app.register_blueprint(module_7_bp)
    app.register_blueprint(module_7_pdf_bp)
    app.register_blueprint(module_8_bp)
    app.register_blueprint(module_8_pdf_bp)
    app.register_blueprint(module_9_bp)
    app.register_blueprint(module_9_pdf_bp)
    app.register_blueprint(module_10_bp)
    app.register_blueprint(module_10_pdf_bp)
    app.register_blueprint(chat_bp)

    # Add homepage route with role-based redirection
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == "user":
                return redirect(url_for('applicant.home'))
            elif current_user.role == "Assigner":
                return redirect(url_for('assigner.home'))
            elif current_user.role in ["Primary Verifier", "Secondary Verifier"]:
                return redirect(url_for('verifier.home'))
            elif current_user.role == "Director":
                return redirect(url_for('director.home'))  # Added Director redirect
            elif current_user.role == "admin":
                return redirect(url_for('admin.dashboard'))
            else:
                return "Role not implemented yet", 501
        return redirect(url_for('auth.login'))

    # Test database connection route
    @app.route('/test_db')
    def test_db():
        try:
            db.session.execute('SELECT 1')
            return "Database connection successful!"
        except Exception as e:
            return f"Database connection failed: {str(e)}"

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))