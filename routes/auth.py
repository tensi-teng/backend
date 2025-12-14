# auth.py

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt,
    get_jwt_identity
)
from db import get_conn

auth_bp = Blueprint("auth", __name__)

# Default gestures for every new user
DEFAULT_GESTURES = [
    {"name": "swipe_left", "action": "delete"},
    {"name": "swipe_right", "action": "mark as done"},
    {"name": "shake", "action": "reset"},
]

# Simple in-memory JWT blacklist (use Redis in production for scalability)
jwt_blacklist = set()


# ---------------- REGISTER ----------------
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

    # Optional: strip whitespace
    username = username.strip()
    email = email.strip()
    reg_number = reg_number.strip()

    hashed_pw = generate_password_hash(password)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check for duplicates
                cur.execute(
                    """
                    SELECT username, email, reg_number 
                    FROM users 
                    WHERE username=%s OR email=%s OR reg_number=%s
                    """,
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

                # Create user
                cur.execute(
                    """
                    INSERT INTO users (username, password, name, reg_number, email)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (username, hashed_pw, name, reg_number, email),
                )
                user_id = cur.fetchone()[0]

                # Add default gestures
                for g in DEFAULT_GESTURES:
                    cur.execute(
                        """
                        INSERT INTO gestures (name, action, user_id)
                        VALUES (%s, %s, %s)
                        """,
                        (g["name"], g["action"], user_id),
                    )

            conn.commit()

        return jsonify({
            "message": "User registered successfully",
            "user_id": str(user_id)
        }), 201

    except Exception as e:
        return jsonify({"error": "Registration failed"}), 500


# ---------------- LOGIN ----------------
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    username = username.strip()

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, password FROM users WHERE username=%s",
                    (username,),
                )
                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "Invalid credentials"}), 401

                user_id, hashed_password = row

                if not check_password_hash(hashed_password, password):
                    return jsonify({"error": "Invalid credentials"}), 401

        # Create JWT token
        token = create_access_token(
            identity=str(user_id),  
            additional_claims={"username": username},
        )

        return jsonify({
            "token": token,
            "user": {
                "id": str(user_id),
                "username": username,
            }
        }), 200

    except Exception as e:
        return jsonify({"error": "Login failed"}), 500


# ---------------- CURRENT USER ----------------
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    claims = get_jwt()
    username = claims.get("username")

    return jsonify({
        "id": user_id,
        "username": username,
    }), 200


# ---------------- LOGOUT ----------------
@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    jwt_blacklist.add(jti)
    return jsonify({"message": "Logged out successfully"}), 200



from flask_jwt_extended import get_jwt

def token_in_blacklist(jti):
    return jti in jwt_blacklist

