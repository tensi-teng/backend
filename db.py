import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    # Fail fast on startup rather than giving vague 500s later
    raise RuntimeError("DATABASE_URL environment variable is not set")

def get_conn():
    # Use the actual DB_URL value, not the literal string.
    # autocommit=True so that simple INSERT/UPDATE/DELETE statements
    # do not require explicit conn.commit() in the route handlers.
    return psycopg.connect(DB_URL, autocommit=True)
