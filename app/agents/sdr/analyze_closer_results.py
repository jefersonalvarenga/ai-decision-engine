import sys
import json
import re
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.glm_caller import call_glm


def load_test_report(path: Path) -> str:
    """
    Load the test report from the specified path.
    If not found, print instructions and return None.
    """
    try:
        return path.read_text()
    except FileNotFoundError:
        print(f"Error: Test report not found at {path}")
        print("Please run the closer tests first to generate the report.")
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
    report_path = Path("/tmp/closer_test_report.txt")
    report_content = load_test_report(report_path)

    if report_content is None:
        return

    # 2. Load agent code
    agent_path = SCRIPT_DIR / "closer" / "agent.py"
    agent_code = load_code_file(agent_path)

    # 3. Load signature
    signature_path = SCRIPT_DIR / "closer" / "signature.py"
    signature_code = load_code_file(signature_path)

    print("Sending data to GLM-5 for analysis...")

    # 4. Build Closer-specific prompt
    prompt = f"""Você é um especialista em agentes de IA para vendas B2B via WhatsApp em PT-BR.

Analise este relatório de testes do Closer SDR Agent (agente que conversa com gestores de clínicas
para agendar uma call de demonstração de 20 minutos) e sugira melhorias.

=== RELATÓRIO DE TESTES ===
{report_content}

=== CÓDIGO DO AGENTE ===
{agent_code}

=== SIGNATURE/PROMPT DO AGENTE ===
{signature_code}

Por favor forneça:

1. **ANÁLISE DAS FALHAS**: Para cada cenário que falhou, explique a causa raiz.

2. **MELHORIAS NO PROMPT**: Sugestões específicas e concretas para a signature do agente
   que corrijam as falhas identificadas.

3. **10 NOVOS CENÁRIOS DE TESTE** em JSON válido:
   Cada cenário no formato:
   {{"name": "...", "manager_name": "...", "manager_phone": "...", "clinic_name": "...", "clinic_specialty": "...", "conversation_history": [...], "latest_message": "...", "expected_stage": "..."}}

   Cubra estes gaps: confirmação de horário, reagendamento, slots vazios,
   rejeição suave vs dura, objeção de preço, gestor que adia várias vezes,
   gestor que pede para ligar, gestor desconfiado, conversa longa sem evolução.

Seja específico e prático."""

    # 5. Call GLM directly
    response = call_glm(prompt, temperature=0.5, max_tokens=4000)

    # 6. Print the full GLM-5 response with section headers
    print("\n" + "=" * 60)
    print("GLM-5 ANALYSIS RESULT")
    print("=" * 60)
    print(response)
    print("=" * 60 + "\n")

    # 7. Look for JSON arrays in the response and save first match
    matches = re.findall(r'\[[\s\S]+?\]', response)

    if matches:
        try:
            json_str = matches[0]
            suggested_cases = json.loads(json_str)

            output_path = Path("/tmp/glm_suggested_closer_cases.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(suggested_cases, f, indent=2)

            print(f"Successfully saved suggested cases to {output_path}")

            # 8. If --apply flag: load existing cases, append, save
            if "--apply" in sys.argv:
                cases_path = SCRIPT_DIR / "test_closer_cases.json"
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
