from flask import Flask
from dotenv import load_dotenv
import os
from flasgger import Swagger
from flask_jwt_extended import JWTManager

# Load .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Set JWT secret
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret')

# === Debug Print for Environment Variables ===
db_url = os.getenv("DATABASE_URL")
jwt_key = os.getenv("JWT_SECRET_KEY")
api_key = os.getenv("API_KEY")

def mask(value):
    """Mask sensitive values for safe logging."""
    return value[:5] + "..." + value[-5:] if value and len(value) > 10 else value or "None"

print("\n=== Environment Variables Check ===")
print("DATABASE_URL:", mask(db_url))
print("JWT_SECRET_KEY:", mask(jwt_key))
print("API_KEY:", mask(api_key))
print("-------------------\n")

# === Swagger Config ===
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

Swagger(app, config=swagger_config)

# JWT setup
jwt = JWTManager(app)

# Import blueprints
from routes.auth import auth_bp
from routes.workouts import workouts_bp
from routes.public_api import public_bp
from routes.importer import import_bp
from routes.gestures import gestures_bp

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(workouts_bp, url_prefix='/user')
app.register_blueprint(public_bp, url_prefix='/api')
app.register_blueprint(import_bp, url_prefix='')
app.register_blueprint(gestures_bp, url_prefix='')

# Run app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
