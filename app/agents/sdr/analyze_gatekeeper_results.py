import sys
import json
import re
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.glm_caller import analyze_test_report


def load_test_report(path: Path) -> str:
    """
    Load the test report from the specified path.
    If not found, print instructions and return None.
    """
    try:
        return path.read_text()
    except FileNotFoundError:
        print(f"Error: Test report not found at {path}")
        print("Please run the gatekeeper tests first to generate the report.")
        return None


def load_code_file(path: Path) -> str:
    """
    Load code from the specified path.
    Return empty string if not found.
    """
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def main():
    # 1. Load report
    report_path = Path("/tmp/gatekeeper_test_report.txt")
    report_content = load_test_report(report_path)
    
    if report_content is None:
        return

    # 2. Load agent code
    agent_path = SCRIPT_DIR / "gatekeeper" / "agent.py"
    agent_code = load_code_file(agent_path)

    # 3. Load signature
    signature_path = SCRIPT_DIR / "gatekeeper" / "signature.py"
    signature_code = load_code_file(signature_path)

    print("Sending data to GLM-5 for analysis...")

    # 4. Call analyze_test_report
    response = analyze_test_report(report_content, agent_code, signature_code)

    # 5. Print the full GLM-5 response with section headers
    print("\n" + "=" * 60)
    print("GLM-5 ANALYSIS RESULT")
    print("=" * 60)
    print(response)
    print("=" * 60 + "\n")

    # 6. Look for JSON arrays in the response and save first match
    # Regex: \[[\s\S]+?\] (Non-greedy match for content inside brackets)
    matches = re.findall(r'\[[\s\S]+?\]', response)

    if matches:
        try:
            # Attempt to parse the first match to ensure it's valid JSON
            json_str = matches[0]
            suggested_cases = json.loads(json_str)

            output_path = Path("/tmp/glm_suggested_cases.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(suggested_cases, f, indent=2)
            
            print(f"Successfully saved suggested cases to {output_path}")

            # 7. If --apply flag: load existing cases, append, save
            if "--apply" in sys.argv:
                cases_path = SCRIPT_DIR / "gatekeeper" / "test_gatekeeper_cases.json"
                existing_cases = []

                if cases_path.exists():
                    try:
                        existing_content = cases_path.read_text()
                        existing_cases = json.loads(existing_content)
                        if not isinstance(existing_cases, list):
                            print(f"Warning: Existing file {cases_path} does not contain a list. Overwriting.")
                            existing_cases = []
                    except json.JSONDecodeError:
                        print(f"Warning: Could not decode existing {cases_path}. Overwriting.")
                        existing_cases = []
                
                # Append new cases
                if isinstance(suggested_cases, list):
                    existing_cases.extend(suggested_cases)
                    
                    with open(cases_path, "w", encoding="utf-8") as f:
                        json.dump(existing_cases, f, indent=2)
                    
                    print(f"Applied {len(suggested_cases)} new cases to {cases_path}")
                else:
                    print("Error: Suggested cases are not in a list format. Cannot apply.")

        except json.JSONDecodeError as e:
            print(f"Error: Found a JSON-like pattern but failed to parse: {e}")
        except Exception as e:
            print(f"Error processing JSON output: {e}")
    else:
        print("No JSON array pattern found in the response.")


if __name__ == "__main__":
    main()
