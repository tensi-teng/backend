import psycopg
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist

saved_workouts_bp = Blueprint('saved_workouts', __name__)

@saved_workouts_bp.route('/public/save/<int:workout_id>', methods=['POST'])
@jwt_required()
def save_public_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get the public workout
                cur.execute("""
                    SELECT name, description, equipment, type, muscles, level
                    FROM public_workouts WHERE id = %s
                """, (workout_id,))
                workout = cur.fetchone()
                if not workout:
                    return jsonify({"error": "Public workout not found"}), 404

                # Check if already saved
                cur.execute("""
                    SELECT id FROM saved_workouts 
                    WHERE user_id = %s AND public_workout_id = %s
                """, (user_id, workout_id))
                if cur.fetchone():
                    return jsonify({"error": "Workout already saved"}), 409

                # Save the workout
                custom_name = data.get('name', workout[0])
                cur.execute("""
                    INSERT INTO saved_workouts 
                    (user_id, public_workout_id, name, description, equipment, type, muscles, level)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (user_id, workout_id, custom_name, workout[1], workout[2],
                      workout[3], workout[4], workout[5]))
                saved_id = cur.fetchone()[0]

                # Generate checklist items if equipment exists
                equipment_list = [e.strip() for e in (workout[2] or '').split(',')]
                if equipment_list:
                    checklist = generate_checklist(equipment_list)
                    for item in checklist:
                        cur.execute("""
                            INSERT INTO checklist_items (task, done, workout_id)
                            VALUES (%s, %s, %s)
                        """, (item['task'], False, saved_id))

        return jsonify({"message": "saved", "id": saved_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@saved_workouts_bp.route('/saved', methods=['GET'])
@jwt_required()
def list_saved_workouts():
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute("""
                    SELECT id, name, description, equipment, type, muscles, level
                    FROM saved_workouts
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                workouts = cur.fetchall()

                for w in workouts:
                    cur.execute("""
                        SELECT id, task, done
                        FROM checklist_items
                        WHERE workout_id = %s
                    """, (w['id'],))
                    w['checklist'] = [
                        {'id': c[0], 'task': c[1], 'done': c[2]}
                        for c in cur.fetchall()
                    ]

        return jsonify(workouts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@saved_workouts_bp.route('/saved/<int:workout_id>', methods=['PUT'])
@jwt_required()
def update_saved_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership
                cur.execute("""
                    SELECT id FROM saved_workouts
                    WHERE id = %s AND user_id = %s
                """, (workout_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Workout not found"}), 404

                # Update allowed fields
                if 'name' in data:
                    cur.execute("""
                        UPDATE saved_workouts SET name = %s
                        WHERE id = %s
                    """, (data['name'], workout_id))
                if 'description' in data:
                    cur.execute("""
                        UPDATE saved_workouts SET description = %s
                        WHERE id = %s
                    """, (data['description'], workout_id))

        return jsonify({"message": "updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@saved_workouts_bp.route('/saved/<int:workout_id>', methods=['DELETE'])
@jwt_required()
def delete_saved_workout(workout_id):
    try:
        user_id = int(get_jwt_identity())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM saved_workouts
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                """, (workout_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Workout not found"}), 404

        return jsonify({"message": "deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
