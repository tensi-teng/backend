import os
import json
import psycopg
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import (
    get_jwt_identity,
    verify_jwt_in_request,
    jwt_required,
)
from utils.generate_checklist import generate_checklist
from db import get_conn

public_bp = Blueprint("public_api", __name__)
DB_URL = os.getenv("DATABASE_URL")


# ---------------------------------------------------
# Universal Request Data Loader
# ---------------------------------------------------
def get_request_data():
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else None

    if request.form:
        return request.form.to_dict(flat=True)

    if request.data:
        try:
            data = json.loads(request.data)
            return data if isinstance(data, dict) else None
        except Exception:
            pass

    return None


# ---------------- GET PUBLIC WORKOUTS ----------------
@public_bp.route("/workouts", methods=["GET"])
def get_workouts():
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()  # string or None
    except Exception:
        user_id = None

    type_filter = request.args.get("type")
    muscle_filter = request.args.get("muscle")
    level_filter = request.args.get("level")

    try:
        # Validate DB_URL
        if not DB_URL:
            raise RuntimeError("DATABASE_URL environment variable is not set")

        # Correct flat parameter usage
        form_data = request.form.to_dict(flat=False)

        # Correct row factory usage
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor() as cur:

                query = """
                    SELECT id, name, equipment, type, muscles, level, instructions
                    FROM public_workouts
                    WHERE 1=1
                """
                params = []

                if type_filter:
                    query += " AND LOWER(type) LIKE LOWER(%s)"
                    params.append(f"%{type_filter}%")

                if muscle_filter:
                    query += """
                        AND EXISTS (
                            SELECT 1 FROM unnest(muscles) m
                            WHERE LOWER(m) LIKE LOWER(%s)
                        )
                    """
                    params.append(f"%{muscle_filter}%")

                if level_filter:
                    query += " AND LOWER(level) LIKE LOWER(%s)"
                    params.append(f"%{level_filter}%")

                cur.execute(query, params)
                workouts = cur.fetchall()

        return jsonify({
            "user_id": user_id,
            "count": len(workouts),
            "workouts": workouts,
        }), 200

    except Exception as e:
        current_app.logger.exception("Error fetching public workouts")
        return jsonify({"error": "database error", "detail": str(e)}), 500


# ---------------- SAVE PUBLIC WORKOUT(S) ----------------
@public_bp.route("/workouts/save", methods=["POST"])
@public_bp.route("/workouts/save/<int:public_workout_id>", methods=["POST"])
@jwt_required()
def save_public_workouts(public_workout_id=None):
    try:
        # JWT identity → STRING → INT
        user_id_int = int(get_jwt_identity())

        data = get_request_data() or {}

        # Require body if no URL ID
        if not data and public_workout_id is None:
            return jsonify({"error": "Request body required"}), 400

        # Determine list of workout IDs
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

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                for wid in workout_ids:

                    # Validate data before accessing attributes
                    if not isinstance(data, dict):
                        return jsonify({"error": "Invalid JSON payload"}), 400

                    overrides = data.get("overrides", {}).get(str(wid), {})
                    if not isinstance(overrides, dict):
                        return jsonify({"error": "Invalid overrides structure"}), 400

                    # Fetch public workout
                    cur.execute(
                        "SELECT * FROM public_workouts WHERE id=%s",
                        (wid,),
                    )
                    public_w = cur.fetchone()
                    if not public_w:
                        continue

                    # Check existing save
                    cur.execute(
                        """
                        SELECT * FROM saved_workouts
                        WHERE user_id=%s AND public_workout_id=%s
                        """,
                        (user_id_int, wid),
                    )
                    existing = cur.fetchone()
                    if existing:
                        saved_id = existing["id"]

                        cur.execute(
                            """
                            SELECT id, task, done
                            FROM checklist_items
                            WHERE workout_id=%s
                            """,
                            (saved_id,),
                        )
                        checklist = cur.fetchall()

                        saved_workouts.append({
                            "id": saved_id,
                            "name": existing["name"],
                            "description": existing["description"],
                            "equipment": existing["equipment"].split(",") if existing["equipment"] else [],
                            "checklist": checklist,
                        })
                        continue

                    # Build values
                    name = overrides.get("name") or public_w["name"]
                    description = overrides.get("description") or public_w.get("instructions") or ""

                    equipment = overrides.get("equipment")
                    if equipment is None:
                        equipment = public_w["equipment"].split(",") if public_w["equipment"] else []

                    eq_str = ",".join(equipment)

                    muscles = public_w.get("muscles") or []
                    muscles_pg = "{" + ",".join(muscles) + "}" if isinstance(muscles, list) else muscles

                    # Insert saved workout
                    cur.execute(
                        """
                        INSERT INTO saved_workouts
                        (user_id, public_workout_id, name, description, equipment, type, muscles, level)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                        """,
                        (
                            user_id_int,
                            wid,
                            name,
                            description,
                            eq_str,
                            public_w.get("type"),
                            muscles_pg,
                            public_w.get("level"),
                        ),
                    )
                    result = cur.fetchone()
                    # Check fetchone() result
                    if result is None:
                        return jsonify({"error": "No data found"}), 404
                    saved_id = result[0]

                    # Generate checklist
                    checklist = generate_checklist(equipment)
                    for item in checklist:
                        cur.execute(
                            """
                            INSERT INTO checklist_items (task, done, workout_id)
                            VALUES (%s,%s,%s)
                            """,
                            (item["task"], item["done"], saved_id),
                        )

                    saved_workouts.append({
                        "id": saved_id,
                        "name": name,
                        "description": description,
                        "equipment": equipment,
                        "checklist": checklist,
                    })

        if not saved_workouts:
            return jsonify({"error": "no workouts saved"}), 409

        return jsonify({
            "message": "workouts saved",
            "saved_workouts": saved_workouts,
        }), 201

    except Exception as e:
        current_app.logger.exception("Save workout failed")
        return jsonify({"error": str(e)}), 500


# Dummy Paystack Payment Integration
@public_bp.route('/paystack/dummy-payment', methods=['POST'])
def dummy_paystack_payment():
    data = request.get_json()

    # Validate request payload
    if not data or 'email' not in data or 'amount' not in data:
        return jsonify({"error": "Email and amount are required"}), 400

    email = data['email']
    amount = data['amount']

    # Simulate Paystack payment initialization
    paystack_response = {
        "status": True,
        "message": "Payment initialized successfully",
        "data": {
            "authorization_url": "https://paystack.com/dummy-authorization",
            "access_code": "DUMMY_ACCESS_CODE",
            "reference": "DUMMY_REFERENCE"
        }
    }

    return jsonify(paystack_response), 200
