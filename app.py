
from flask import Flask
from dotenv import load_dotenv
import os
load_dotenv()

from flasgger import Swagger
from flask_jwt_extended import JWTManager

from routes.auth import auth_bp
from routes.workouts import workouts_bp
from routes.public_api import public_bp
from routes.importer import import_bp
from routes.gestures import gestures_bp
from routes.saved_workouts import saved_workouts_bp

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret')

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "securityDefinitions": {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "name": "X-API-KEY",
            "in": "header"
        }
    }
}

# Initialize Swagger with security definitions
Swagger(app, config=swagger_config)

jwt = JWTManager(app)

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(workouts_bp, url_prefix='')
app.register_blueprint(public_bp, url_prefix='/predefined_workouts')
app.register_blueprint(saved_workouts_bp, url_prefix='')
app.register_blueprint(import_bp, url_prefix='')
app.register_blueprint(gestures_bp, url_prefix='')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
