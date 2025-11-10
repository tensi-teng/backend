from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist
import psycopg

workouts_bp = Blueprint('workouts', __name__)

@workouts_bp.route('/workouts', methods=['POST'])
@jwt_required()
def create_workout():
    # Safely parse JSON
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid or missing JSON"}), 400

    name = data.get('name')
    if not name:
        return jsonify({"error": "name required"}), 400

    description = data.get('description')
    equipment = data.get('equipment', [])
    user_id = str(get_jwt_identity())
    eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')

    # Safe DB connection
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO workouts (name, description, equipment, user_id) VALUES (%s,%s,%s,%s) RETURNING id',
                    (name, description, eq_str, user_id)
                )
                wid = cur.fetchone()[0]

                # generate checklist items
                items = generate_checklist(equipment)
                for it in items:
                    cur.execute(
                        'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                        (it['task'], it['done'], wid)
                    )

    except psycopg.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    return jsonify({
        'message': 'created',
        'workout': {'id': wid, 'name': name, 'description': description, 'equipment': equipment}
    }), 201
