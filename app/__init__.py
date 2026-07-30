import logging

from flask import Flask

from config import Config
from app import db as db_module
from app.security.csrf import protect as csrf_protect, token as csrf_token
from app.version import __version__


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    logging.basicConfig(level=logging.INFO)

    if app.config["SECRET_KEY"] == "change-me-in-production":
        app.logger.warning("SECRET_KEY is using the insecure default")
    if not app.config["CLUSTER_CREDENTIALS_KEY"]:
        app.logger.warning("CLUSTER_CREDENTIALS_KEY is not configured; saving cluster credentials is disabled")

    db_module.init_db(app)

    app.before_request(csrf_protect)
    app.context_processor(lambda: {"csrf_token": csrf_token, "app_version": __version__})

    from app.routes.auth import bp as auth_bp
    from app.routes.volumes import bp as volumes_bp
    from app.routes.backups import bp as backups_bp
    from app.routes.clusters import bp as clusters_bp
    from app.routes.api import bp as api_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(volumes_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(clusters_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    return app
