from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token
from db import get_conn

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
    """
          tags:
            - Auth
          summary: Register a new user account
          description: Register a new user with username, password, name, registration number, and email.
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  required:
                    - username
                    - password
                    - name
                    - reg_number
                    - email
                  properties:
                    username:
                      type: string
                      example: john_doe123
                      description: Enter a unique username
                    password:
                      type: string
                      format: password
                      example: SecurePass123!
                      description: Choose a strong password
                    name:
                      type: string
                      example: John Michael Doe
                      description: Full name of the user
                    reg_number:
                      type: string
                      example: REG2025-001
                      description: Registration number for verification
                    email:
                      type: string
                      format: email
                      example: john.doe@example.com
                      description: Valid email address for the account
          responses:
            '201':
              description: User registered successfully
              content:
                application/json:
                  example:
                    message: user registered
                    user_id: 42
            '400':
              description: Bad request (missing or duplicate fields)
              content:
                application/json:
                  example:
                    error: All fields are required
    """
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    name = data.get("name")
    reg_number = data.get("reg_number")
    email = data.get("email")

    if not all([username, password, name, reg_number, email]):
        return jsonify({"error": "All fields are required"}), 400

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, email, reg_number FROM users WHERE username=%s OR email=%s OR reg_number=%s",
                (username, email, reg_number),
            )
            existing = cur.fetchone()
            if existing:
                if existing[0] == username:
                    return jsonify({"error": "Username already exists"}), 400
                if existing[1] == email:
                    return jsonify({"error": "Email already registered"}), 400
                if existing[2] == reg_number:
                    return jsonify({"error": "Registration number already exists"}), 400

            hashed_pw = generate_password_hash(password)
            cur.execute(
                """
                INSERT INTO users (username, password, name, reg_number, email)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (username, hashed_pw, name, reg_number, email),
            )
            uid = cur.fetchone()[0]

    return jsonify({'message': 'user registered', 'user_id': uid}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """
          tags:
            - Auth
          summary: Login to get JWT token
          description: Authenticate user and receive a JWT token to access protected endpoints.
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  required:
                    - username
                    - password
                  properties:
                    username:
                      type: string
                      example: john_doe123
                      description: Enter your registered username
                    password:
                      type: string
                      format: password
                      example: SecurePass123!
                      description: Enter your account password
          responses:
            '200':
              description: Login successful
              content:
                application/json:
                  example:
                    token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
            '400':
              description: Missing username or password
              content:
                application/json:
                  example:
                    error: username and password required
            '401':
              description: Invalid credentials
              content:
                application/json:
                  example:
                    error: invalid credentials
    """
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id, password FROM users WHERE username=%s', (username,))
            row = cur.fetchone()
            if not row or not check_password_hash(row[1], password):
                return jsonify({'error': 'invalid credentials'}), 401
            uid = row[0]

    token = create_access_token(identity=uid)
    return jsonify({'token': token}), 200
