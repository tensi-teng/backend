from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn

reminders_bp = Blueprint('reminders', __name__)

@reminders_bp.route('/reminders', methods=['POST'])
@jwt_required()
def create_reminder():
    """
    Endpoint to collect time data for reminders from the frontend.
    """
    try:
        # Validate JWT identity
        user_id = get_jwt_identity()
        if not isinstance(user_id, str):
            return jsonify({"error": "Invalid JWT payload"}), 400

        # Validate incoming JSON
        data = request.get_json() or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        reminder_time = data.get('time')
        if not reminder_time or not isinstance(reminder_time, str):
            return jsonify({"error": "Invalid or missing 'time'. It must be a string."}), 400

        description = data.get('description', '')
        if not isinstance(description, str):
            return jsonify({"error": "Invalid 'description'. It must be a string."}), 400

        # Store reminder in the database
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reminders (user_id, time, description)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, reminder_time, description)
                )
                reminder_id = cur.fetchone()[0]

        return jsonify({
            "message": "Reminder created successfully",
            "reminder": {
                "id": reminder_id,
                "time": reminder_time,
                "description": description
            }
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500