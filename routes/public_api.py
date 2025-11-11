import os
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, jwt_required
from utils.generate_checklist import generate_checklist
from db import get_conn
import psycopg

public_bp = Blueprint('public_api', __name__)
DB_URL = os.getenv('DATABASE_URL')

# ---------------- GET PUBLIC WORKOUTS ----------------
@public_bp.route('/workouts', methods=['GET'])
def get_workouts():
    user_id = None
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except Exception:
        user_id = None

    type_filter = request.args.get('type')
    muscle_filter = request.args.get('muscle')
    level_filter = request.args.get('level')

    try:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                query = "SELECT id, name, equipment, type, muscles, level, instructions FROM public_workouts WHERE 1=1"
                params = []

                if type_filter:
                    query += " AND LOWER(type) LIKE LOWER(%s)"
                    params.append(f"%{type_filter}%")
                if muscle_filter:
                    # muscles is an array, use ANY for partial match
                    query += " AND EXISTS (SELECT 1 FROM unnest(muscles) m WHERE LOWER(m) LIKE LOWER(%s))"
                    params.append(f"%{muscle_filter}%")
                if level_filter:
                    query += " AND LOWER(level) LIKE LOWER(%s)"
                    params.append(f"%{level_filter}%")

                cur.execute(query, params)
                rows = cur.fetchall()
                workouts = [dict(row) for row in rows]

        return jsonify({
            'user_id': user_id,
            'count': len(workouts),
            'workouts': workouts
        }), 200
    except Exception as e:
        current_app.logger.exception('Error fetching public workouts')
        return jsonify({'error': 'database error', 'detail': str(e)}), 500


# ---------------- SAVE PUBLIC WORKOUT ----------------
@public_bp.route('/workouts/save/<int:public_workout_id>', methods=['POST'])
@jwt_required()
def save_public_workout(public_workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        custom_name = data.get('name')
        custom_description = data.get('description')
        custom_equipment = data.get('equipment')

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute('SELECT * FROM public_workouts WHERE id=%s', (public_workout_id,))
                pw = cur.fetchone()
                if not pw:
                    return jsonify({'error': 'public workout not found'}), 404

                cur.execute(
                    'SELECT id FROM saved_workouts WHERE user_id=%s AND public_workout_id=%s',
                    (user_id, public_workout_id)
                )
                if cur.fetchone():
                    return jsonify({'error': 'already saved'}), 400

                name = custom_name or pw['name']
                description = custom_description or pw.get('instructions') or ''
                equipment = custom_equipment or (pw['equipment'].split(',') if pw['equipment'] else [])
                eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')

                cur.execute(
                    '''
                    INSERT INTO saved_workouts
                    (user_id, public_workout_id, name, description, equipment, type, muscles, level)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    ''',
                    (user_id, public_workout_id, name, description, eq_str,
                     pw.get('type'), pw.get('muscles'), pw.get('level'))
                )
                saved_id = cur.fetchone()[0]

                items = generate_checklist(equipment if isinstance(equipment, list) else [])
                for it in items:
                    cur.execute(
                        'INSERT INTO checklist_items (task, done, workout_id, source) VALUES (%s,%s,%s,%s)',
                        (it['task'], it['done'], saved_id, 'saved')
                    )

        return jsonify({
            'message': 'public workout saved',
            'saved_workout': {
                'id': saved_id,
                'name': name,
                'description': description,
                'equipment': equipment,
                'checklist': items
            }
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

