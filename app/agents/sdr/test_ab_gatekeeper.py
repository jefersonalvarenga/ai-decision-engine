import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

# Path setup
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import init_dspy, get_settings, _settings as reset_settings
import app.core.config as cfg
from app.agents.sdr.gatekeeper import gatekeeper_graph


def run_model_scenarios(provider: str, model: str, scenarios: list) -> list:
    """
    Runs the gatekeeper scenarios against a specific model configuration.
    Temporarily sets environment variables, resets config singleton, and runs tests.
    """
    # Save original environment variables
    original_provider = os.environ.get("DSPY_PROVIDER")
    original_model = os.environ.get("DSPY_MODEL")

    results = []

    try:
        # Set new environment variables
        os.environ["DSPY_PROVIDER"] = provider
        os.environ["DSPY_MODEL"] = model

        # Reset settings singleton and re-initialize
        cfg._settings = None
        init_dspy()

        print(f"Running scenarios for {provider}/{model}...")

        for scenario in scenarios:
            name = scenario.get("name", "Unnamed Scenario")
            history = scenario.get("conversation_history", [])
            expected_stage = scenario.get("expected_stage")

            # Calculate attempt_count based on agent turns in history
            attempt_count = len([t for t in history if t.get("role") == "agent"])

            start_time = time.time()

            try:
                input_state = {
                    "clinic_name": scenario.get("clinic_name", "Clínica Teste"),
                    "conversation_history": history,
                    "latest_message": scenario.get("latest_message"),
                    "current_hour": 10,
                    "attempt_count": attempt_count
                }

                output = gatekeeper_graph.invoke(input_state)

                actual_stage = output.get("conversation_stage")
                message = output.get("response_message", "")
                
            except Exception as e:
                actual_stage = "ERROR"
                message = str(e)

            end_time = time.time()
            processing_ms = (end_time - start_time) * 1000

            correct = (actual_stage == expected_stage)

            results.append({
                "name": name,
                "expected_stage": expected_stage,
                "actual_stage": actual_stage,
                "correct": correct,
                "message": message,
                "processing_ms": processing_ms
            })

    finally:
        # Restore original environment variables
        if original_provider is not None:
            os.environ["DSPY_PROVIDER"] = original_provider
        else:
            os.environ.pop("DSPY_PROVIDER", None)

        if original_model is not None:
            os.environ["DSPY_MODEL"] = original_model
        else:
            os.environ.pop("DSPY_MODEL", None)
        
        # Reset settings to original state for subsequent runs
        cfg._settings = None
        # Note: We don't call init_dspy() here again to avoid overhead, 
        # main() will handle re-init for the next model or exit.

    return results


def print_ab_report(results_a: list, results_b: list, label_a: str, label_b: str):
    """
    Prints a comparison report between two sets of model results.
    """
    print(f"\n{'='*100}")
    print(f"A/B Test Report: {label_a} vs {label_b}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}\n")

    # Table Header
    header = f"{'Scenario':<32} | {'Expected':<15} | {label_a + ' Result':<20} | {label_b + ' Result':<20}"
    print(header)
    print("-" * len(header))

    total_a = len(results_a)
    correct_a = 0
    time_a = 0.0
    
    total_b = len(results_b)
    correct_b = 0
    time_b = 0.0

    for r_a, r_b in zip(results_a, results_b):
        # Truncate name to 30 chars
        name = r_a['name'][:30]
        expected = r_a['expected_stage']
        
        # Format results with icons
        icon_a = "✅" if r_a['correct'] else "⚠️"
        icon_b = "✅" if r_b['correct'] else "⚠️"
        
        res_a_str = f"{icon_a} {r_a['actual_stage']}"
        res_b_str = f"{icon_b} {r_b['actual_stage']}"

        print(f"{name:<32} | {expected:<15} | {res_a_str:<20} | {res_b_str:<20}")

        # Accumulate stats
        if r_a['correct']:
            correct_a += 1
        time_a += r_a['processing_ms']

        if r_b['correct']:
            correct_b += 1
        time_b += r_b['processing_ms']

    print("-" * len(header))

    # Summary
    acc_a = (correct_a / total_a * 100) if total_a > 0 else 0
    avg_time_a = (time_a / total_a) if total_a > 0 else 0

    acc_b = (correct_b / total_b * 100) if total_b > 0 else 0
    avg_time_b = (time_b / total_b) if total_b > 0 else 0

    print(f"\nSummary Statistics:")
    print(f"Model A ({label_a}):")
    print(f"  - Accuracy: {acc_a:.1f}% ({correct_a}/{total_a})")
    print(f"  - Avg Processing Time: {avg_time_a:.2f}ms")
    
    print(f"\nModel B ({label_b}):")
    print(f"  - Accuracy: {acc_b:.1f}% ({correct_b}/{total_b})")
    print(f"  - Avg Processing Time: {avg_time_b:.2f}ms")
    print(f"{'='*100}\n")


def main():
    # Load scenarios
    cases_path = SCRIPT_DIR / "test_gatekeeper_cases.json"
    
    if not cases_path.exists():
        print(f"Error: Test cases file not found at {cases_path}")
        return

    with open(cases_path, "r") as f:
        scenarios = json.load(f)

    print(f"Loaded {len(scenarios)} test scenarios.")

    # Run Model A: GPT-4o-mini
    results_a = run_model_scenarios(
        provider="openai", 
        model="gpt-4o-mini", 
        scenarios=scenarios
    )

    # Run Model B: GLM-5
    results_b = run_model_scenarios(
        provider="glm", 
        model="glm-5", 
        scenarios=scenarios
    )

    # Print Report
    print_ab_report(results_a, results_b, "GPT-4o-mini", "GLM-5")


if __name__ == "__main__":
    main()
