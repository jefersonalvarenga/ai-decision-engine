"""
Parse test output from test_sdr_agents.py and emit GitHub Actions outputs.

Usage:
    python scripts/parse_test_results.py test_output.txt >> $GITHUB_OUTPUT
"""

import sys
import re

def parse(log_path: str):
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match "GATEKEEPER: 38/41 (92%)" or "CLOSER: 49/49 (100%)"
    summary_pattern = re.search(
        r"(GATEKEEPER|CLOSER):\s+(\d+)/(\d+)\s+\((\d+)%\)", content
    )

    passed = failed = total = 0
    pass_rate = 0

    if summary_pattern:
        passed = int(summary_pattern.group(2))
        total = int(summary_pattern.group(3))
        pass_rate = int(summary_pattern.group(4))
        failed = total - passed

    # Extract individual failure names
    failures = re.findall(r"•\s+(GATEKEEPER|CLOSER)\s+\|\s+(.+?)(?:\n|$)", content)
    failed_scenarios = "; ".join(f"{name}" for _, name in failures[:10])  # max 10

    print(f"passed_count={passed}")
    print(f"failed_count={failed}")
    print(f"total_count={total}")
    print(f"pass_rate={pass_rate}")
    print(f"failed_scenarios={failed_scenarios}")

    return pass_rate


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parse_test_results.py <log_file>", file=sys.stderr)
        sys.exit(1)

    rate = parse(sys.argv[1])
    sys.exit(0)
