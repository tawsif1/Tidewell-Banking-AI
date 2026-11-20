"""Create the demo data on a fresh database, and do nothing if it already exists.

Runs before every deploy on Render. seed.py drops and recreates every table, so
calling it on each deploy would wipe the sessions. This only seeds when the
customers table is missing.
"""

import os

import psycopg
from dotenv import load_dotenv

from seed import seed

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    exists = conn.execute("SELECT to_regclass('public.customers')").fetchone()[0] is not None

if exists:
    print("Database already has the demo data; leaving it alone.")
else:
    seed()
