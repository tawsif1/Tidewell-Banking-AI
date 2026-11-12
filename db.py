"""Database connections for the app. Everything that talks to Postgres imports `pool` from here."""

import os

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

load_dotenv()

pool = ConnectionPool(
    os.environ["DATABASE_URL"],
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
    configure=register_vector,               # teach each new connection the vector type
    check=ConnectionPool.check_connection,
    timeout=5,
    open=True,
)