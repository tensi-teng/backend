import os
import json
import psycopg
from psycopg import sql, rows
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
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

# ---------------- CREATE WORKOUT ----------------
@workouts_bp.route("/workouts", methods=["POST"])
@jwt_required()
def create_workout():
    try:
        user_id_str = get_jwt_identity()     # JWT identity is STRING
        user_id_int = int(user_id_str)       # DB needs INT

        # ---------- MULTIPART ----------
        if request.content_type and "multipart/form-data" in request.content_type:
            name = request.form.get("name")
            if not name:
                return jsonify({"error": "name required"}), 400

            description = request.form.get("description", "")
            raw_eq = request.form.get("equipment", "")

            try:
                if raw_eq.strip().startswith("["):
                    equipment = json.loads(raw_eq)
                else:
                    equipment = [e.strip() for e in raw_eq.split(",") if e.strip()]
            except Exception:
                equipment = []

            fileobj = request.files.get("file")
            uploaded_url = uploaded_public_id = None

            if fileobj:
                uploaded = cloudinary.uploader.upload(
                    fileobj,
                    folder=f"workouts/{user_id_str}",
                    use_filename=True,
                    unique_filename=False,
                )
                uploaded_url = uploaded.get("secure_url")
                uploaded_public_id = uploaded.get("public_id")

        # ---------- JSON ----------
        else:
            data = request.get_json(silent=True) or {}
            if not isinstance(data, dict):
                return jsonify({"error": "Invalid JSON payload"}), 400

            name = data.get("name")
            if not name:
                return jsonify({"error": "name required"}), 400

            description = data.get("description", "")
            equipment = data.get("equipment", [])

            if not isinstance(equipment, list):
                return jsonify({"error": "equipment must be a list"}), 400

            uploaded_url = uploaded_public_id = None
            image_remote = data.get("image_url")

            if image_remote:
                uploaded = cloudinary.uploader.upload(
                    image_remote,
                    folder=f"workouts/{user_id_str}",
                    use_filename=True,
                    unique_filename=False,
                )
                uploaded_url = uploaded.get("secure_url")
                uploaded_public_id = uploaded.get("public_id")

        # ---------- DB ----------
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Payment check
                cur.execute(
                    "SELECT COUNT(*) FROM payments WHERE user_id=%s AND status='success'",
                    (user_id_int,),
                )
                if cur.fetchone()[0] == 0:
                    return jsonify({"error": "No active payment found"}), 403

                eq_str = ",".join(equipment)

                cur.execute(
                    """
                    INSERT INTO workouts (name, description, equipment, user_id, image_url, public_id)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (name, description, eq_str, user_id_int, uploaded_url, uploaded_public_id),
                )

                wid = cur.fetchone()[0]

                for it in generate_checklist(equipment):
                    cur.execute(
                        """
                        INSERT INTO checklist_items (task, done, workout_id)
                        VALUES (%s,%s,%s)
                        """,
                        (it["task"], it["done"], wid),
                    )

        return jsonify({
            "message": "created",
            "workout": {
                "id": wid,
                "name": name,
                "description": description,
                "equipment": equipment,
                "image_url": uploaded_url,
            },
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- LIST WORKOUTS ----------------
@workouts_bp.route("/workouts", methods=["GET"])
@jwt_required()
def list_workouts():
    try:
        user_id_int = int(get_jwt_identity())
        workouts = []

        with get_conn() as conn:
            with conn.cursor(row_factory=rows.dict_row) as cur:
                for table in ["workouts", "saved_workouts"]:
                    cur.execute(
                        f"""
                        SELECT id, name, description, equipment, image_url
                        FROM {table}
                        WHERE user_id=%s
                        ORDER BY id DESC
                        """,
                        (user_id_int,),
                    )
                    workouts.extend(cur.fetchall())

        return jsonify([
            {
                "id": w["id"],
                "name": w["name"],
                "description": w["description"],
                "equipment": [e for e in (w["equipment"] or "").split(",") if e],
                "image_url": w["image_url"],
            }
            for w in workouts
        ]), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- UPDATE WORKOUT ----------------
@workouts_bp.route("/workouts/<int:wid>", methods=["PUT"])
@jwt_required()
def update_workout(wid):
    try:
        data = request.get_json(silent=True) or {}
        user_id_int = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM workouts WHERE id=%s", (wid,))
                row = cur.fetchone()
                table = "workouts"

                if not row:
                    cur.execute("SELECT user_id FROM saved_workouts WHERE id=%s", (wid,))
                    row = cur.fetchone()
                    table = "saved_workouts"

                # Check fetchone() result
                result = cur.fetchone()
                if result is None:
                    return jsonify({"error": "No workout found"}), 404
                workout_id = result[0]

                # Use psycopg.sql for dynamic queries
                from psycopg.sql import SQL, Identifier
                query = SQL("SELECT * FROM workouts WHERE id = %s")
                cur.execute(query, (workout_id,))

                # Validate fetchone() result
                row = cur.fetchone()
                if row is None:
                    return jsonify({"error": "Workout not found"}), 404

                # Correct dynamic query usage
                table_query = SQL("SELECT id, name, description, equipment, image_url FROM {table} WHERE user_id=%s").format(table=Identifier(table))
                cur.execute(table_query, (user_id,))

                # Ensure user_id is defined
                user_id = request.args.get("user_id")
                if not user_id:
                    return jsonify({"error": "User ID is required"}), 400

                if not row or row[0] != user_id_int:
                    return jsonify({"error": "not allowed"}), 404

                if "name" in data:
                    cur.execute(
                        sql.SQL("UPDATE {t} SET name=%s WHERE id=%s")
                        .format(t=sql.Identifier(table)),
                        (data["name"], wid),
                    )

                if "description" in data:
                    cur.execute(
                        sql.SQL("UPDATE {t} SET description=%s WHERE id=%s")
                        .format(t=sql.Identifier(table)),
                        (data["description"], wid),
                    )

                if "equipment" in data:
                    eq = ",".join(data["equipment"])
                    cur.execute(
                        sql.SQL("UPDATE {t} SET equipment=%s WHERE id=%s")
                        .format(t=sql.Identifier(table)),
                        (eq, wid),
                    )

                    cur.execute("DELETE FROM checklist_items WHERE workout_id=%s", (wid,))
                    for it in generate_checklist(data["equipment"]):
                        cur.execute(
                            "INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)",
                            (it["task"], it["done"], wid),
                        )

        return jsonify({"message": "updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- DELETE WORKOUT(S) ----------------
@workouts_bp.route("/workouts/<wid>", methods=["DELETE"])
@jwt_required()
def delete_workout(wid):
    try:
        user_id_int = int(get_jwt_identity())
        ids = []

        with get_conn() as conn:
            with conn.cursor() as cur:
                if wid.lower() == "all":
                    for table in ["workouts", "saved_workouts"]:
                        cur.execute(
                            f"SELECT id FROM {table} WHERE user_id=%s",
                            (user_id_int,),
                        )
                        ids.extend([r[0] for r in cur.fetchall()])
                else:
                    ids = [int(x) for x in wid.split(",")]

                if not ids:
                    return jsonify({"message": "nothing to delete"}), 200

                cur.execute("DELETE FROM checklist_items WHERE workout_id = ANY(%s)", (ids,))
                cur.execute("DELETE FROM workouts WHERE id = ANY(%s)", (ids,))
                cur.execute("DELETE FROM saved_workouts WHERE id = ANY(%s)", (ids,))

        return jsonify({"message": "deleted", "ids": ids}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
