import os
import json
from dotenv import load_dotenv
import psycopg

load_dotenv()

DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise RuntimeError('DATABASE_URL environment variable is not set')

with psycopg.connect(DB_URL, autocommit=True) as conn:
    with conn.cursor() as cur:
        with open('db_init.sql', 'r') as f:
            cur.execute(f.read())
        print('Schema created.')

        # Load workouts JSON
        with open('workouts.json', 'r') as f:
            data = json.load(f)

        for w in data:
            equipment_list = w.get('equipment') or []
            if not isinstance(equipment_list, list):
                equipment_list = [equipment_list]
            equipment_str = ','.join(equipment_list)

            cur.execute(
                """
                INSERT INTO workouts (name, description, equipment, user_id)
                VALUES (%s, %s, %s, NULL)
                """,
                (w.get('name'), w.get('instructions'), equipment_str)
            )

        print(f"Inserted {len(data)} sample workouts.")
