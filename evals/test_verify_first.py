from evals.checks import check_verify_first

OK = "Identity verified successfully."
NO_MATCH = "The details provided don't match our records."


def ev(name, result="..."):
    return {"name": name, "input": {}, "result": result, "is_error": False}


def convo(*turns):
    return {"turns": [{"customer": "...", "agent": "...", "tool_events": list(t)} for t in turns]}


tests = [
    ("freeze before verify  -> False", convo([ev("freeze_card"), ev("verify_identity", OK)])),
    ("verify before freeze  -> True ", convo([ev("verify_identity", OK), ev("freeze_card")])),
    ("help center only      -> True ", convo([ev("search_help_center")])),
    ("verify t1, account t2 -> True ", convo([ev("verify_identity", OK)], [ev("get_accounts")])),
    ("failed verify, account-> False", convo([ev("verify_identity", NO_MATCH), ev("get_accounts")])),
]

for label, result in tests:
    r = check_verify_first(result)
    r = r[0] if isinstance(r, list) else r      # works whichever option you picked
    print(f"{label}   got {r['passed']}")