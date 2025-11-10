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

                for r in rows:
                    eq = [e for e in (r['equipment'] or '').split(',') if e]
                    cur.execute('SELECT id, task, done FROM checklist_items WHERE workout_id=%s', (r['id'],))
                    checklist = [{'id': c[0], 'task': c[1], 'done': c[2]} for c in cur.fetchall()]
                    out.append({
                        'id': r['id'],
                        'name': r['name'],
                        'description': r['description'],
                        'equipment': eq,
                        'checklist': checklist
                    })

        return jsonify(out), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- UPDATE USER WORKOUT ----------------
@workouts_bp.route('/workouts/<int:wid>', methods=['PUT'])
@jwt_required()
def update_workout(wid):
    try:
        data = request.get_json() or {}
        user_id = int(get_jwt_identity())
        name = data.get('name')
        description = data.get('description')
        equipment = data.get('equipment')

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT user_id FROM workouts WHERE id=%s', (wid,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                if name:
                    cur.execute('UPDATE workouts SET name=%s WHERE id=%s', (name, wid))
                if description is not None:
                    cur.execute('UPDATE workouts SET description=%s WHERE id=%s', (description, wid))
                if equipment is not None:
                    eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')
                    cur.execute('UPDATE workouts SET equipment=%s WHERE id=%s', (eq_str, wid))
                    cur.execute('DELETE FROM checklist_items WHERE workout_id=%s', (wid,))
                    items = generate_checklist(equipment if isinstance(equipment, list) else [])
                    for it in items:
                        cur.execute('INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                                    (it['task'], it['done'], wid))

        return jsonify({'message': 'updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- DELETE USER WORKOUT ----------------
@workouts_bp.route('/workouts/<int:wid>', methods=['DELETE'])
@jwt_required()
def delete_workout(wid):
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT user_id FROM workouts WHERE id=%s', (wid,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404
                cur.execute('DELETE FROM workouts WHERE id=%s', (wid,))
        return jsonify({'message': 'deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- TOGGLE CHECKLIST ITEM ----------------
@workouts_bp.route('/checklist/<int:item_id>', methods=['PATCH'])
@jwt_required()
def toggle_checklist(item_id):
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT ci.done, w.user_id FROM checklist_items ci '
                    'JOIN workouts w ON ci.workout_id=w.id WHERE ci.id=%s',
                    (item_id,)
                )
                row = cur.fetchone()
                if not row or row[1] != user_id:
                    return jsonify({'error': 'not allowed'}), 403

                new_done = not row[0]
                cur.execute('UPDATE checklist_items SET done=%s WHERE id=%s', (new_done, item_id))

        return jsonify({'message': 'toggled', 'done': new_done}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- SAVE PUBLIC WORKOUT ----------------
@workouts_bp.route('/public', methods=['GET'])
@jwt_required(optional=True) 
def list_public_workouts():
    try:
        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    'SELECT id, name, description, equipment, type, muscles, level '
                    'FROM public_workouts ORDER BY id DESC'
                )
                workouts = cur.fetchall() or []
        return jsonify(workouts), 200
    except Exception as e:
        import traceback
        print("❌ Error in list_public_workouts:", e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@workouts_bp.route('/public/save/<int:workout_id>', methods=['POST'])
@jwt_required()
def save_public_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT name, description, equipment, type, muscles, level FROM public_workouts WHERE id=%s',
                    (workout_id,)
                )
                workout = cur.fetchone()
                if not workout:
                    return jsonify({"error": "Public workout not found"}), 404

                # Check duplicate
                cur.execute('SELECT id FROM saved_workouts WHERE user_id=%s AND public_workout_id=%s',
                            (user_id, workout_id))
                if cur.fetchone():
                    return jsonify({"error": "Workout already saved"}), 409

                custom_name = data.get('name', workout[0])
                cur.execute(
                    'INSERT INTO saved_workouts '
                    '(user_id, public_workout_id, name, description, equipment, type, muscles, level) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                    (user_id, workout_id, custom_name, workout[1], workout[2], workout[3], workout[4], workout[5])
                )
                saved_id = cur.fetchone()[0]

                # Generate checklist if equipment exists
                equipment_list = [e.strip() for e in (workout[2] or '').split(',')]
                if equipment_list:
                    checklist = generate_checklist(equipment_list)
                    for item in checklist:
                        cur.execute('INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                                    (item['task'], False, saved_id))

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
                    'SELECT id, name, description, equipment, type, muscles, level '
                    'FROM saved_workouts WHERE user_id=%s ORDER BY created_at DESC',
                    (user_id,)
                )
                workouts = cur.fetchall()

                for w in workouts:
                    cur.execute('SELECT id, task, done FROM checklist_items WHERE workout_id=%s', (w['id'],))
                    w['checklist'] = [{'id': c[0], 'task': c[1], 'done': c[2]} for c in cur.fetchall()]

        return jsonify(workouts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- UPDATE SAVED WORKOUT ----------------
@workouts_bp.route('/saved/<int:workout_id>', methods=['PUT'])
@jwt_required()
def update_saved_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM saved_workouts WHERE id=%s AND user_id=%s', (workout_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Workout not found"}), 404

                if 'name' in data:
                    cur.execute('UPDATE saved_workouts SET name=%s WHERE id=%s', (data['name'], workout_id))
                if 'description' in data:
                    cur.execute('UPDATE saved_workouts SET description=%s WHERE id=%s', (data['description'], workout_id))

        return jsonify({"message": "updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- DELETE SAVED WORKOUT ----------------
@workouts_bp.route('/saved/<int:workout_id>', methods=['DELETE'])
@jwt_required()
def delete_saved_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM saved_workouts WHERE id=%s AND user_id=%s RETURNING id',
                            (workout_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Workout not found"}), 404
        return jsonify({"message": "deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- TOGGLE CHECKLIST FOR SAVED WORKOUT ----------------
@workouts_bp.route('/checklist/<int:item_id>', methods=['PATCH'])
@jwt_required()
def toggle_saved_checklist(item_id):
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT ci.done, sw.user_id FROM checklist_items ci '
                    'JOIN saved_workouts sw ON ci.workout_id=sw.id WHERE ci.id=%s',
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
