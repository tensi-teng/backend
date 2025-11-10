import psycopg
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist

workouts_bp = Blueprint('workouts', __name__)

@workouts_bp.route('/workouts', methods=['POST'])
@jwt_required()
def create_workout():
    try:
        data = request.get_json() or {}
        name = data.get('name')
        if not name:
            return jsonify({'error': 'name required'}), 400

        description = data.get('description')
        equipment = data.get('equipment', [])
        user_id = int(get_jwt_identity())  # Ensure integer

        eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO workouts (name, description, equipment, user_id) VALUES (%s,%s,%s,%s) RETURNING id',
                    (name, description, eq_str, user_id)
                )
                wid = cur.fetchone()[0]

                # Generate checklist items
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


@workouts_bp.route('/workouts', methods=['GET'])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    'SELECT id, name, description, equipment FROM workouts WHERE user_id=%s ORDER BY created_at DESC',
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

                    # Regenerate checklist
                    cur.execute('DELETE FROM checklist_items WHERE workout_id=%s', (wid,))
                    items = generate_checklist(equipment if isinstance(equipment, list) else [])
                    for it in items:
                        cur.execute(
                            'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                            (it['task'], it['done'], wid)
                        )

        return jsonify({'message': 'updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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


@workouts_bp.route('/checklist/<int:item_id>', methods=['PATCH'])
@jwt_required()
def toggle_checklist(item_id):
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT ci.done, w.user_id FROM checklist_items ci JOIN workouts w ON ci.workout_id=w.id WHERE ci.id=%s',
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
