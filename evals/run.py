import json
import sys
from datetime import datetime
from pathlib import Path

from evals.scenario import load_scenarios
from evals.simulator import run_conversation
from seed import seed


def main():
    wanted = sys.argv[1:]          # optional: only these scenario ids
    scenarios = [s for s in load_scenarios() if not wanted or s.id in wanted]

    run_dir = Path("evals/runs") / datetime.now().strftime("%Y-%m-%d_%H%M")
    run_dir.mkdir(parents=True, exist_ok=True)

    for s in scenarios:
        seed()                     # every scenario starts from the same data
        result = run_conversation(s)
        path = run_dir / f"{s.id}.json"
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"{s.id}: {len(result['turns'])} turns, verified={result['verified']}")

    print("Saved to", run_dir)


if __name__ == "__main__":
    main()