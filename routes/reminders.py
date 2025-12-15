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

# ---------------- DELETE REMINDER ----------------
@reminders_bp.route("/reminders/<int:reminder_id>", methods=["DELETE"])
@jwt_required()
def delete_reminder(reminder_id):
    try:
        # JWT identity is STRING
        user_id_str = get_jwt_identity()
        user_id_int = int(user_id_str)

        # Delete reminder
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM reminders WHERE id=%s AND user_id=%s RETURNING id",
                    (reminder_id, user_id_int),
                )

                # Check fetchone() result
                result = cur.fetchone()
                if result is None:
                    return jsonify({"error": "Reminder not found or not authorized"}), 404

        return jsonify({"message": "Reminder deleted successfully"}), 200

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- EDIT REMINDER ----------------
@reminders_bp.route("/reminders/<int:reminder_id>", methods=["PUT"])
@jwt_required()
def edit_reminder(reminder_id):
    try:
        # JWT identity is STRING
        user_id_str = get_jwt_identity()
        user_id_int = int(user_id_str)

        # Validate incoming JSON
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        reminder_time = data.get("time")
        description = data.get("description")

        if reminder_time is not None and not isinstance(reminder_time, str):
            return jsonify({"error": "Invalid 'time'. It must be a string."}), 400

        if description is not None and not isinstance(description, str):
            return jsonify({"error": "Invalid 'description'. It must be a string."}), 400

        # Update reminder
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE reminders
                    SET time = COALESCE(%s, time),
                        description = COALESCE(%s, description)
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                    """,
                    (reminder_time, description, reminder_id, user_id_int),
                )

                # Check fetchone() result
                result = cur.fetchone()
                if result is None:
                    return jsonify({"error": "Reminder not found or not authorized"}), 404

        return jsonify({"message": "Reminder updated successfully"}), 200

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- LIST REMINDERS ----------------
@reminders_bp.route("/reminders", methods=["GET"])
@jwt_required()
def list_reminders():
    try:
        # JWT identity is STRING
        user_id_str = get_jwt_identity()
        user_id_int = int(user_id_str)

        # Fetch reminders
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, time, description FROM reminders WHERE user_id = %s ORDER BY time ASC",
                    (user_id_int,),
                )
                reminders = cur.fetchall()

        return jsonify({
            "reminders": [
                {"id": r[0], "time": r[1], "description": r[2]} for r in reminders
            ]
        }), 200

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500