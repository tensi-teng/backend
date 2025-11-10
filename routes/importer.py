
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist

import_bp = Blueprint('importer', __name__)

@import_bp.route('/import', methods=['POST'])
@jwt_required()
def import_workout():
    data = request.get_json() or {}
    # Accept JSON payload for a workout (name, description, equipment)
    name = data.get('name')
    description = data.get('description')
    equipment = data.get('equipment', [])
    if not name:
        return jsonify({'error':'name required'}), 400
    user_id = str(get_jwt_identity())
    eq_str = ','.join(equipment) if isinstance(equipment, list) else equipment
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO workouts (name, description, equipment, user_id) VALUES (%s,%s,%s,%s) RETURNING id', (name, description, eq_str, user_id))
            wid = cur.fetchone()[0]
            checklist = generate_checklist(equipment)
            for it in checklist:
                cur.execute('INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)', (it['task'], it['done'], wid))
    return jsonify({'message':'imported', 'workout_id': wid}), 201
