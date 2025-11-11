from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
import psycopg
import os

public_bp = Blueprint('public_api', __name__)
DB_URL = os.getenv('DATABASE_URL')

@public_bp.route('/workouts', methods=['GET'])
def get_workouts():
    # Optional JWT handling
    user_id = None
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except Exception:
        user_id = None 

    # Filters from query params
    type_filter = request.args.get('type')
    muscle_filter = request.args.get('muscle')
    level_filter = request.args.get('level')

    try:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                query = "SELECT id, name, equipment, type, muscles, level, instructions FROM public_workouts WHERE 1=1"
                params = []
                if type_filter:
                    query += " AND LOWER(type) LIKE LOWER(%s)"
                    params.append(f"%{type_filter}%")
                if muscle_filter:
                    query += " AND LOWER(muscles) LIKE LOWER(%s)"
                    params.append(f"%{muscle_filter}%")
                if level_filter:
                    query += " AND LOWER(level) LIKE LOWER(%s)"
                    params.append(f"%{level_filter}%")
                cur.execute(query, params)
                rows = cur.fetchall()
                workouts = [dict(row) for row in rows]
    except psycopg.Error as e:
        current_app.logger.exception('Database error while fetching workouts')
        return jsonify({'error':'database error','detail': str(e)}), 500

    return jsonify({
        'user_id': user_id, 
        'count': len(workouts),
        'workouts': workouts
    }), 200
