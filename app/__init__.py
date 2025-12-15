import os
from datetime import timedelta
from flask import Flask


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # Defaults
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.environ.get("DATABASE_URL", "sqlite:///instance/app.db"),
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault(
        "JWT_SECRET_KEY", os.environ.get("JWT_SECRET_KEY", "dev-secret")
    )
    app.config.setdefault("JWT_ACCESS_TOKEN_EXPIRES", timedelta(days=7))
    app.config.setdefault("AUTO_MIGRATE", True)

    # Load config from environment with prefix, e.g., APP_SQLALCHEMY_DATABASE_URI
    # See https://flask.palletsprojects.com/ for from_prefixed_env
    try:
        app.config.from_prefixed_env(prefix="APP")
    except Exception:
        raise RuntimeError("Failed to load configuration from environment variables")

    # Fallback: map DATABASE_URL -> SQLALCHEMY_DATABASE_URI if not set by prefix
    if not app.config.get("SQLALCHEMY_DATABASE_URI") and os.environ.get("DATABASE_URL"):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Init logging
    from .logging import init_logging

    init_logging(app)

    # Init extensions
    from .extensions import db, migrate, jwt, swagger

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    swagger.init_app(app)

    # Auto-migrate on startup (if configured)
    with app.app_context():
        from flask_migrate import upgrade

        # Only auto-migrate if explicitly enabled to avoid conflicts in dev/test
        if app.config.get("AUTO_MIGRATE"):
            try:
                upgrade()
            except Exception:
                pass  # Log or handle migration failure

    # Register blueprints
    from .blueprints.auth import bp as auth_bp
    from .blueprints.workouts import bp as workouts_bp
    from .blueprints.public import bp as public_bp
    from .blueprints.reminders import bp as reminders_bp
    from .blueprints.payments import bp as payments_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(workouts_bp, url_prefix="/users")
    app.register_blueprint(public_bp, url_prefix="/public")
    app.register_blueprint(reminders_bp, url_prefix="/api")
    app.register_blueprint(payments_bp, url_prefix="/payments")

    return app
