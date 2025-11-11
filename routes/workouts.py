import psycopg
from psycopg import sql
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
                        'INSERT INTO checklist_items (task, done, workout_id, source) VALUES (%s,%s,%s,%s)',
                        (it['task'], it['done'], wid, 'workouts')
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
                # Fetch user workouts
                cur.execute(
                    'SELECT id, name, description, equipment FROM workouts WHERE user_id=%s ORDER BY id DESC',
                    (user_id,)
                )
                user_rows = cur.fetchall()

                # Fetch saved workouts
                cur.execute(
                    'SELECT id, name, description, equipment FROM saved_workouts WHERE user_id=%s ORDER BY id DESC',
                    (user_id,)
                )
                saved_rows = cur.fetchall()

            out = []

            with conn.cursor(row_factory=psycopg.rows.dict_row) as checklist_cur:
                # Combine user and saved workouts
                for r, src in [(r, 'workouts') for r in user_rows] + [(r, 'saved') for r in saved_rows]:
                    eq = [e.strip() for e in (r['equipment'] or '').split(',') if e]
                    checklist_cur.execute(
                        'SELECT id, task, done FROM checklist_items WHERE workout_id=%s AND source=%s',
                        (r['id'], src)
                    )
                    checklist = [{'id': c['id'], 'task': c['task'], 'done': c['done']} for c in checklist_cur.fetchall()]
                    out.append({
                        'id': r['id'],
                        'name': r['name'],
                        'description': r.get('description'),
                        'equipment': eq,
                        'checklist': checklist,
                        'source': src
                    })

        return jsonify(out), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ---------------- UPDATE WORKOUT ----------------
@workouts_bp.route('/workouts/<string:source>/<int:wid>', methods=['PUT'])
@jwt_required()
def update_workout(source, wid):
    try:
        if source not in ('workouts', 'saved'):
            return jsonify({'error': 'invalid source'}), 400

        data = request.get_json() or {}
        user_id = int(get_jwt_identity())
        name = data.get('name')
        description = data.get('description')
        equipment = data.get('equipment')

        table = 'workouts' if source == 'workouts' else 'saved_workouts'

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL('SELECT user_id FROM {table} WHERE id=%s').format(
                    table=sql.Identifier(table)
                ), (wid,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                if name:
                    cur.execute(sql.SQL('UPDATE {table} SET name=%s WHERE id=%s').format(
                        table=sql.Identifier(table)
                    ), (name, wid))
                if description is not None:
                    cur.execute(sql.SQL('UPDATE {table} SET description=%s WHERE id=%s').format(
                        table=sql.Identifier(table)
                    ), (description, wid))
                if equipment is not None:
                    eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')
                    cur.execute(sql.SQL('UPDATE {table} SET equipment=%s WHERE id=%s').format(
                        table=sql.Identifier(table)
                    ), (eq_str, wid))

                    # Reset checklist
                    cur.execute(
                        'DELETE FROM checklist_items WHERE workout_id=%s AND source=%s',
                        (wid, source)
                    )
                    items = generate_checklist(equipment if isinstance(equipment, list) else [])
                    for it in items:
                        cur.execute(
                            'INSERT INTO checklist_items (task, done, workout_id, source) VALUES (%s,%s,%s,%s)',
                            (it['task'], it['done'], wid, source)
                        )

        return jsonify({'message': 'updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- SAVE PUBLIC WORKOUT ----------------
@workouts_bp.route('/workouts/save/<int:public_workout_id>', methods=['POST'])
@jwt_required()
def save_public_workout(public_workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        # Optional overrides
        custom_name = data.get('name')
        custom_description = data.get('description')
        custom_equipment = data.get('equipment')

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                # Fetch public workout
                cur.execute(
                    'SELECT * FROM public_workouts WHERE id=%s',
                    (public_workout_id,)
                )
                pw = cur.fetchone()
                if not pw:
                    return jsonify({'error': 'public workout not found'}), 404

                # Check if already saved
                cur.execute(
                    'SELECT id FROM saved_workouts WHERE user_id=%s AND public_workout_id=%s',
                    (user_id, public_workout_id)
                )
                if cur.fetchone():
                    return jsonify({'error': 'already saved'}), 400

                # Prepare values
                name = custom_name or pw['name']
                description = custom_description or pw.get('instructions') or ''
                equipment = custom_equipment or (pw['equipment'].split(',') if pw['equipment'] else [])
                eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')

                # Insert into saved_workouts
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

                # Generate checklist items
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

# ---------------- DELETE WORKOUT ----------------
@workouts_bp.route('/workouts/<string:source>/<int:wid>', methods=['DELETE'])
@jwt_required()
def delete_workout(source, wid):
    try:
        if source not in ('workouts', 'saved'):
            return jsonify({'error': 'invalid source'}), 400

        user_id = int(get_jwt_identity())
        table = 'workouts' if source == 'workouts' else 'saved_workouts'

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL('SELECT user_id FROM {table} WHERE id=%s').format(
                    table=sql.Identifier(table)
                ), (wid,))
                row = cur.fetchone()
                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                cur.execute(sql.SQL('DELETE FROM {table} WHERE id=%s').format(
                    table=sql.Identifier(table)
                ), (wid,))
                cur.execute('DELETE FROM checklist_items WHERE workout_id=%s AND source=%s', (wid, source))

        return jsonify({'message': 'deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------- TOGGLE CHECKLIST ITEM ----------------
@workouts_bp.route('/checklist/<string:source>/<int:item_id>', methods=['PATCH'])
@jwt_required()
def toggle_checklist_item(source, item_id):
    try:
        if source not in ('workouts', 'saved'):
            return jsonify({'error': 'invalid source'}), 400

        user_id = int(get_jwt_identity())
        table = 'workouts' if source == 'workouts' else 'saved_workouts'

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        'SELECT ci.done, w.user_id FROM checklist_items ci '
                        'JOIN {table} w ON ci.workout_id=w.id '
                        'WHERE ci.id=%s AND ci.source=%s'
                    ).format(table=sql.Identifier(table)),
                    (item_id, source)
                )
                row = cur.fetchone()
                if not row or row[1] != user_id:
                    return jsonify({'error': 'not allowed'}), 403

                new_done = not row[0]
                cur.execute('UPDATE checklist_items SET done=%s WHERE id=%s', (new_done, item_id))

        return jsonify({'message': 'toggled', 'done': new_done}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------- LIST ALL CHECKLIST ITEMS FOR USER ----------------
@workouts_bp.route('/checklist', methods=['GET'])
@jwt_required()
def list_all_checklist_items():
    try:
        user_id = int(get_jwt_identity())
        all_items = []

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                for source, table in [('workouts', 'workouts'), ('saved', 'saved_workouts')]:
                    query = sql.SQL(
                        "SELECT ci.id, ci.task, ci.done, ci.workout_id, w.name AS workout_name, %s AS source "
                        "FROM checklist_items ci "
                        "JOIN {table} w ON ci.workout_id = w.id "
                        "WHERE w.user_id = %s"
                    ).format(table=sql.Identifier(table))

                    # Convert to string for psycopg to avoid IDE/type warnings
                    cur.execute(query.as_string(conn), (source, user_id))
                    items = cur.fetchall()
                    all_items.extend(items)

        return jsonify(all_items), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
