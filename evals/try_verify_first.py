import json
import sys
from pathlib import Path

from evals.checks import check_verify_first

run_dir = Path(sys.argv[1])
for path in sorted(run_dir.glob("*_run*.json")):
    result = json.loads(path.read_text(encoding="utf-8"))
    if "turns" not in result:          # an ERROR run has no conversation
        continue
    r = check_verify_first(result)
    r = r[0] if isinstance(r, list) else r
    print(f"{'PASS' if r['passed'] else 'FAIL'}  {path.stem}  {r['detail']}")