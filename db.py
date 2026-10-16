"""Database connections for the app. Everything that talks to Postgres imports `pool` from here."""

import os

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

pool = ConnectionPool(
    os.environ["DATABASE_URL"],
    min_size=1,                              # keep at least one connection open
    max_size=5,                              # never open more than five
    kwargs={"row_factory": dict_row},        # rows come back as dicts: row["balance"]
    check=ConnectionPool.check_connection,   # test a connection before lending it out
    timeout=5,                               # give up after 5 seconds if the database is down
    open=True,
)