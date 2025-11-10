import os
import json
from dotenv import load_dotenv
import psycopg

# Load environment variables
load_dotenv()
DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise RuntimeError('DATABASE_URL environment variable is not set')

parts = DB_URL.split('@')
masked = f"{parts[0].split('://')[0]}://*****@{parts[1]}" if len(parts) > 1 else DB_URL
print(f"DATABASE_URL: {masked}")

def load_workouts():
    try:
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor() as cur:

                # Step 1: Create table if it doesn't exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS public_workouts (
                        id SERIAL PRIMARY KEY,
                        type VARCHAR(100),
                        name VARCHAR(255),
                        muscles VARCHAR(255),
                        equipment TEXT,
                        instructions TEXT,
                        level VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                print("✓ Table 'public_workouts' is ready.")

                # Step 2: Load workouts JSON
                try:
                    with open('workouts.json', 'r') as f:
                        workouts = json.load(f)
                    print(f"✓ Found {len(workouts)} workouts in JSON file")
                except FileNotFoundError:
                    print("✗ workouts.json not found")
                    return
                except json.JSONDecodeError:
                    print("✗ Invalid JSON in workouts.json")
                    return

                # Step 3: Clear existing data for idempotency
                cur.execute("DELETE FROM public_workouts")
                print("✓ Cleared existing workouts")

                # Step 4: Insert data
                for w in workouts:
                    # Convert equipment list to comma-separated string
                    equipment_list = w.get('equipment') or []
                    if not isinstance(equipment_list, list):
                        equipment_list = [equipment_list]
                    equipment_str = ','.join(equipment_list)

                    cur.execute("""
                        INSERT INTO public_workouts
                        (type, name, muscles, equipment, instructions, level)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        w.get('type'),
                        w.get('name'),
                        w.get('muscles'),
                        equipment_str,
                        w.get('instructions'),
                        w.get('level')
                    ))
                print(f"✓ Successfully inserted {len(workouts)} workouts!")

    except psycopg.Error as e:
        print(f"✗ Database error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

if __name__ == "__main__":
    load_workouts()
