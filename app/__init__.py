# app/__init__.py
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_mail import Mail
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

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
    from app.dashboard import dashboard as dashboard_bp
    from app.modules.module_1 import module_1 as module_1_bp
    from app.modules.module_2 import module_2 as module_2_bp
    from app.chat import chat as chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(module_1_bp)
    app.register_blueprint(module_2_bp)
    app.register_blueprint(chat_bp)

    # Add homepage route
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.home'))  # Changed to 'dashboard.home'
        return redirect(url_for('auth.login'))  # Redirect to login for guests

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))