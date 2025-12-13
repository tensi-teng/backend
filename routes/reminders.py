from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn

reminders_bp = Blueprint("reminders", __name__)

# ---------------- CREATE REMINDER ----------------
@reminders_bp.route("/reminders", methods=["POST"])
@jwt_required()
def create_reminder():
    try:
        # JWT identity is STRING
        user_id_str = get_jwt_identity()
        user_id_int = int(user_id_str)

        # Validate incoming JSON
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        reminder_time = data.get("time")
        if not reminder_time or not isinstance(reminder_time, str):
            return jsonify({
                "error": "Invalid or missing 'time'. It must be a string."
            }), 400

        description = data.get("description", "")
        if not isinstance(description, str):
            return jsonify({
                "error": "Invalid 'description'. It must be a string."
            }), 400

        # Store reminder
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reminders (user_id, time, description)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (user_id_int, reminder_time, description),
                )

                # Check fetchone() result
                result = cur.fetchone()
                if result is None:
                    return jsonify({"error": "No reminder found"}), 404
                reminder_id = result[0]

        return jsonify({
            "message": "Reminder created successfully",
            "reminder": {
                "id": reminder_id,
                "time": reminder_time,
                "description": description,
            },
        }), 201

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
