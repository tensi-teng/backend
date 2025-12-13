import os
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg import rows, sql
from db import get_conn
from utils.generate_checklist import generate_checklist
import cloudinary
import cloudinary.uploader

# ---------------- CLOUDINARY CONFIG ----------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

workouts_bp = Blueprint("workouts", __name__)


# CREATE WORKOUT (user-created only)

@workouts_bp.route("/workouts", methods=["POST"])
@jwt_required()
def create_workout():
    try:
        user_id = int(get_jwt_identity())

        if request.content_type and "multipart/form-data" in request.content_type:
            name = request.form.get("name")
            description = request.form.get("description", "")
            raw_eq = request.form.get("equipment", "")
            equipment = [e.strip() for e in raw_eq.split(",") if e.strip()]
            fileobj = request.files.get("file")
        else:
            data = request.get_json(silent=True) or {}
            name = data.get("name")
            description = data.get("description", "")
            equipment = data.get("equipment", [])
            fileobj = None

        if not name:
            return jsonify({"error": "name required"}), 400

        image_url = None
        public_id = None

        if fileobj:
            uploaded = cloudinary.uploader.upload(
                fileobj,
                folder=f"workouts/{user_id}",
                use_filename=True,
                unique_filename=False,
            )
            image_url = uploaded["secure_url"]
            public_id = uploaded["public_id"]

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM payments WHERE user_id=%s AND status='success' LIMIT 1",
                    (user_id,),
                )
                if not cur.fetchone():
                    return jsonify({"error": "No active payment found"}), 403

                cur.execute(
                    """
                    INSERT INTO workouts (name, description, equipment, user_id, image_url, public_id)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (name, description, ",".join(equipment), user_id, image_url, public_id),
                )
                wid = cur.fetchone()[0]

                for item in generate_checklist(equipment):
                    cur.execute(
                        """
                        INSERT INTO checklist_items (task, done, workout_id)
                        VALUES (%s,%s,%s)
                        """,
                        (item["task"], item["done"], wid),
                    )

        return jsonify({"id": wid, "message": "created"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================
# LIST WORKOUTS (created + saved public workouts)
# ==================================================
@workouts_bp.route("/workouts", methods=["GET"])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor(row_factory=rows.dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        name,
                        description,
                        equipment,
                        image_url,
                        NULL AS instructions,
                        NULL AS muscles,
                        NULL AS type,
                        NULL AS level,
                        'created' AS source
                    FROM workouts
                    WHERE user_id=%s

                    UNION ALL

                    SELECT
                        id,
                        name,
                        description,
                        equipment,
                        NULL AS image_url,
                        instructions,
                        muscles,
                        type,
                        level,
                        'saved' AS source
                    FROM saved_workouts
                    WHERE user_id=%s

                    ORDER BY id DESC
                    """,
                    (user_id, user_id),
                )
                rows_data = cur.fetchall()

        return jsonify([
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "equipment": (r["equipment"] or "").split(","),
                "image_url": r["image_url"],
                "instructions": r["instructions"],
                "muscles": r["muscles"],
                "type": r["type"],
                "level": r["level"],
                "source": r["source"],
            }
            for r in rows_data
        ]), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================
# UPDATE WORKOUT (ONLY user-created workouts)
# ==================================================
@workouts_bp.route("/workouts/<int:wid>", methods=["PUT"])
@jwt_required()
def update_workout(wid):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM workouts WHERE id=%s",
                    (wid,),
                )
                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "Saved workouts cannot be edited"}), 403

                if row[0] != user_id:
                    return jsonify({"error": "not allowed"}), 403

                if "name" in data:
                    cur.execute(
                        "UPDATE workouts SET name=%s WHERE id=%s",
                        (data["name"], wid),
                    )

                if "description" in data:
                    cur.execute(
                        "UPDATE workouts SET description=%s WHERE id=%s",
                        (data["description"], wid),
                    )

                if "equipment" in data:
                    eq = ",".join(data["equipment"])
                    cur.execute(
                        "UPDATE workouts SET equipment=%s WHERE id=%s",
                        (eq, wid),
                    )

                    cur.execute(
                        "DELETE FROM checklist_items WHERE workout_id=%s",
                        (wid,),
                    )
                    for item in generate_checklist(data["equipment"]):
                        cur.execute(
                            """
                            INSERT INTO checklist_items (task, done, workout_id)
                            VALUES (%s,%s,%s)
                            """,
                            (item["task"], item["done"], wid),
                        )

        return jsonify({"message": "updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================
# DELETE WORKOUT(S)
# ==================================================
@workouts_bp.route("/workouts/<wid>", methods=["DELETE"])
@jwt_required()
def delete_workout(wid):
    try:
        user_id = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor() as cur:
                if wid.lower() == "all":
                    cur.execute(
                        "DELETE FROM checklist_items WHERE workout_id IN (SELECT id FROM workouts WHERE user_id=%s)",
                        (user_id,),
                    )
                    cur.execute(
                        "DELETE FROM workouts WHERE user_id=%s",
                        (user_id,),
                    )
                    cur.execute(
                        "DELETE FROM saved_workouts WHERE user_id=%s",
                        (user_id,),
                    )
                else:
                    ids = [int(i) for i in wid.split(",")]
                    cur.execute(
                        "DELETE FROM checklist_items WHERE workout_id = ANY(%s)",
                        (ids,),
                    )
                    cur.execute(
                        "DELETE FROM workouts WHERE id = ANY(%s) AND user_id=%s",
                        (ids, user_id),
                    )
                    cur.execute(
                        "DELETE FROM saved_workouts WHERE id = ANY(%s) AND user_id=%s",
                        (ids, user_id),
                    )

        return jsonify({"message": "deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
