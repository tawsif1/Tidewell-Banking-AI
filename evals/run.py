import json
import sys
from datetime import datetime
from pathlib import Path

from evals.checks import check_conversation
from evals.scenario import load_scenarios
from evals.simulator import run_conversation
from seed import seed


def parse_args(args):
    repeats = 1
    if "--repeat" in args:
        i = args.index("--repeat")
        repeats = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    return args, repeats


def main():
    wanted, repeats = parse_args(sys.argv[1:])
    scenarios = [s for s in load_scenarios() if not wanted or s.id in wanted]

    run_dir = Path("evals/runs") / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    for s in scenarios:
        passed_runs = 0
        for k in range(1, repeats + 1):
            seed()
            result = run_conversation(s)
            result["checks"] = check_conversation(s, result)
            failed = [c["check"] for c in result["checks"] if not c["passed"]]
            if not failed:
                passed_runs += 1
            path = run_dir / f"{s.id}_run{k}.json"
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"{s.id} run {k}: {'PASS' if not failed else 'FAIL: ' + '; '.join(failed)}")
        print(f"==> {s.id}: {passed_runs}/{repeats}")

    print("Saved to", run_dir)


if __name__ == "__main__":
    main()