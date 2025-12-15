from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..domain import Reminder

bp = Blueprint("reminders", __name__)


@bp.route("/reminders", methods=["POST"])
@jwt_required()
def create_reminder():
    try:
        user_id_int = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        reminder_time = data.get("time")
        if not reminder_time or not isinstance(reminder_time, str):
            return (
                jsonify({"error": "Invalid or missing 'time'. It must be a string."}),
                400,
            )

        description = data.get("description", "")
        if not isinstance(description, str):
            return (
                jsonify({"error": "Invalid 'description'. It must be a string."}),
                400,
            )

        reminder = Reminder(
            user_id=user_id_int, time=reminder_time, description=description
        )
        db.session.add(reminder)
        db.session.commit()
        return (
            jsonify(
                {
                    "message": "Reminder created successfully",
                    "reminder": {
                        "id": reminder.id,
                        "time": reminder.time,
                        "description": reminder.description,
                    },
                }
            ),
            201,
        )

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/reminders/<int:reminder_id>", methods=["DELETE"])
@jwt_required()
def delete_reminder(reminder_id):
    try:
        user_id_int = int(get_jwt_identity())
        reminder = Reminder.query.filter_by(id=reminder_id, user_id=user_id_int).first()
        if not reminder:
            return jsonify({"error": "Reminder not found or not authorized"}), 404
        db.session.delete(reminder)
        db.session.commit()
        return jsonify({"message": "Reminder deleted successfully"}), 200

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/reminders/<int:reminder_id>", methods=["PUT"])
@jwt_required()
def edit_reminder(reminder_id):
    try:
        user_id_int = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON payload"}), 400

        reminder = Reminder.query.filter_by(id=reminder_id, user_id=user_id_int).first()
        if not reminder:
            return jsonify({"error": "Reminder not found or not authorized"}), 404

        reminder_time = data.get("time")
        description = data.get("description")
        if reminder_time is not None and not isinstance(reminder_time, str):
            return jsonify({"error": "Invalid 'time'. It must be a string."}), 400
        if description is not None and not isinstance(description, str):
            return (
                jsonify({"error": "Invalid 'description'. It must be a string."}),
                400,
            )

        if reminder_time is not None:
            reminder.time = reminder_time
        if description is not None:
            reminder.description = description

        db.session.commit()
        return jsonify({"message": "Reminder updated successfully"}), 200

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/reminders", methods=["GET"])
@jwt_required()
def list_reminders():
    try:
        user_id_int = int(get_jwt_identity())
        reminders = (
            Reminder.query.filter_by(user_id=user_id_int)
            .order_by(Reminder.time.asc())
            .all()
        )
        return (
            jsonify(
                {
                    "reminders": [
                        {"id": r.id, "time": r.time, "description": r.description}
                        for r in reminders
                    ]
                }
            ),
            200,
        )

    except ValueError:
        return jsonify({"error": "Invalid user ID in token"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
