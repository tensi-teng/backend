import psycopg
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist

workouts_bp = Blueprint('workouts', __name__)

# ---------------- CREATE USER WORKOUT ----------------
@workouts_bp.route('/workouts', methods=['POST'])
@jwt_required()
def create_workout():
    try:
        data = request.get_json() or {}
        name = data.get('name')
        if not name:
            return jsonify({'error': 'name required'}), 400

        description = data.get('description', '')
        equipment = data.get('equipment', [])
        user_id = int(get_jwt_identity())
        eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO workouts (name, description, equipment, user_id) VALUES (%s,%s,%s,%s) RETURNING id',
                    (name, description, eq_str, user_id)
                )
                wid = cur.fetchone()[0]

                items = generate_checklist(equipment if isinstance(equipment, list) else [])
                for it in items:
                    cur.execute(
                        'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                        (it['task'], it['done'], wid)
                    )

        return jsonify({
            'message': 'created',
            'workout': {
                'id': wid,
                'name': name,
                'description': description,
                'equipment': equipment
            }
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- LIST USER WORKOUTS ----------------
@workouts_bp.route('/workouts', methods=['GET'])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    'SELECT id, name, description, equipment FROM workouts WHERE user_id=%s ORDER BY id DESC',
                    (user_id,)
                )
                rows = cur.fetchall()

            out = []
            with conn.cursor(row_factory=psycopg.rows.dict_row) as checklist_cur:
                for r in rows:
                    eq = [e.strip() for e in (r['equipment'] or '').split(',') if e]
                    checklist_cur.execute(
                        'SELECT id, task, done FROM checklist_items WHERE workout_id=%s', 
                        (r['id'],)
                    )
                    checklist = [{'id': c['id'], 'task': c['task'], 'done': c['done']} for c in checklist_cur.fetchall()]
                    out.append({
                        'id': r['id'],
                        'name': r['name'],
                        'description': r['description'],
                        'equipment': eq,
                        'checklist': checklist
                    })

        return jsonify(out), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ---------------- UPDATE WORKOUT / SAVED WORKOUT ----------------
@workouts_bp.route('/workouts/<source>/<int:wid>', methods=['PUT'])
@jwt_required()
def update_workout(source, wid):
    try:
        user_id = int(get_jwt_identity())
        if source not in ['workouts', 'saved']:
            return jsonify({"error": "Invalid source"}), 400

        data = request.get_json() or {}
        table = 'workouts' if source == 'workouts' else 'saved_workouts'

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT user_id FROM {table} WHERE id=%s', (wid,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                # Update fields
                if 'name' in data:
                    cur.execute(f'UPDATE {table} SET name=%s WHERE id=%s', (data['name'], wid))
                if 'description' in data and source == 'workouts':
                    cur.execute(f'UPDATE {table} SET description=%s WHERE id=%s', (data['description'], wid))
                if 'equipment' in data:
                    eq_str = ','.join(data['equipment']) if isinstance(data['equipment'], list) else (data['equipment'] or '')
                    cur.execute(f'UPDATE {table} SET equipment=%s WHERE id=%s', (eq_str, wid))
                    cur.execute('DELETE FROM checklist_items WHERE workout_id=%s', (wid,))
                    items = generate_checklist(data['equipment'] if isinstance(data['equipment'], list) else [])
                    for it in items:
                        cur.execute('INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                                    (it['task'], it['done'], wid))

        return jsonify({'message': 'updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- DELETE WORKOUT / SAVED WORKOUT ----------------
@workouts_bp.route('/workouts/<source>/<int:wid>', methods=['DELETE'])
@jwt_required()
def delete_workout(source, wid):
    try:
        user_id = int(get_jwt_identity())
        if source not in ['workouts', 'saved']:
            return jsonify({"error": "Invalid source"}), 400

        table = 'workouts' if source == 'workouts' else 'saved_workouts'

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT user_id FROM {table} WHERE id=%s', (wid,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({"error": "not found or not allowed"}), 404
                cur.execute(f'DELETE FROM {table} WHERE id=%s', (wid,))

        return jsonify({'message': 'deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- SAVE PUBLIC WORKOUT ----------------
@workouts_bp.route('/workouts/save/<int:workout_id>', methods=['POST'])
@jwt_required()
def save_public_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT name, equipment, type, muscles, level FROM public_workouts WHERE id=%s',
                    (workout_id,)
                )
                workout = cur.fetchone()
                if not workout:
                    return jsonify({"error": "Public workout not found"}), 404

                # Check duplicate
                cur.execute(
                    'SELECT id FROM saved_workouts WHERE user_id=%s AND public_workout_id=%s',
                    (user_id, workout_id)
                )
                if cur.fetchone():
                    return jsonify({"error": "Workout already saved"}), 409

                custom_name = data.get('name', workout[0])
                cur.execute(
                    'INSERT INTO saved_workouts '
                    '(user_id, public_workout_id, name, equipment, type, muscles, level) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                    (user_id, workout_id, custom_name, workout[1], workout[2], workout[3], workout[4])
                )
                saved_id = cur.fetchone()[0]

                equipment_list = [e.strip() for e in (workout[1] or '').split(',') if e]
                if equipment_list:
                    checklist = generate_checklist(equipment_list)
                    for item in checklist:
                        cur.execute(
                            'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                            (item['task'], False, saved_id)
                        )

        return jsonify({"message": "saved", "id": saved_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- LIST SAVED WORKOUTS ----------------
@workouts_bp.route('/saved', methods=['GET'])
@jwt_required()
def list_saved_workouts():
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    'SELECT id, name, equipment, type, muscles, level FROM saved_workouts '
                    'WHERE user_id=%s ORDER BY created_at DESC',
                    (user_id,)
                )
                workouts = cur.fetchall()
                for w in workouts:
                    cur.execute('SELECT id, task, done FROM checklist_items WHERE workout_id=%s', (w['id'],))
                    w['checklist'] = [{'id': c[0], 'task': c[1], 'done': c[2]} for c in cur.fetchall()]

        return jsonify(workouts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- TOGGLE CHECKLIST ITEM ----------------
@workouts_bp.route('/checklist/<source>/<int:item_id>', methods=['PATCH'])
@jwt_required()
def toggle_checklist_item(source, item_id):
    try:
        user_id = int(get_jwt_identity())
        if source not in ['workouts', 'saved']:
            return jsonify({"error": "Invalid source"}), 400

        table = 'workouts' if source == 'workouts' else 'saved_workouts'

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT ci.done, w.user_id FROM checklist_items ci '
                    f'JOIN {table} w ON ci.workout_id=w.id WHERE ci.id=%s',
                    (item_id,)
                )
                row = cur.fetchone()
                if not row or row[1] != user_id:
                    return jsonify({"error": "not allowed"}), 403

                new_done = not row[0]
                cur.execute('UPDATE checklist_items SET done=%s WHERE id=%s', (new_done, item_id))

        return jsonify({"message": "toggled", "done": new_done}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- LIST ALL CHECKLIST ITEMS FOR USER ----------------
@workouts_bp.route('/checklist', methods=['GET'])
@jwt_required()
def list_checklist_items():
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                # Personal workouts
                cur.execute(
                    'SELECT ci.id, ci.task, ci.done, ci.workout_id, w.name AS workout_name '
                    'FROM checklist_items ci '
                    'JOIN workouts w ON ci.workout_id=w.id '
                    'WHERE w.user_id=%s',
                    (user_id,)
                )
                user_workout_items = cur.fetchall()

                # Saved workouts
                cur.execute(
                    'SELECT ci.id, ci.task, ci.done, ci.workout_id, sw.name AS workout_name '
                    'FROM checklist_items ci '
                    'JOIN saved_workouts sw ON ci.workout_id=sw.id '
                    'WHERE sw.user_id=%s',
                    (user_id,)
                )
                saved_workout_items = cur.fetchall()

        all_items = user_workout_items + saved_workout_items
        return jsonify(all_items), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
