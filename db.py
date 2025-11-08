
import os
import psycopg
from dotenv import load_dotenv
load_dotenv()

DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise RuntimeError('DATABASE_URL environment variable is not set')

def get_conn():
    return psycopg.connect("DB_URL", autocommit=True)
