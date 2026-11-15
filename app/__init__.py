import secrets
from flask import Flask

def create_app():

    # Create a new Flask application
    app = Flask(__name__, static_folder = "")
    from .gate import init_gate
    init_gate(app)
    app.config["SECRET_KEY"] = secrets.token_hex(32)

    # Import the blueprint
    from app.routes import home
    app.register_blueprint(home)
    return app