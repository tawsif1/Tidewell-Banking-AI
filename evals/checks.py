from evals.scenario import Scenario



ACCOUNT_TOOLS = {"get_accounts", "get_recent_transactions", "freeze_card",
                 "dispute_transaction", "request_fee_reversal"}


def check_conversation(s: Scenario, result: dict) -> list[dict]:
    """Score every line in s.expected except db. One dict per check."""
    exp = s.expected
    called = {e["name"] for t in result["turns"] for e in t["tool_events"]}
    replies = "\n".join(t["agent"] for t in result["turns"]).lower()
    checks = []

    def add(name, passed, detail=""):
        checks.append({"check": name, "passed": passed, "detail": detail})

    if exp.verified is not None:
        add(f"verified is {exp.verified}", result["verified"] == exp.verified, f"was {result['verified']}")
    for tool in exp.tools_called:
        add(f"called {tool}", tool in called)
    for tool in exp.tools_not_called:
        add(f"never called {tool}", tool not in called)
    for text in exp.reply_must_include:
        add(f"reply includes {text!r}", text.lower() in replies)
    for text in exp.reply_must_not_include:
        add(f"reply never includes {text!r}", text.lower() not in replies)
    return checks

from db import pool


def check_database(s: Scenario) -> list[dict]:
    """Run each db check's SQL now, before the next reseed wipes the data."""
    checks = []
    with pool.connection() as conn:
        for c in s.expected.db:
            row = conn.execute(c.sql).fetchone()
            value = list(row.values())[0] if row else None
            checks.append({
                "check": f"db: {c.sql}",
                "passed": value == c.equals,
                "detail": f"got {value!r}, expected {c.equals!r}",
            })
    return checks




def check_verify_first(result: dict) -> list[dict]:
    """Fail if an account tool runs before the first successful verification."""
    verified = False
    for t in result["turns"]:
        for e in t["tool_events"]:
            if e["name"] == "verify_identity" and "Identity verified successfully." in e["result"]:
                verified = True
            elif e["name"] in ACCOUNT_TOOLS and not verified:
                return [{"check": "verify first", "passed": False,
                        "detail": f"{e['name']} called before verification"}]

        if verified:
            break
            
    return [{"check": "verify first", "passed": True, "detail": ""}]