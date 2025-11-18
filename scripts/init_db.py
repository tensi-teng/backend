import os
import json
import psycopg
from dotenv import load_dotenv

# ----------------------
# ENV SETUP
# ----------------------
load_dotenv()
DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise RuntimeError('DATABASE_URL environment variable is not set')

# Mask database URL for display
parts = DB_URL.split('@')
masked = f"{parts[0].split('://')[0]}://*****@{parts[1]}" if len(parts) > 1 else DB_URL
print(f"\nDATABASE_URL: {masked}")
print("\n=== INITIALIZING DATABASE ===")

# LOAD SCHEMA
try:
    with open('db_init.sql', 'r') as file:
        init_sql = file.read()
    print("✓ Loaded db_init.sql successfully.")
except FileNotFoundError:
    print("✗ db_init.sql not found. Please make sure it’s in the same directory.")
    raise

# CONNECT & INITIALIZE
try:
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("\n→ Connecting to database...")
            print("✓ Connected.")
            print("→ Creating tables...")
            cur.execute(init_sql)
            print("✓ Tables created successfully!")

            # LOAD PUBLIC WORKOUTS
            print("\n=== LOADING PUBLIC WORKOUTS ===")
            try:
                with open('workouts.json', 'r') as f:
                    workouts = json.load(f)
                print(f"✓ Found {len(workouts)} workouts in JSON file.")
            except FileNotFoundError:
                print("✗ workouts.json not found — skipping public workouts load.")
                workouts = []
            except json.JSONDecodeError:
                print("✗ Invalid JSON format in workouts.json — skipping load.")
                workouts = []

            if workouts:
                # Clear existing data
                cur.execute("DELETE FROM public_workouts;")
                print("✓ Cleared existing workouts from public_workouts table.")

                inserted = 0

                for w in workouts:
                    # ----------------------------------------
                    # SANITIZE EQUIPMENT → TEXT (comma string)
                    # ----------------------------------------
                    equipments = w.get('equipments') or []
                    if isinstance(equipments, list):
                        equipment_str = ",".join(equipments)
                    else:
                        equipment_str = str(equipments)

                    # ----------------------------------------
                    # SANITIZE MUSCLES → TEXT[]
                    # ----------------------------------------
                    muscles = w.get('muscles') or []
                    if not isinstance(muscles, list):
                        muscles = [muscles]

                    # ----------------------------------------
                    # SANITIZE INSTRUCTIONS → TEXT
                    # If array → join with new lines
                    # ----------------------------------------
                    instr = w.get('instructions') or ""
                    if isinstance(instr, list):
                        instr = "\n".join(instr)

                    # ----------------------------------------
                    # SANITIZE DESCRIPTION → TEXT
                    # If array → join with new lines
                    # ----------------------------------------
                    desc = w.get('description') or ""
                    if isinstance(desc, list):
                        desc = "\n".join(desc)

                    # INSERT
                    try:
                        cur.execute("""
                            INSERT INTO public_workouts
                            (type, name, muscles, equipment, description, instructions, level)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            w.get('type'),
                            w.get('name'),
                            muscles,
                            equipment_str,
                            desc,
                            instr,
                            w.get('level')
                        ))
                        inserted += 1

                    except Exception as err:
                        print(f"✗ Failed inserting workout: {w.get('name')}")
                        print("  Error:", err)
                        continue

                print(f"✓ Successfully inserted {inserted} workouts into public_workouts!")

    print("\n🎉 DATABASE INITIALIZED AND WORKOUTS LOADED SUCCESSFULLY!")

except psycopg.Error as e:
    print(f"✗ Database error: {e}")
    raise
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    raise
