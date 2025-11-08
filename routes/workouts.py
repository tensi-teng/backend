
import psycopg
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_conn
from utils.generate_checklist import generate_checklist

workouts_bp = Blueprint('workouts', __name__)

@workouts_bp.route('/workouts', methods=['POST'])
@jwt_required()
def create_workout():
    """
    Create a new workout
    ---
    tags:
      - Workouts
    security:
      - bearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - name
            properties:
              name:
                type: string
                description: Name of the workout
              description:
                type: string
                description: Description of the workout
              equipment:
                type: array
                items:
                  type: string
                description: List of equipment needed
              geotag_id:
                type: integer
                description: Optional geotag ID to associate with workout
    responses:
      201:
        description: Workout created successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: created
                workout:
                  type: object
                  properties:
                    id:
                      type: integer
                    name:
                      type: string
                    description:
                      type: string
                    equipment:
                      type: array
                      items:
                        type: string
      400:
        description: Invalid input
        content:
          application/json:
            schema:
              type: object
              properties:
                error:
                  type: string
                  example: name required
      401:
        description: Missing or invalid authentication token
    """
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({'error':'name required'}), 400
    description = data.get('description')
    equipment = data.get('equipment', [])
    geotag_id = data.get('geotag_id')
    user_id = get_jwt_identity()
    eq_str = ','.join(equipment) if isinstance(equipment, list) else (equipment or '')
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO workouts (name, description, equipment, user_id, geotag_id) VALUES (%s,%s,%s,%s,%s) RETURNING id', (name, description, eq_str, user_id, geotag_id))
            wid = cur.fetchone()[0]
            # generate checklist items
            items = generate_checklist(equipment)
            for it in items:
                cur.execute('INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)', (it['task'], it['done'], wid))
    return jsonify({'message':'created','workout': {'id': wid, 'name':name, 'description':description, 'equipment': equipment}}), 201

@workouts_bp.route('/workouts', methods=['GET'])
@jwt_required()
def list_workouts():
    """
    List all workouts for the authenticated user
    ---
    tags:
      - Workouts
    security:
      - bearerAuth: []
    responses:
      200:
        description: List of workouts
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  description:
                    type: string
                  equipment:
                    type: array
                    items:
                      type: string
                  checklist:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: integer
                        task:
                          type: string
                        done:
                          type: boolean
                  geotag_id:
                    type: integer
      401:
        description: Missing or invalid authentication token
    """
    user_id = get_jwt_identity()
    with get_conn() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute('SELECT id, name, description, equipment, geotag_id FROM workouts WHERE user_id=%s ORDER BY created_at DESC', (user_id,))
            rows = cur.fetchall()
            out = []
            for r in rows:
                eq = [e for e in (r['equipment'] or '').split(',') if e]
                cur.execute('SELECT id, task, done FROM checklist_items WHERE workout_id=%s', (r['id'],))
                checklist = [{'id':c[0],'task':c[1],'done':c[2]} for c in cur.fetchall()]
                out.append({'id': r['id'], 'name': r['name'], 'description': r['description'], 'equipment': eq, 'checklist': checklist, 'geotag_id': r['geotag_id']})
    return jsonify(out), 200

@workouts_bp.route('/workouts/<int:wid>', methods=['PUT'])
@jwt_required()
def update_workout(wid):
    """
    Update an existing workout
    ---
    tags:
      - Workouts
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: wid
        schema:
          type: integer
        required: true
        description: Workout ID
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
                description: New name for the workout
              description:
                type: string
                description: New description
              equipment:
                type: array
                items:
                  type: string
                description: Updated equipment list
              geotag_id:
                type: integer
                description: Updated geotag ID
    responses:
      200:
        description: Workout updated successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: updated
      404:
        description: Workout not found or not owned by user
      401:
        description: Missing or invalid authentication token
    """
    data = request.get_json() or {}
    user_id = get_jwt_identity()
    name = data.get('name')
    description = data.get('description')
    equipment = data.get('equipment')
    geotag_id = data.get('geotag_id')
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT user_id FROM workouts WHERE id=%s', (wid,))
            row = cur.fetchone()
            if not row or row[0] != user_id:
                return jsonify({'error':'not found or not allowed'}), 404
            if name: cur.execute('UPDATE workouts SET name=%s WHERE id=%s', (name, wid))
            if description is not None: cur.execute('UPDATE workouts SET description=%s WHERE id=%s', (description, wid))
            if equipment is not None:
                eq_str = ','.join(equipment) if isinstance(equipment, list) else equipment
                cur.execute('UPDATE workouts SET equipment=%s WHERE id=%s', (eq_str, wid))
                # regenerate checklist
                cur.execute('DELETE FROM checklist_items WHERE workout_id=%s', (wid,))
                items = generate_checklist(equipment)
                for it in items:
                    cur.execute('INSERT INTO checklist_items (task, done, workout_id) VALUES (%s,%s,%s)', (it['task'], it['done'], wid))
            if geotag_id is not None:
                cur.execute('UPDATE workouts SET geotag_id=%s WHERE id=%s', (geotag_id, wid))
    return jsonify({'message':'updated'}), 200

@workouts_bp.route('/workouts/<int:wid>', methods=['DELETE'])
@jwt_required()
def delete_workout(wid):
    """
    Delete a workout
    ---
    tags:
      - Workouts
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: wid
        schema:
          type: integer
        required: true
        description: Workout ID to delete
    responses:
      200:
        description: Workout deleted successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: deleted
      404:
        description: Workout not found or not owned by user
      401:
        description: Missing or invalid authentication token
    """
    user_id = get_jwt_identity()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT user_id FROM workouts WHERE id=%s', (wid,))
            row = cur.fetchone()
            if not row or row[0] != user_id:
                return jsonify({'error':'not found or not allowed'}), 404
            cur.execute('DELETE FROM workouts WHERE id=%s', (wid,))
    return jsonify({'message':'deleted'}), 200

@workouts_bp.route('/checklist/<int:item_id>', methods=['PATCH'])
@jwt_required()
def toggle_checklist(item_id):
    """
    Toggle a checklist item's done status
    ---
    tags:
      - Workouts
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: item_id
        schema:
          type: integer
        required: true
        description: Checklist item ID to toggle
    responses:
      200:
        description: Item toggled successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: toggled
                done:
                  type: boolean
                  description: New done status
      403:
        description: Not allowed to modify this checklist item
      401:
        description: Missing or invalid authentication token
    """
    user_id = get_jwt_identity()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT ci.done, w.user_id FROM checklist_items ci JOIN workouts w ON ci.workout_id=w.id WHERE ci.id=%s', (item_id,))
            row = cur.fetchone()
            if not row or row[1] != user_id:
                return jsonify({'error':'not allowed'}), 403
            new_done = not row[0]
            cur.execute('UPDATE checklist_items SET done=%s WHERE id=%s', (new_done, item_id))
    return jsonify({'message':'toggled','done': new_done}), 200
