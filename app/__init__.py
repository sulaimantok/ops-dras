import logging

from flask import Flask

from config import Config
from app import db as db_module


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    logging.basicConfig(level=logging.INFO)

    db_module.init_db(app)

    from app.routes.auth import bp as auth_bp
    from app.routes.volumes import bp as volumes_bp
    from app.routes.backups import bp as backups_bp
    from app.routes.clusters import bp as clusters_bp
    from app.routes.api import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(volumes_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(clusters_bp)
    app.register_blueprint(api_bp)

    return app
