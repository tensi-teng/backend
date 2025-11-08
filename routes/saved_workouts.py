from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import psycopg
from db import get_conn
from utils.generate_checklist import generate_checklist

saved_workouts_bp = Blueprint('saved_workouts', __name__)

@saved_workouts_bp.route('/public/save/<int:workout_id>', methods=['POST'])
@jwt_required()
def save_public_workout(workout_id):
    """
    Save a public workout to user's collection
    ---
    tags:
      - Saved Workouts
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: workout_id
        schema:
          type: integer
        required: true
        description: ID of the public workout to save
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
                description: Optional custom name for the saved workout
    responses:
      201:
        description: Workout saved successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: saved
                id:
                  type: integer
                  description: ID of the saved workout
      404:
        description: Public workout not found
      409:
        description: Workout already saved by user
    """
    user_id = get_jwt_identity()
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
                (user_id, public_workout_id, name, description, equipment, 
                 type, muscles, level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (user_id, workout_id, custom_name, workout[1], workout[2],
                  workout[3], workout[4], workout[5]))
            saved_id = cur.fetchone()[0]
            
            # Generate and save checklist items if there's equipment
            if workout[2]:  # if equipment exists
                equipment_list = [e.strip() for e in workout[2].split(',')]
                checklist = generate_checklist(equipment_list)
                for item in checklist:
                    cur.execute("""
                        INSERT INTO checklist_items (task, done, workout_id)
                        VALUES (%s, false, %s)
                    """, (item['task'], saved_id))
                    
    return jsonify({
        "message": "saved",
        "id": saved_id
    }), 201

@saved_workouts_bp.route('/saved', methods=['GET'])
@jwt_required()
def list_saved_workouts():
    """
    List all saved workouts for the user
    ---
    tags:
      - Saved Workouts
    security:
      - bearerAuth: []
    responses:
      200:
        description: List of saved workouts
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
                    type: string
                  type:
                    type: string
                  muscles:
                    type: array
                    items:
                      type: string
                  level:
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
    """
    user_id = get_jwt_identity()
    
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
                w['checklist'] = cur.fetchall()
                
    return jsonify(workouts), 200

@saved_workouts_bp.route('/saved/<int:workout_id>', methods=['PUT'])
@jwt_required()
def update_saved_workout(workout_id):
    """
    Update a saved workout
    ---
    tags:
      - Saved Workouts
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: workout_id
        schema:
          type: integer
        required: true
        description: ID of the saved workout
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
    """
    user_id = get_jwt_identity()
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

@saved_workouts_bp.route('/saved/<int:workout_id>', methods=['DELETE'])
@jwt_required()
def delete_saved_workout(workout_id):
    """
    Delete a saved workout
    ---
    tags:
      - Saved Workouts
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: workout_id
        schema:
          type: integer
        required: true
        description: ID of the saved workout to delete
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
    """
    user_id = get_jwt_identity()
    
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