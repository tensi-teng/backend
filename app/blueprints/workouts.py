import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import cloudinary
import cloudinary.uploader

from ..extensions import db
from ..domain import Workout, Payment, ChecklistItem, SavedWorkout
from ..utils.generate_checklist import generate_checklist


cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

bp = Blueprint("workouts", __name__)


@bp.route("/workouts", methods=["POST"])
@jwt_required()
def create_workout():
    try:
        user_id = int(get_jwt_identity())
        name = None
        description = ""
        equipment = []
        fileobj = None

        if request.form:
            name = request.form.get("name")
            description = request.form.get("description", "").strip()
            raw_eq = request.form.get("equipment")
            if raw_eq:
                equipment = [e.strip() for e in raw_eq.split(",") if e.strip()]
            fileobj = request.files.get("file")

        if not name and request.is_json:
            data = request.get_json() or {}
            name = data.get("name")
            description = data.get("description", "").strip()
            equipment = data.get("equipment", []) or []

        if not name or not name.strip():
            return jsonify({"error": "name required"}), 400

        name = name.strip()

        image_url = public_id = None
        if fileobj and fileobj.filename != "":
            uploaded = cloudinary.uploader.upload(
                fileobj, folder=f"workouts/{user_id}", resource_type="image"
            )
            image_url = uploaded.get("secure_url")
            public_id = uploaded.get("public_id")

        has_sub = (
            db.session.query(Payment)
            .filter_by(user_id=user_id, status="success", type="subscription")
            .first()
        )
        if not has_sub:
            return jsonify({"error": "No active subscription found"}), 403

        workout = Workout(
            name=name,
            description=description,
            equipment=",".join(equipment),
            user_id=user_id,
            image_url=image_url,
            public_id=public_id,
        )
        db.session.add(workout)
        db.session.flush()

        for item in generate_checklist(equipment):
            db.session.add(
                ChecklistItem(
                    task=item["task"], done=item["done"], workout_id=workout.id
                )
            )

        db.session.commit()
        return jsonify({"message": "created", "workout_id": workout.id}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/workouts", methods=["GET"])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())

        created = (
            db.session.query(Workout)
            .filter_by(user_id=user_id)
            .order_by(Workout.name.asc())
            .all()
        )

        saved = (
            db.session.query(SavedWorkout)
            .filter_by(user_id=user_id)
            .order_by(SavedWorkout.name.asc())
            .all()
        )

        response = []
        for w in created:
            checklist = [
                {"id": c.id, "task": c.task, "done": c.done}
                for c in db.session.query(ChecklistItem)
                .filter_by(workout_id=w.id)
                .order_by(ChecklistItem.id.asc())
            ]
            response.append(
                {
                    "workout_id": w.id,
                    "saved_id": None,
                    "name": w.name,
                    "description": w.description or "",
                    "equipment": (w.equipment or "").split(",") if w.equipment else [],
                    "image_url": w.image_url,
                    "instructions": None,
                    "muscles": [],
                    "type": None,
                    "level": None,
                    "source": "created",
                    "checklist": checklist,
                }
            )

        for s in saved:
            checklist = [
                {"id": c.id, "task": c.task, "done": c.done}
                for c in db.session.query(ChecklistItem)
                .filter_by(workout_id=s.id)
                .order_by(ChecklistItem.id.asc())
            ]
            response.append(
                {
                    "workout_id": None,
                    "saved_id": s.id,
                    "name": s.name,
                    "description": s.description or "",
                    "equipment": (s.equipment or "").split(",") if s.equipment else [],
                    "image_url": None,
                    "instructions": None,
                    "muscles": s.muscles or [],
                    "type": s.type,
                    "level": s.level,
                    "source": "saved",
                    "checklist": checklist,
                }
            )

        response.sort(
            key=lambda x: (
                0 if x["source"] == "saved" else 1,
                (x["name"] or "").lower(),
            )
        )
        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/workouts/<int:workout_id>", methods=["PUT"])
@jwt_required()
def update_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())

        w = db.session.get(Workout, workout_id)
        if not w:
            return jsonify({"error": "Workout not found"}), 404
        if w.user_id != user_id:
            return jsonify({"error": "Not allowed"}), 403

        name = None
        description = None
        equipment = None
        fileobj = None

        if request.files or request.form:
            fileobj = request.files.get("file")
            name = request.form.get("name")
            description = request.form.get("description", "").strip() or None
            raw_eq = request.form.get("equipment")
            if raw_eq is not None:
                equipment = [e.strip() for e in raw_eq.split(",") if e.strip()]

        if request.is_json:
            data = request.get_json(silent=True) or {}
            name = data.get("name", name)
            description = data.get("description", "").strip() or description
            if "equipment" in data:
                equipment = (
                    [e.strip() for e in data["equipment"] if e.strip()]
                    if data["equipment"]
                    else None
                )

        if all(v is None for v in [name, description, equipment, fileobj]):
            return jsonify({"error": "No updates provided"}), 400

        new_image_url = None
        new_public_id = None
        if fileobj and fileobj.filename != "":
            if not fileobj.mimetype.startswith("image/"):
                return jsonify({"error": "Only image files are allowed"}), 400
            uploaded = cloudinary.uploader.upload(
                fileobj,
                folder=f"workouts/{user_id}",
                resource_type="image",
                overwrite=True,
            )
            new_image_url = uploaded.get("secure_url")
            new_public_id = uploaded.get("public_id")

            if w.public_id and w.public_id != new_public_id:
                try:
                    cloudinary.uploader.destroy(w.public_id)
                except Exception:
                    pass

        if name is not None:
            w.name = name.strip()
        if description is not None:
            w.description = description
        if equipment is not None:
            w.equipment = ",".join(equipment)
        if new_image_url:
            w.image_url = new_image_url
            w.public_id = new_public_id

        if equipment is not None:
            db.session.query(ChecklistItem).filter_by(workout_id=w.id).delete()
            for item in generate_checklist(equipment):
                db.session.add(
                    ChecklistItem(task=item["task"], done=item["done"], workout_id=w.id)
                )

        db.session.commit()
        return jsonify({"message": "Workout updated successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/workouts/<wid>", methods=["DELETE"])
@jwt_required()
def delete_workout(wid):
    try:
        user_id = int(get_jwt_identity())

        if wid.lower() == "all":
            user_workouts = db.session.query(Workout).filter_by(user_id=user_id).all()
            for w in user_workouts:
                db.session.query(ChecklistItem).filter_by(workout_id=w.id).delete()
                db.session.delete(w)
        else:
            ids = [int(i) for i in wid.split(",") if i.isdigit()]
            if not ids:
                return jsonify({"error": "Invalid IDs"}), 400
            for wid_ in ids:
                w = (
                    db.session.query(Workout)
                    .filter_by(id=wid_, user_id=user_id)
                    .first()
                )
                if w:
                    db.session.query(ChecklistItem).filter_by(workout_id=w.id).delete()
                    db.session.delete(w)

        db.session.commit()
        return jsonify({"message": "deleted"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/checklist/items/<int:item_id>", methods=["PATCH"])
@jwt_required()
def toggle_checklist_item(item_id):
    try:
        user_id = int(get_jwt_identity())

        item = db.session.query(ChecklistItem).get(item_id)
        if not item:
            return jsonify({"error": "Checklist item not found or not authorized"}), 404

        workout = db.session.query(Workout).get(item.workout_id)
        if not workout or workout.user_id != user_id:
            return jsonify({"error": "Checklist item not found or not authorized"}), 404

        item.done = not item.done
        db.session.commit()
        return (
            jsonify(
                {
                    "message": "Checklist item toggled successfully",
                    "item": {"id": item.id, "done": item.done},
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
