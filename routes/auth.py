from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token
from db import get_conn

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
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
            uid = str(cur.fetchone()[0])  # Convert user ID to string

    return jsonify({'message': 'user registered', 'user_id': uid}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
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
            uid = str(row[0])  # Convert user ID to string

    token = create_access_token(identity=uid)  # Identity is now a string
    return jsonify({'token': token}), 200
