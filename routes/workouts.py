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
        name = description = None
        equipment = []
        fileobj = None

        # Handle form-data first
        if request.form:
            name = request.form.get("name")
            description = request.form.get("description", "")
            raw_eq = request.form.get("equipment")
            if raw_eq:
                equipment = [e.strip() for e in raw_eq.split(",") if e.strip()]
            fileobj = request.files.get("file")

        # Fallback to JSON payload
        elif request.is_json:
            data = request.get_json()
            name = data.get("name")
            description = data.get("description", "")
            equipment = data.get("equipment", [])

        # Ensure name is retrieved correctly for both JSON and form-data
        if not name:
            name = request.form.get("name") if request.content_type and "multipart/form-data" in request.content_type else None

        if not name:
            return jsonify({"error": "name required"}), 400

        image_url = public_id = None
        if fileobj:
            uploaded = cloudinary.uploader.upload(
                fileobj, folder=f"workouts/{user_id}", resource_type="image"
            )
            image_url = uploaded.get("secure_url")
            public_id = uploaded.get("public_id")

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Subscription check
                cur.execute(
                    "SELECT 1 FROM payments WHERE user_id=%s AND status='success' AND type='subscription' LIMIT 1",
                    (user_id,),
                )
                if not cur.fetchone():
                    return jsonify({"error": "No active subscription found"}), 403

                # Insert workout
                cur.execute(
                    """
                    INSERT INTO workouts (name, description, equipment, user_id, image_url, public_id)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (name, description, ",".join(equipment), user_id, image_url, public_id),
                )
                workout_id = cur.fetchone()[0]

                # Generate checklist
                for item in generate_checklist(equipment):
                    cur.execute(
                        "INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)",
                        (item["task"], item["done"], workout_id),
                    )

        # Ensure database transaction is committed properly
        conn.commit()

        return jsonify({"message": "created", "workout_id": workout_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- LIST WORKOUTS ----------------
@workouts_bp.route("/workouts", methods=["GET"])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor(row_factory=rows.dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS workout_id, NULL AS saved_id, name, description, equipment, image_url,
                           NULL AS instructions, NULL AS muscles, NULL AS type, NULL AS level, 'created' AS source
                    FROM workouts WHERE user_id=%s
                    UNION ALL
                    SELECT NULL AS workout_id, id AS saved_id, name, description, equipment, NULL AS image_url,
                           instructions, muscles, type, level, 'saved' AS source
                    FROM saved_workouts WHERE user_id=%s
                    ORDER BY source DESC
                    """,
                    (user_id, user_id),
                )
                rows_data = cur.fetchall()

        return jsonify([
            {
                "workout_id": r["workout_id"],
                "saved_id": r["saved_id"],
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

# ---------------- UPDATE WORKOUT ----------------
@workouts_bp.route("/workouts/<int:workout_id>", methods=["PUT"])
@jwt_required()
def update_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}

        # Ensure the object is valid before accessing
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
                            "INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)",
                            (item["task"], item["done"], workout_id),
                        )

        # Ensure database transaction is committed properly
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
                    ids = [int(i) for i in wid.split(",")]
                    cur.execute("DELETE FROM checklist_items WHERE workout_id = ANY(%s)", (ids,))
                    cur.execute("DELETE FROM workouts WHERE id = ANY(%s) AND user_id=%s", (ids, user_id))
                    cur.execute("DELETE FROM saved_workouts WHERE id = ANY(%s) AND user_id=%s", (ids, user_id))

        return jsonify({"message": "deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- TOGGLE CHECKLIST ----------------
@workouts_bp.route("/workouts/<int:workout_id>/checklist", methods=["PATCH"])
@jwt_required()
def toggle_checklist(workout_id):
    try:
        user_id = int(get_jwt_identity())

        # Ensure the JSON payload is valid before accessing 'get'
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400

        item_ids = data.get("item_ids", [])

        if not isinstance(item_ids, list):
            return jsonify({"error": "item_ids must be a list"}), 400

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM workouts WHERE id=%s", (workout_id,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({"error": "Not allowed"}), 403
                cur.execute(
                    "UPDATE checklist_items SET done = NOT done WHERE workout_id=%s AND id = ANY(%s) RETURNING id, done",
                    (workout_id, item_ids),
                )
                results = cur.fetchall()

        return jsonify({"updated": len(results), "items": [{"id": r[0], "done": r[1]} for r in results]}), 200
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
                # Validate fetchone() result before accessing
                result = cur.fetchone()
                if not result:
                    return jsonify({"error": "No workout found"}), 404

                workout_id = result[0]

        return jsonify({
            "status": True,
            "message": f"{payment_type.capitalize()} payment of NGN {result[1]} successful",
            "data": {
                "payment_id": result[0],
                "reference": "DUMMY_SUB_REFERENCE",
                "authorization_url": "https://paystack.com/dummy-authorization",
            },
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
