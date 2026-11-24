import json
from pathlib import Path

from evals.checks import check_conversation
from evals.scenario import load_scenarios

run_dir = sorted(Path("evals/runs").iterdir())[-1]     # the latest run
for s in load_scenarios():
    result = json.loads((run_dir / f"{s.id}.json").read_text(encoding="utf-8"))
    for c in check_conversation(s, result):
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"{mark}  {s.id}: {c['check']}  {c['detail'] if not c['passed'] else ''}")