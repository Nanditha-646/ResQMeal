import os

from flask import Flask, render_template
from dotenv import load_dotenv

from app.db import init_mysql

from app.routes.auth import auth_bp
from app.routes.admin import admin_bp
from app.routes.donor import donor_bp
from app.routes.ngo import ngo_bp


load_dotenv()


def create_app():

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    app.config["SECRET_KEY"] = os.getenv(
        "SECRET_KEY"
    )

    init_mysql(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(donor_bp)
    app.register_blueprint(ngo_bp)

    @app.route("/")
    def home():
        return render_template(
            "index.html"
        )

    return app