import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg import rows
from db import get_conn
from utils.generate_checklist import generate_checklist
import cloudinary.uploader
import cloudinary

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
            data = request.get_json()
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

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM payments WHERE user_id=%s AND status='success' AND type='subscription' LIMIT 1",
                    (user_id,),
                )
                if not cur.fetchone():
                    return jsonify({"error": "No active subscription found"}), 403

                cur.execute(
                    """
                    INSERT INTO workouts (name, description, equipment, user_id, image_url, public_id)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (name, description, ",".join(equipment), user_id, image_url, public_id),
                )
                workout_id = cur.fetchone()[0]

                for item in generate_checklist(equipment):
                    cur.execute(
                        "INSERT INTO checklist_items (task, done, workout_id) VALUES (%s, %s, %s)",
                        (item["task"], item["done"], workout_id),
                    )

            conn.commit()

        return jsonify({"message": "created", "workout_id": workout_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- LIST WORKOUTS WITH CHECKLIST ----------------
@workouts_bp.route("/workouts", methods=["GET"])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor(row_factory=rows.dict_row) as cur:
                # Fetch all workouts (created + saved)
                cur.execute(
                    """
                    SELECT 
                        id AS workout_id, NULL::integer AS saved_id,
                        name, description, equipment, image_url,
                        NULL AS instructions, NULL AS muscles, NULL AS type, NULL AS level,
                        'created' AS source
                    FROM workouts 
                    WHERE user_id = %s

                    UNION ALL

                    SELECT 
                        NULL::integer AS workout_id, id AS saved_id,
                        name, description, equipment, NULL AS image_url,
                        instructions, muscles, type, level,
                        'saved' AS source
                    FROM saved_workouts 
                    WHERE user_id = %s

                    ORDER BY source DESC, name
                    """,
                    (user_id, user_id)
                )
                workouts = cur.fetchall()

                # Collect workout_ids for created workouts to fetch their checklist items
                created_workout_ids = [w["workout_id"] for w in workouts if w["workout_id"] is not None]

                checklist_map = {}
                if created_workout_ids:
                    cur.execute(
                        """
                        SELECT id, task, done, workout_id
                        FROM checklist_items
                        WHERE workout_id = ANY(%s)
                        ORDER BY id
                        """,
                        (created_workout_ids,)
                    )
                    for row in cur.fetchall():
                        wid = row["workout_id"]
                        if wid not in checklist_map:
                            checklist_map[wid] = []
                        checklist_map[wid].append({
                            "id": row["id"],
                            "task": row["task"],
                            "done": row["done"]
                        })

        # Build final response
        response = []
        for w in workouts:
            workout_data = {
                "workout_id": w["workout_id"],
                "saved_id": w["saved_id"],
                "name": w["name"],
                "description": w["description"] or "",
                "equipment": (w["equipment"] or "").split(",") if w["equipment"] else [],
                "image_url": w["image_url"],
                "instructions": w["instructions"],
                "muscles": w["muscles"] or [],
                "type": w["type"],
                "level": w["level"],
                "source": w["source"],
                # Only created workouts have checklist items
                "checklist": checklist_map.get(w["workout_id"], []) if w["workout_id"] else []
            }
            response.append(workout_data)

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- UPDATE WORKOUT ----------------
@workouts_bp.route("/workouts/<int:workout_id>", methods=["PUT"])
@jwt_required()
def update_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}

        if not data:
            return jsonify({"error": "Invalid request payload"}), 400

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM workouts WHERE id=%s", (workout_id,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "Workout not found"}), 404
                if row[0] != user_id:
                    return jsonify({"error": "Not allowed"}), 403

                if "name" in data:
                    cur.execute("UPDATE workouts SET name=%s WHERE id=%s", (data["name"], workout_id))
                if "description" in data:
                    cur.execute("UPDATE workouts SET description=%s WHERE id=%s", (data["description"], workout_id))
                if "equipment" in data:
                    eq = ",".join(data["equipment"])
                    cur.execute("UPDATE workouts SET equipment=%s WHERE id=%s", (eq, workout_id))
                    cur.execute("DELETE FROM checklist_items WHERE workout_id=%s", (workout_id,))
                    for item in generate_checklist(data["equipment"]):
                        cur.execute(
                            "INSERT INTO checklist_items (task, done, workout_id) VALUES (%s, %s, %s)",
                            (item["task"], item["done"], workout_id),
                        )

            conn.commit()

        return jsonify({"message": "updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- DELETE WORKOUT ----------------
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
                    cur.execute("DELETE FROM workouts WHERE user_id=%s", (user_id,))
                    cur.execute("DELETE FROM saved_workouts WHERE user_id=%s", (user_id,))
                else:
                    ids = [int(i) for i in wid.split(",") if i.isdigit()]
                    if not ids:
                        return jsonify({"error": "Invalid IDs"}), 400
                    cur.execute("DELETE FROM checklist_items WHERE workout_id = ANY(%s)", (ids,))
                    cur.execute("DELETE FROM workouts WHERE id = ANY(%s) AND user_id=%s", (ids, user_id))
                    cur.execute("DELETE FROM saved_workouts WHERE id = ANY(%s) AND user_id=%s", (ids, user_id))

            conn.commit()

        return jsonify({"message": "deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- TOGGLE SINGLE CHECKLIST ITEM ----------------
@workouts_bp.route("/checklist/items/<int:item_id>", methods=["PATCH"])
@jwt_required()
def toggle_checklist_item(item_id):
    """
    Toggle the 'done' status of a single checklist item.
    URL: PATCH /users/checklist/items/<item_id>
    No body required.
    """
    try:
        user_id = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership through workout
                cur.execute(
                    """
                    SELECT ci.id, ci.done
                    FROM checklist_items ci
                    JOIN workouts w ON ci.workout_id = w.id
                    WHERE ci.id = %s AND w.user_id = %s
                    """,
                    (item_id, user_id)
                )
                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "Checklist item not found or not authorized"}), 404

                # Toggle
                cur.execute(
                    """
                    UPDATE checklist_items
                    SET done = NOT done
                    WHERE id = %s
                    RETURNING id, done
                    """,
                    (item_id,)
                )
                result = cur.fetchone()
                toggled_item = {"id": result[0], "done": result[1]}

            conn.commit()

        return jsonify({
            "message": "Checklist item toggled successfully",
            "item": toggled_item
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- DUMMY PAYSTACK PAYMENT ----------------
@workouts_bp.route("/paystack/dummy-payment", methods=["POST"])
@jwt_required()
def paystack_dummy_payment():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}
        email = data.get("email")
        if not email:
            return jsonify({"error": "Email is required"}), 400

        fixed_amount = 5000
        payment_type = "subscription"

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payments (user_id, amount, currency, status, type, paid_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id, amount, status
                    """,
                    (user_id, fixed_amount, "NGN", "success", payment_type),
                )
                result = cur.fetchone()
                if not result:
                    return jsonify({"error": "Payment recording failed"}), 500

            conn.commit()

        return jsonify({
            "status": True,
            "message": f"{payment_type.capitalize()} payment of NGN {fixed_amount} successful",
            "data": {
                "payment_id": result[0],
                "reference": "DUMMY_SUB_REFERENCE",
                "authorization_url": "https://paystack.com/dummy-authorization",
            },
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500