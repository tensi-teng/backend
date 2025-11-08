
from functools import wraps
from flask import Blueprint, jsonify, request, current_app
import psycopg
import os
from dotenv import load_dotenv
load_dotenv()

public_bp = Blueprint('public_api', __name__)
API_KEY = os.getenv('API_KEY')
DB_URL = os.getenv('DATABASE_URL')

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-KEY')
        if api_key != API_KEY:
            return jsonify({'error':'you need a valid api key'}), 403
        return f(*args, **kwargs)
    return decorated_function

@public_bp.route('/workouts', methods=['GET'])
@require_api_key
def get_workouts():
    """
    Get all workouts or filter by type, muscle, level
    ---
    tags:
      - Public API
    security:
      - ApiKeyAuth: []
    parameters:
      - in: query
        name: type
        schema:
          type: string
        description: Filter workouts by type (e.g., cardio, strength)
      - in: query
        name: muscle
        schema:
          type: string
        description: Filter by target muscle group
      - in: query
        name: level
        schema:
          type: string
        description: Filter by difficulty level
    responses:
      200:
        description: List of workouts
        content:
          application/json:
            schema:
              type: object
              properties:
                count:
                  type: integer
                  description: Number of workouts returned
                workouts:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: integer
                      name:
                        type: string
                      equipment:
                        type: string
                      description:
                        type: string
      403:
        description: Invalid or missing API key
      500:
        description: Database error
        content:
          application/json:
            schema:
              type: object
              properties:
                error:
                  type: string
                  example: database error
                detail:
                  type: string
    """
    type_filter = request.args.get('type')
    muscle_filter = request.args.get('muscle')
    level_filter = request.args.get('level')

    try:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                query = "SELECT id, name, equipment, description FROM workouts WHERE 1=1"
                params = []
                if type_filter:
                    query += " AND LOWER(name) LIKE LOWER(%s)"
                    params.append(f"%{type_filter}%")
                if muscle_filter:
                    query += " AND LOWER(description) LIKE LOWER(%s)"
                    params.append(f"%{muscle_filter}%")
                if level_filter:
                    query += " AND LOWER(description) LIKE LOWER(%s)"
                    params.append(f"%{level_filter}%")
                cur.execute(query, params)
                rows = cur.fetchall()
                workouts = [dict(row) for row in rows]
    except psycopg.Error as e:
        current_app.logger.exception('Database error while fetching workouts')
        return jsonify({'error':'database error','detail': str(e)}), 500
    return jsonify({'count': len(workouts), 'workouts': workouts}), 200

@public_bp.route('/protected', methods=['GET'])
@require_api_key
def protected_resource():
    """
    Test protected API endpoint
    ---
    tags:
      - Public API
    security:
      - ApiKeyAuth: []
    responses:
      200:
        description: Successfully accessed protected endpoint
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: this is a protected API!
      403:
        description: Invalid or missing API key
    """
    return jsonify({'message':'this is a protected API!'}), 200
