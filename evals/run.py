import json
import sys
from datetime import datetime
from pathlib import Path
from evals.checks import check_conversation, check_database, check_verify_first
from evals.scenario import load_scenarios
from evals.simulator import run_conversation
from seed import seed
import anthropic


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

    scorecard = []

    for s in scenarios:
        passed_runs = errors = 0
        for k in range(1, repeats + 1):
            seed()
            path = run_dir / f"{s.id}_run{k}.json"
            try:
                result = run_conversation(s)
            except anthropic.APIError as e:
                if "credit balance" in str(e):
                    raise SystemExit("Out of API credits: stopping the run.")
                errors += 1
                path.write_text(json.dumps({"scenario": s.id, "error": str(e)}, indent=2), encoding="utf-8")
                print(f"{s.id} run {k}: ERROR: {type(e).__name__}")
                continue

            result["checks"] = check_conversation(s, result) + check_database(s) + check_verify_first(result)
            failed = [c["check"] for c in result["checks"] if not c["passed"]]
            if not failed:
                passed_runs += 1
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"{s.id} run {k}: {'PASS' if not failed else 'FAIL: ' + '; '.join(failed)}")

        completed = repeats - errors
        summary = f"==> {s.id}: {passed_runs}/{completed} passed"
        print(summary + (f", {errors} error(s)" if errors else ""))
        scorecard.append({"scenario": s.id, "passed": passed_runs, "completed": completed, "errors": errors})

    total_passed = sum(r["passed"] for r in scorecard)
    total_completed = sum(r["completed"] for r in scorecard)
    print(f"\nTOTAL: {total_passed}/{total_completed} runs passed")
    (run_dir / "scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    print("Saved to", run_dir)
    


if __name__ == "__main__":
    main()