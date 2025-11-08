import json
import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

print("\nLoading environment and data:")
DB_URL = os.getenv('DATABASE_URL')
if DB_URL:
    parts = DB_URL.split('@')
    if len(parts) > 1:
        masked = f"{parts[0].split('://')[0]}://*****@{parts[1]}"
    else:
        masked = DB_URL
    print(f"DATABASE_URL: {masked}")
else:
    print("DATABASE_URL: not set")
if not DB_URL:
    raise RuntimeError('DATABASE_URL environment variable is not set')

def load_workouts():
    try:
        # Load JSON data
        print("\nReading workouts.json...")
        with open("workouts.json", "r") as f:
            workouts = json.load(f)
        print(f"✓ Found {len(workouts)} workouts in JSON file")

        # Connect and insert
        print("\nConnecting to database...")
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Clear existing data
                cur.execute("DELETE FROM public_workouts")
                print("✓ Cleared existing workouts")
                
                # Insert new data
                print("\nInserting workouts...")
                for w in workouts:
                    cur.execute("""
                    INSERT INTO public_workouts (type, name, muscles, equipment, instructions, level)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """, (w["type"], w["name"], w["muscles"], w["equipment"], w["instructions"], w["level"]))
                
                # Verify count
                cur.execute("SELECT COUNT(*) FROM public_workouts")
                count = cur.fetchone()[0]
                print(f"✓ Successfully loaded {count} workouts into database!")
                
    except FileNotFoundError:
        print("✗ Error: workouts.json not found")
        raise
    except json.JSONDecodeError:
        print("✗ Error: Invalid JSON in workouts.json")
        raise
    except psycopg.Error as e:
        print(f"✗ Database error: {str(e)}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
        raise

if __name__ == "__main__":
    load_workouts()