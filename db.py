# db.py
import os
import psycopg
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

# Get the database URL from environment
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

def get_conn():
    return psycopg.connect(DB_URL, autocommit=True)
