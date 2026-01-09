from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, jwt_required

from ..extensions import db
from ..models import PublicWorkout, SavedWorkout, ChecklistItem
from ..utils.generate_checklist import generate_checklist

bp = Blueprint("public", __name__)


@bp.route("/workouts", methods=["GET"])
def get_workouts():
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        user_id = None

    type_filter = request.args.get("type")
    muscle_filter = request.args.get("muscle")
    level_filter = request.args.get("level")

    try:
        q = PublicWorkout.query
        if type_filter:
            q = q.filter(PublicWorkout.type.ilike(f"%{type_filter}%"))
        if muscle_filter:
            q = q.filter(
                db.func.lower(muscle_filter).op("=")(
                    db.any(db.func.lower(PublicWorkout.muscles))
                )
            )
        if level_filter:
            q = q.filter(PublicWorkout.level.ilike(f"%{level_filter}%"))

        rows = q.with_entities(
            PublicWorkout.id,
            PublicWorkout.name,
            PublicWorkout.equipment,
            PublicWorkout.type,
            PublicWorkout.muscles,
            PublicWorkout.level,
            PublicWorkout.instructions,
        ).all()

        workouts = [
            {
                "id": r[0],
                "name": r[1],
                "equipment": r[2],
                "type": r[3],
                "muscles": r[4] or [],
                "level": r[5],
                "instructions": r[6],
            }
            for r in rows
        ]

        return (
            jsonify({"user_id": user_id, "count": len(workouts), "workouts": workouts}),
            200,
        )

    except Exception as e:
        current_app.logger.exception("Error fetching public workouts")
        return jsonify({"error": "database error", "detail": str(e)}), 500


@bp.route("/workouts/save", methods=["POST"])
@bp.route("/workouts/save/<int:public_workout_id>", methods=["POST"])
@jwt_required()
def save_public_workouts(public_workout_id=None):
    try:
        user_id_int = int(get_jwt_identity())

        data = None
        if request.is_json:
            data = request.get_json(silent=True) or {}
        elif request.form:
            data = request.form.to_dict(flat=True)
        else:
            data = {}

        if not data and public_workout_id is None:
            return jsonify({"error": "Request body required"}), 400

        if public_workout_id is not None:
            workout_ids = [public_workout_id]
        else:
            workout_ids = data.get("workout_ids", [])
            if isinstance(workout_ids, int):
                workout_ids = [workout_ids]
            if not isinstance(workout_ids, list):
                return jsonify({"error": "workout_ids must be int or list"}), 400

        if not workout_ids:
            return jsonify({"error": "workout_ids required"}), 400

        saved_workouts = []

        for wid in workout_ids:
            overrides = {}
            if isinstance(data, dict):
                overrides = (data.get("overrides", {}) or {}).get(str(wid), {})
                if not isinstance(overrides, dict):
                    return jsonify({"error": "Invalid overrides structure"}), 400

            public_w = PublicWorkout.query.get(wid)
            if not public_w:
                continue

            existing = SavedWorkout.query.filter_by(
                user_id=user_id_int, public_workout_id=wid
            ).first()
            if existing:
                checklist = [
                    {"id": c.id, "task": c.task, "done": c.done}
                    for c in ChecklistItem.query.filter_by(workout_id=existing.id).all()
                ]
                saved_workouts.append(
                    {
                        "id": existing.id,
                        "name": existing.name,
                        "description": existing.description,
                        "equipment": (
                            existing.equipment.split(",") if existing.equipment else []
                        ),
                        "checklist": checklist,
                    }
                )
                continue

            name = overrides.get("name") or public_w.name
            description = overrides.get("description") or (public_w.instructions or "")

            equipment = overrides.get("equipment")
            if equipment is None:
                equipment = public_w.equipment.split(",") if public_w.equipment else []
            eq_str = ",".join(equipment)

            saved = SavedWorkout(
                user_id=user_id_int,
                public_workout_id=wid,
                name=name,
                description=description,
                equipment=eq_str,
                type=public_w.type,
                muscles=public_w.muscles or [],
                level=public_w.level,
            )
            db.session.add(saved)
            db.session.flush()

            checklist = generate_checklist(equipment)
            for item in checklist:
                db.session.add(
                    ChecklistItem(
                        task=item["task"], done=item["done"], workout_id=saved.id
                    )
                )

            saved_workouts.append(
                {
                    "id": saved.id,
                    "name": name,
                    "description": description,
                    "equipment": equipment,
                    "checklist": checklist,
                }
            )

        if not saved_workouts:
            return jsonify({"error": "no workouts saved"}), 409

        db.session.commit()
        return (
            jsonify({"message": "workouts saved", "saved_workouts": saved_workouts}),
            201,
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Save workout failed")
        return jsonify({"error": str(e)}), 500
