"""Run a customer-escalation scenario using Claude Code and a selected prompt."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="Scenario key from support_scenarios.json")
    parser.add_argument(
        "--policy", choices=["baseline", "explicit"], default="explicit",
        help="Which system prompt to use"
    )
    args = parser.parse_args()

    scenario_path = HERE / "support_scenarios.json"
    policy_path = HERE / (
        "escalation_policy_baseline.txt" if args.policy == "baseline"
        else "escalation_policy.txt"
    )

    try:
        scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
        scenario = scenarios[args.scenario]
    except FileNotFoundError as exc:
        sys.exit(f"Required lab file not found: {exc.filename}")
    except KeyError:
        sys.exit(
            "Unknown scenario. Choose one of: " + ", ".join(scenarios.keys())
        )
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON in {scenario_path}: {exc}")

    try:
        system_prompt = policy_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(f"Policy prompt file not found: {policy_path.name}")

    user_prompt = (
        f"Scenario: {args.scenario}\n"
        f"Case context:\n{scenario['case_context']}\n\n"
        f"Customer message:\n{scenario['customer_message']}\n\n"
        "Respond directly to the customer. Do not reveal internal reasoning. "
        "Make the appropriate escalation or clarification decision, and do not claim "
        "that an action or handoff happened unless the case context confirms it."
    )

    print(f"SCENARIO: {args.scenario}")
    print(f"POLICY: {args.policy}")
    print(f"CUSTOMER: {scenario['customer_message']}\n")

    try:
        result = subprocess.run(
            ["claude", "-p", user_prompt, "--system-prompt", system_prompt],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except FileNotFoundError:
        sys.exit("The 'claude' command was not found. Check that Claude Code is installed and on PATH.")
    except subprocess.TimeoutExpired:
        sys.exit("Claude Code did not finish within 300 seconds. You can rerun the scenario.")

    if result.returncode != 0:
        sys.stderr.write(result.stderr or "Claude Code returned a non-zero exit status.\n")
        sys.exit(result.returncode)

    print("ANSWER:")
    print(result.stdout.strip())
    print("\nEXPECTED DECISION FOR REVIEW:")
    print(scenario["expected_decision"])


if __name__ == "__main__":
    main()
