import os
import json
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, jwt_required
from utils.generate_checklist import generate_checklist
from db import get_conn
import psycopg

public_bp = Blueprint('public_api', __name__)
DB_URL = os.getenv('DATABASE_URL')


# ---------------------------------------------------
# Universal Request Data Loader
# Returns dict if body exists, else None
# ---------------------------------------------------
def get_request_data():
    if request.is_json:
        return request.get_json()
    try:
        data = json.loads(request.data)
        return data if isinstance(data, dict) else None
    except:
        pass
    if request.form:
        return request.form.to_dict(flat=True)
    return None


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


# ---------------- SAVE PUBLIC WORKOUT(S) ----------------
@public_bp.route('/workouts/save', methods=['POST'])
@public_bp.route('/workouts/save/<int:public_workout_id>', methods=['POST'])
@jwt_required()
def save_public_workouts(public_workout_id=None):
    try:
        user_id = int(get_jwt_identity())

        # Load request data
        data = get_request_data()

        # If no URL ID, require body
        if not data and public_workout_id is None:
            return jsonify({'error': 'Request body required'}), 400

        # Determine list of workout IDs to save
        if public_workout_id is not None:
            workout_ids = [public_workout_id]
        else:
            workout_ids = data.get('workout_ids', [])

            # Normalize single number
            if isinstance(workout_ids, int):
                workout_ids = [workout_ids]

            if not isinstance(workout_ids, list):
                return jsonify({'error': 'workout_ids must be an int or list of ints'}), 400

        if not workout_ids:
            return jsonify({'error': 'workout_ids required'}), 400

        saved_workouts = []

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                for wid in workout_ids:

                    # Overrides support
                    overrides = data.get('overrides', {}).get(str(wid), {}) if data else {}
                    custom_name = overrides.get('name')
                    custom_description = overrides.get('description')
                    custom_equipment = overrides.get('equipment')

                    # Fetch the public workout
                    cur.execute('SELECT * FROM public_workouts WHERE id=%s', (wid,))
                    public_w = cur.fetchone()

                    if not public_w:
                        continue

                    # Check if already saved
                    cur.execute(
                        'SELECT * FROM saved_workouts WHERE user_id=%s AND public_workout_id=%s',
                        (user_id, wid)
                    )
                    existing_saved = cur.fetchone()

                    if existing_saved:
                        # Already saved – return existing data
                        saved_id = existing_saved['id']

                        # Load checklist
                        cur.execute(
                            'SELECT id, task, done, workout_id FROM checklist_items WHERE workout_id=%s',
                            (saved_id,)
                        )
                        checklist = cur.fetchall()

                        saved_workouts.append({
                            'id': saved_id,
                            'name': existing_saved['name'],
                            'description': existing_saved['description'],
                            'equipment': existing_saved['equipment'].split(',') if existing_saved['equipment'] else [],
                            'checklist': checklist
                        })
                        continue

                    # Build new values
                    name = custom_name or public_w['name']
                    description = custom_description or public_w.get('instructions') or ''
                    equipment = custom_equipment or (
                        public_w['equipment'].split(',') if public_w['equipment'] else []
                    )

                    eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')

                    # Insert saved workout
                    cur.execute(
                        '''
                        INSERT INTO saved_workouts
                        (user_id, public_workout_id, name, description, equipment, type, muscles, level)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                        ''',
                        (
                            user_id, wid, name, description, eq_str,
                            public_w.get('type'), public_w.get('muscles'), public_w.get('level')
                        )
                    )
                    saved_id = cur.fetchone()[0]

                    # Generate checklist if equipment exists
                    checklist = generate_checklist(equipment) if equipment else []

                    for item in checklist:
                        cur.execute(
                            'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                            (item['task'], item['done'], saved_id)
                        )

                    saved_workouts.append({
                        'id': saved_id,
                        'name': name,
                        'description': description,
                        'equipment': equipment,
                        'checklist': checklist
                    })

        if not saved_workouts:
            return jsonify({'error': 'no workouts saved (invalid IDs)'}), 409

        return jsonify({'message': 'workouts saved', 'saved_workouts': saved_workouts}), 201

    except Exception as e:
        current_app.logger.exception('Save workout failed')
        return jsonify({'error': str(e)}), 500
