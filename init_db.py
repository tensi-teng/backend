import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

print("\nInitializing database...")
DB_URL = os.getenv('DATABASE_URL')

# Read the SQL file
with open('db_init.sql', 'r') as file:
    init_sql = file.read()

try:
    # Connect and execute the SQL
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("Connected to database")
            print("Creating tables...")
            cur.execute(init_sql)
            print("✓ Database tables created successfully!")
except Exception as e:
    print(f"✗ Error initializing database: {str(e)}")
    raise