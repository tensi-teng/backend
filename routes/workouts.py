import os
import json      # <-- YOU FORGOT THIS (Critical fix)
import psycopg
from psycopg import sql
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist

# CLOUDINARY CONFIG

import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

workouts_bp = Blueprint('workouts', __name__)

# Add public_id column if missing
try:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE workouts 
                ADD COLUMN IF NOT EXISTS public_id TEXT;
            """)
except Exception:
    pass


# CREATE WORKOUT

@workouts_bp.route('/workouts', methods=['POST'])
@jwt_required()
def create_workout():
    try:
        user_id = int(get_jwt_identity())

        # Detect multipart vs JSON
        if request.content_type and "multipart/form-data" in request.content_type:

            name = request.form.get("name")
            if not name:
                return jsonify({"error": "name required"}), 400

            description = request.form.get("description", "")
            raw_eq = request.form.get("equipment", "")

            # Parse equipment correctly
            try:
                if raw_eq and raw_eq.strip().startswith("["):
                    equipment = json.loads(raw_eq)
                else:
                    equipment = [e.strip() for e in raw_eq.split(",") if e.strip()]
            except Exception:
                equipment = []

            fileobj = request.files.get("file")
            uploaded_url = None
            uploaded_public_id = None

            # Upload file if exists
            if fileobj:
                try:
                    uploaded = cloudinary.uploader.upload(
                        fileobj,
                        folder=f"workouts/{user_id}",
                        use_filename=True,
                        unique_filename=False
                    )
                    uploaded_url = uploaded.get("secure_url")
                    uploaded_public_id = uploaded.get("public_id")

                except Exception as e:
                    return jsonify({"error": f"Cloudinary upload failed: {str(e)}"}), 500

        else:
            # JSON body
            data = request.get_json(silent=True) or {}

            name = data.get("name")
            if not name:
                return jsonify({"error": "name required"}), 400

            description = data.get("description", "")
            equipment = data.get("equipment", [])
            image_remote = data.get("image_url")

            uploaded_url = None
            uploaded_public_id = None

            if image_remote:
                try:
                    uploaded = cloudinary.uploader.upload(
                        image_remote,
                        folder=f"workouts/{user_id}",
                        use_filename=True,
                        unique_filename=False
                    )
                    uploaded_url = uploaded.get("secure_url")
                    uploaded_public_id = uploaded.get("public_id")

                except Exception as e:
                    return jsonify({"error": f"Cloudinary upload failed: {str(e)}"}), 500

        # Store in DB
        eq_str = ",".join(equipment)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO workouts (name, description, equipment, user_id, image_url, public_id)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (name, description, eq_str, user_id, uploaded_url, uploaded_public_id))

                wid = cur.fetchone()[0]

                # Generate checklist
                for it in generate_checklist(equipment):
                    cur.execute("""
                        INSERT INTO checklist_items (task, done, workout_id)
                        VALUES (%s, %s, %s)
                    """, (it["task"], it["done"], wid))

        return jsonify({
            "message": "created",
            "workout": {
                "id": wid,
                "name": name,
                "description": description,
                "equipment": equipment,
                "image_url": uploaded_url
            }
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- LIST USER WORKOUTS ----------------
@workouts_bp.route('/workouts', methods=['GET'])
@jwt_required()
def list_workouts():
    try:
        user_id = int(get_jwt_identity())
        workouts = []

        with get_conn() as conn:
            # use dict_row so fields are accessible by name
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    '''
                    SELECT id, name, description, equipment, image_url
                    FROM workouts WHERE user_id=%s ORDER BY id DESC
                    ''',
                    (user_id,)
                )
                workouts.extend(cur.fetchall())

                cur.execute(
                    '''
                    SELECT id, name, description, equipment, image_url
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
                        'equipment': eq,
                        'image_url': r.get('image_url')
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

                    # Reset checklist (only applies to workouts table: checklist_items references workouts.id)
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
                if isinstance(wid, str) and wid.lower() == 'all':
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

                # Before deleting workouts, remove images from Cloudinary (best-effort)
                # Fetch public_ids for images
                cur.execute('SELECT public_id FROM workouts WHERE id = ANY(%s)', (ids_to_delete,))
                public_ids = [r[0] for r in cur.fetchall() if r[0]]
                for pid in public_ids:
                    try:
                        cloudinary.uploader.destroy(pid, invalidate=True)
                    except Exception:
                        pass

                # DELETE EVERYTHING FOUND (checklist_items & workouts cascade)
                cur.execute('DELETE FROM workouts WHERE id = ANY(%s)', (ids_to_delete,))
                cur.execute('DELETE FROM saved_workouts WHERE id = ANY(%s)', (ids_to_delete,))

                # Also clear any checklist_items (redundant if cascade is working)
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

                if isinstance(item_id, str) and item_id.lower() == 'all':
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


# ---------------- ADD / REPLACE IMAGE FOR A WORKOUT (CLOUDINARY) ----------------
# Accepts multipart/form-data with file under "file" OR JSON with {"image_url": "<remote_url>"}
@workouts_bp.route('/workouts/<int:wid>/image', methods=['POST'])
@jwt_required()
def add_or_replace_workout_image(wid):
    try:
        user_id = int(get_jwt_identity())

        # verify ownership (workouts or saved_workouts)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT user_id, public_id FROM workouts WHERE id=%s', (wid,))
                row = cur.fetchone()
                table = 'workouts'
                existing_public_id = None

                if not row:
                    cur.execute('SELECT user_id FROM saved_workouts WHERE id=%s', (wid,))
                    row = cur.fetchone()
                    table = 'saved_workouts'

                if not row or row[0] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                # If workout was in workouts table fetch public_id (for deletion)
                if table == 'workouts':
                    cur.execute('SELECT public_id FROM workouts WHERE id=%s', (wid,))
                    pid_row = cur.fetchone()
                    existing_public_id = pid_row[0] if pid_row else None

        # figure out upload source
        uploaded = None
        fileobj = request.files.get('file')
        if fileobj:
            uploaded = cloudinary.uploader.upload(
                fileobj,
                folder=f'workouts/{user_id}',
                use_filename=True,
                unique_filename=False,
                overwrite=False
            )
        else:
            data = request.get_json(silent=True) or {}
            image_url = data.get('image_url')
            if not image_url:
                return jsonify({'error': 'file (multipart/form-data) or image_url (JSON) required'}), 400

            uploaded = cloudinary.uploader.upload(
                image_url,
                folder=f'workouts/{user_id}',
                use_filename=True,
                unique_filename=False,
                overwrite=False
            )

        if not uploaded:
            return jsonify({'error': 'upload failed'}), 500

        image_url = uploaded.get('secure_url') or uploaded.get('url')
        public_id = uploaded.get('public_id')

        # store the image_url and public_id in workouts table (only if the workout is in workouts)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE workouts SET image_url=%s, public_id=%s WHERE id=%s',
                    (image_url, public_id, wid)
                )

        # delete old cloudinary resource (best-effort)
        if existing_public_id:
            try:
                cloudinary.uploader.destroy(existing_public_id, invalidate=True)
            except Exception:
                pass

        return jsonify({'message': 'image added', 'image_url': image_url}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------- DELETE IMAGE FOR A WORKOUT (Cloudinary + DB) ----------------
@workouts_bp.route('/workouts/<int:wid>/image', methods=['DELETE'])
@jwt_required()
def delete_workout_image(wid):
    try:
        user_id = int(get_jwt_identity())

        with get_conn() as conn:
            with conn.cursor() as cur:
                # verify ownership and get public_id
                cur.execute(
                    '''
                    SELECT w.public_id, w.user_id
                    FROM workouts w WHERE w.id=%s
                    UNION
                    SELECT NULL AS public_id, sw.user_id
                    FROM saved_workouts sw WHERE sw.id=%s
                    ''',
                    (wid, wid)
                )
                row = cur.fetchone()

                if not row or row[1] != user_id:
                    return jsonify({'error': 'not found or not allowed'}), 404

                public_id = row[0]

                # Clear DB fields on workouts (if present)
                cur.execute('UPDATE workouts SET image_url=NULL, public_id=NULL WHERE id=%s', (wid,))

        # Delete from Cloudinary (best-effort)
        if public_id:
            try:
                cloudinary.uploader.destroy(public_id, invalidate=True)
            except Exception:
                pass

        return jsonify({'message': 'image deleted'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
