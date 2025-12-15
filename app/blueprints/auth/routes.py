from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt,
    get_jwt_identity,
)

from ...extensions import db
from ...domain import User, Gesture

bp = Blueprint("auth", __name__)

DEFAULT_GESTURES = [
    {"name": "swipe_left", "action": "delete"},
    {"name": "swipe_right", "action": "mark as done"},
    {"name": "shake", "action": "reset"},
]

jwt_blacklist = set()


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password")
    name = data.get("name")
    reg_number = (data.get("reg_number") or "").strip()
    email = (data.get("email") or "").strip()

    if not all([username, password, name, reg_number, email]):
        return jsonify({"error": "All fields are required"}), 400

    existing_user = User.query.filter(
        (User.username == username)
        | (User.email == email)
        | (User.reg_number == reg_number)
    ).first()
    if existing_user:
        if existing_user.username == username:
            return jsonify({"error": "Username already exists"}), 400
        if existing_user.email == email:
            return jsonify({"error": "Email already registered"}), 400
        if existing_user.reg_number == reg_number:
            return jsonify({"error": "Registration number already exists"}), 400

    hashed_pw = generate_password_hash(password)
    user = User(
        username=username,
        password=hashed_pw,
        name=name,
        reg_number=reg_number,
        email=email,
    )
    db.session.add(user)
    db.session.flush()  # assign id

    for g in DEFAULT_GESTURES:
        db.session.add(Gesture(name=g["name"], action=g["action"], user_id=user.id))

    db.session.commit()
    return (
        jsonify({"message": "User registered successfully", "user_id": str(user.id)}),
        201,
    )


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(
        identity=str(user.id), additional_claims={"username": username}
    )
    return (
        jsonify({"token": token, "user": {"id": str(user.id), "username": username}}),
        200,
    )


@bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    claims = get_jwt()
    username = claims.get("username")
    return jsonify({"id": user_id, "username": username}), 200


@bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    jwt_blacklist.add(jti)
    return jsonify({"message": "Logged out successfully"}), 200


def token_in_blacklist(jti):
    return jti in jwt_blacklist
