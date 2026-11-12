"""Reset the database to the demo data.

Recreates every table from db/schema.sql, then loads the fake data from bank_data.py.
Run it before a test run:  .\\.venv\\Scripts\\python.exe seed.py
"""

import os
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from bank_data import ACCOUNTS, CARDS, CUSTOMERS, DISPUTES, FEE_REVERSALS, TRANSACTIONS

import json

import numpy as np
from pgvector.psycopg import register_vector

INDEX_PATH = Path(__file__).parent / "data" / "help_center_index.json"

load_dotenv()
SCHEMA_PATH = Path(__file__).parent / "db" / "schema.sql"


def seed() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        register_vector(conn)

        with conn.cursor() as cur:
            # 2. Copy the data, parents before children.
            cur.executemany(
                "INSERT INTO customers (id, full_name, date_of_birth, card_last4) VALUES (%s, %s, %s, %s)",
                [
                    (customer_id, c["full_name"], date.fromisoformat(c["date_of_birth"]), c["card_last4"])
                    for customer_id, c in CUSTOMERS.items()
                ],
            )
            cur.executemany(
                "INSERT INTO accounts (id, customer_id, type, balance) VALUES (%s, %s, %s, %s)",
                [
                    (account_id, a["customer_id"], a["type"], a["balance"])
                    for account_id, a in ACCOUNTS.items()
                ],
            )
            cur.executemany(
                "INSERT INTO cards (id, customer_id, last4, type, status, freeze_reason) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (card_id, c["customer_id"], c["last4"], c["type"], c["status"], c.get("freeze_reason"))
                    for card_id, c in CARDS.items()
                ],
            )
            cur.executemany(
                "INSERT INTO transactions (id, account_id, date, description, amount, type, status, fee_type) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (tx_id, t["account_id"], t["date"], t["description"], t["amount"], t["type"], t["status"],
                     t.get("fee_type"))
                    for tx_id, t in TRANSACTIONS.items()
                ],
            )
            cur.executemany(
                "INSERT INTO disputes (id, transaction_id, customer_id, reason, details, status, filed_on) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (dispute_id, d["transaction_id"], d["customer_id"], d["reason"], d["details"], d["status"],
                     d["filed_on"])
                    for dispute_id, d in DISPUTES.items()
                ],
            )
            cur.executemany(
                "INSERT INTO fee_reversals (id, transaction_id, customer_id, amount, reason, reversed_on) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (reversal_id, f["transaction_id"], f["customer_id"], f["amount"], f["reason"], f["reversed_on"])
                    for reversal_id, f in FEE_REVERSALS.items()
                ],
            )

            # Help center chunks, with the embeddings rag.py saved (no Voyage calls needed).
            chunks = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            cur.executemany(
                "INSERT INTO help_center_chunks (id, article, section, source, text, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (c["id"], c["article"], c["section"], c["source"], c["text"], np.array(c["embedding"]))
                    for c in chunks
                ],
            )


            # 3. Move the ID counters past the rows just inserted.
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('transactions', 'id'), (SELECT max(id) FROM transactions))"
            )
            cur.execute(
                "SELECT setval('dispute_number_seq', (SELECT max(split_part(id, '-', 2)::int) FROM disputes))"
            )
            cur.execute(
                "SELECT setval('fee_reversal_number_seq', (SELECT max(split_part(id, '-', 2)::int) FROM fee_reversals))"
            )

    print("Database reset to demo data.")


if __name__ == "__main__":
    seed()