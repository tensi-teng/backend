import psycopg
import json
import os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

with psycopg.connect(DB_URL, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("""
        DROP TABLE IF EXISTS public_workouts;
        CREATE TABLE public_workouts (
            id SERIAL PRIMARY KEY,
            type VARCHAR(50),
            name VARCHAR(100),
            muscles TEXT[],
            equipment TEXT,
            instructions TEXT,
            level VARCHAR(20)
        );
        """)
        print('public_workouts table created.')

        # Load JSON data
        with open("workouts.json", "r") as f:
            workouts = json.load(f)

        # Insert data
        for w in workouts:
            cur.execute("""
            INSERT INTO public_workouts (type, name, muscles, equipment, instructions, level)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (w.get("type"), w.get("name"), w.get("muscles"), w.get("equipment"), w.get("instructions"), w.get("level")))

print("Workouts loaded into public_workouts table!")