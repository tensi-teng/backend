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
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        if not name:
            return jsonify({'error': 'name required'}), 400

        description = data.get('description', '')
        equipment = data.get('equipment', [])
        user_id = int(get_jwt_identity())

        eq_str = ",".join(equipment) if isinstance(equipment, list) else (equipment or "")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    '''
                    INSERT INTO workouts (name, description, equipment, user_id)
                    VALUES (%s,%s,%s,%s) RETURNING id
                    ''',
                    (name, description, eq_str, user_id)
                )
                wid = cur.fetchone()[0]

                items = generate_checklist(equipment if isinstance(equipment, list) else [])
                for it in items:
                    cur.execute(
                        'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                        (it["task"], it["done"], wid)
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
        workouts = []

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    '''
                    SELECT id, name, description, equipment
                    FROM workouts WHERE user_id=%s ORDER BY id DESC
                    ''',
                    (user_id,)
                )
                workouts.extend(cur.fetchall())

                cur.execute(
                    '''
                    SELECT id, name, description, equipment
                    FROM saved_workouts WHERE user_id=%s ORDER BY id DESC
                    ''',
                    (user_id,)
                )
                workouts.extend(cur.fetchall())

        out = []
        for r in workouts:
            eq = [e.strip() for e in (r['equipment'] or "").split(",") if e]
            out.append({
                'id': r['id'],
                'name': r['name'],
                'description': r.get('description'),
                'equipment': eq
            })

        return jsonify(out), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ---------------- UPDATE WORKOUT ----------------
@workouts_bp.route('/workouts/<int:wid>', methods=['PUT'])
@jwt_required()
def update_workout(wid):
    try:
        data = request.get_json(silent=True) or {}
        user_id = int(get_jwt_identity())

        name = data.get('name')
        description = data.get('description')
        equipment = data.get('equipment')

        with get_conn() as conn:
            with conn.cursor() as cur:

                # Check workouts table
                cur.execute('SELECT user_id FROM workouts WHERE id=%s', (wid,))
                row = cur.fetchone()
                table = 'workouts'

                # If not in workouts, check saved_workouts
                if not row:
                    cur.execute('SELECT user_id FROM saved_workouts WHERE id=%s', (wid,))
                    row = cur.fetchone()
                    table = 'saved_workouts'

                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                # Update fields
                if name:
                    cur.execute(
                        sql.SQL("UPDATE {tbl} SET name=%s WHERE id=%s")
                        .format(tbl=sql.Identifier(table)),
                        (name, wid)
                    )

                if description is not None:
                    cur.execute(
                        sql.SQL("UPDATE {tbl} SET description=%s WHERE id=%s")
                        .format(tbl=sql.Identifier(table)),
                        (description, wid)
                    )

                if equipment is not None:
                    eq_str = ",".join(equipment) if isinstance(equipment, list) else (equipment or "")
                    cur.execute(
                        sql.SQL("UPDATE {tbl} SET equipment=%s WHERE id=%s")
                        .format(tbl=sql.Identifier(table)),
                        (eq_str, wid)
                    )

                    # Reset checklist
                    cur.execute('DELETE FROM checklist_items WHERE workout_id=%s', (wid,))
                    items = generate_checklist(equipment if isinstance(equipment, list) else [])
                    for it in items:
                        cur.execute(
                            'INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)',
                            (it["task"], it["done"], wid)
                        )

        return jsonify({'message': 'updated'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ---------------- DELETE WORKOUT(S) ----------------
@workouts_bp.route('/workouts/<wid>', methods=['DELETE'])
@jwt_required()
def delete_workout(wid):
    try:
        user_id = int(get_jwt_identity())
        ids_to_delete = []

        with get_conn() as conn:
            with conn.cursor() as cur:

                # DELETE ALL
                if wid.lower() == 'all':
                    cur.execute('SELECT id FROM workouts WHERE user_id=%s', (user_id,))
                    ids_to_delete.extend([r[0] for r in cur.fetchall()])

                    cur.execute('SELECT id FROM saved_workouts WHERE user_id=%s', (user_id,))
                    ids_to_delete.extend([r[0] for r in cur.fetchall()])
                else:
                    ids = [int(w.strip()) for w in wid.split(',')]

                    # Check workouts
                    cur.execute(
                        'SELECT id FROM workouts WHERE id = ANY(%s) AND user_id=%s',
                        (ids, user_id)
                    )
                    ids_to_delete.extend([r[0] for r in cur.fetchall()])

                    # Check saved_workouts
                    cur.execute(
                        'SELECT id FROM saved_workouts WHERE id = ANY(%s) AND user_id=%s',
                        (ids, user_id)
                    )
                    ids_to_delete.extend([r[0] for r in cur.fetchall()])

                if not ids_to_delete:
                    return jsonify({'message': 'nothing to delete'}), 200

                # DELETE EVERYTHING FOUND
                cur.execute('DELETE FROM workouts WHERE id = ANY(%s)', (ids_to_delete,))
                cur.execute('DELETE FROM saved_workouts WHERE id = ANY(%s)', (ids_to_delete,))
                cur.execute('DELETE FROM checklist_items WHERE workout_id = ANY(%s)', (ids_to_delete,))

        return jsonify({'message': 'deleted', 'deleted_ids': ids_to_delete}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ---------------- TOGGLE CHECKLIST ITEM(S) ----------------
@workouts_bp.route('/checklist/<item_id>', methods=['PATCH'])
@jwt_required()
def toggle_checklist_item(item_id):
    try:
        user_id = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor() as cur:

                if item_id.lower() == 'all':
                    cur.execute(
                        '''
                        SELECT ci.id, ci.done
                        FROM checklist_items ci
                        JOIN workouts w ON ci.workout_id = w.id
                        WHERE w.user_id=%s
                        UNION
                        SELECT ci.id, ci.done
                        FROM checklist_items ci
                        JOIN saved_workouts sw ON ci.workout_id = sw.id
                        WHERE sw.user_id=%s
                        ''',
                        (user_id, user_id)
                    )
                    items = cur.fetchall()
                else:
                    ids = [int(i.strip()) for i in item_id.split(',')]
                    cur.execute(
                        '''
                        SELECT ci.id, ci.done
                        FROM checklist_items ci
                        JOIN workouts w ON ci.workout_id = w.id
                        WHERE ci.id = ANY(%s) AND w.user_id=%s
                        UNION
                        SELECT ci.id, ci.done
                        FROM checklist_items ci
                        JOIN saved_workouts sw ON ci.workout_id = sw.id
                        WHERE ci.id = ANY(%s) AND sw.user_id=%s
                        ''',
                        (ids, user_id, ids, user_id)
                    )
                    items = cur.fetchall()

                if not items:
                    return jsonify({'message': 'no items found'}), 404

                toggled = []
                for cid, done in items:
                    new_done = not done
                    cur.execute('UPDATE checklist_items SET done=%s WHERE id=%s', (new_done, cid))
                    toggled.append({'id': cid, 'done': new_done})

        return jsonify({'message': 'toggled', 'toggled_items': toggled}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ---------------- LIST ALL CHECKLIST ITEMS ----------------
@workouts_bp.route('/checklist', methods=['GET'])
@jwt_required()
def list_all_checklist_items():
    try:
        user_id = int(get_jwt_identity())
        all_items = []

        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                for table in ['workouts', 'saved_workouts']:
                    query = sql.SQL(
                        '''
                        SELECT ci.id, ci.task, ci.done, ci.workout_id, w.name AS workout_name
                        FROM checklist_items ci
                        JOIN {tbl} w ON ci.workout_id = w.id
                        WHERE w.user_id=%s
                        '''
                    ).format(tbl=sql.Identifier(table))
                    cur.execute(query, (user_id,))
                    all_items.extend(cur.fetchall())

        return jsonify(all_items), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
