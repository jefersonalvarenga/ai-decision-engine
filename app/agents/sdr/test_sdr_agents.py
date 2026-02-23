"""
Testes locais para os agentes SDR (Gatekeeper e Closer)

Execute com:
    python -m app.agents.sdr.test_sdr_agents

Ou para testar cenários específicos:
    python -m app.agents.sdr.test_sdr_agents --gatekeeper
    python -m app.agents.sdr.test_sdr_agents --closer
    python -m app.agents.sdr.test_sdr_agents --interactive
"""

import os
import sys
import argparse
import json
from datetime import datetime, timedelta
from typing import List, Dict
from pathlib import Path

# Diretório onde este arquivo está localizado
SCRIPT_DIR = Path(__file__).parent.absolute()

# Adiciona o diretório raiz ao path
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


# ============================================================================
# LOGGER — duplica stdout para arquivo de log
# ============================================================================

class TeeLogger:
    """Escreve simultaneamente no terminal e num arquivo de log."""

    def __init__(self, log_path: Path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()
        sys.stdout = self.terminal


def setup_logger(agent: str) -> TeeLogger:
    """Cria o diretório de logs e inicia o TeeLogger."""
    from app.core.config import get_settings
    settings = get_settings()
    provider = settings.dspy_provider
    model = settings.dspy_model if settings.dspy_provider != "glm" else "glm-5"

    logs_dir = SCRIPT_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{agent}_{provider}_{model}.log"
    log_path = logs_dir / filename

    logger = TeeLogger(log_path)
    sys.stdout = logger
    print(f"📝 Log salvo em: logs/{filename}\n")
    return logger

from app.core.config import init_dspy


# ============================================================================
# TEST SCENARIOS - GATEKEEPER
# ============================================================================

# Carregando do arquivo externo (usando caminho absoluto)
GATEKEEPER_JSON = SCRIPT_DIR / "test_gatekeeper_cases.json"
if GATEKEEPER_JSON.exists():
    with open(GATEKEEPER_JSON, 'r', encoding='utf-8') as f:
        GATEKEEPER_SCENARIOS = json.load(f)
else:
    # Fallback: cenários inline se arquivo não existir
    GATEKEEPER_SCENARIOS = [
        {
            "name": "Primeira mensagem",
            "clinic_name": "Clínica Bella Luna",
            "conversation_history": [],
            "latest_message": None,
            "expected_stage": "opening",
        },
    ]




# ============================================================================
# TEST SCENARIOS - CLOSER
# ============================================================================

def get_available_slots() -> List[str]:
    """Gera slots disponíveis para os próximos 3 dias"""
    slots = []
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for day_offset in range(1, 4):
        day = base + timedelta(days=day_offset)
        for hour in [9, 10, 11, 14, 15, 16, 17]:
            slots.append(day.strftime(f"%Y-%m-%d {hour:02d}:00"))
            slots.append(day.strftime(f"%Y-%m-%d {hour:02d}:30"))

    return slots

# Carregando do arquivo externo (usando caminho absoluto)
CLOSER_JSON = SCRIPT_DIR / "test_closer_cases.json"
if CLOSER_JSON.exists():
    with open(CLOSER_JSON, 'r', encoding='utf-8') as f:
        CLOSER_SCENARIOS = json.load(f)
else:
    # Fallback: cenários inline se arquivo não existir
    CLOSER_SCENARIOS = [
        {
            "name": "Primeira mensagem ao gestor",
            "manager_name": "Dr. Carlos",
            "manager_phone": "11999887766",
            "clinic_name": "Clínica Bella Luna",
            "clinic_specialty": "estética",
            "conversation_history": [],
            "latest_message": None,
            "expected_stage": "greeting",
        },
    ]


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_gatekeeper_test(scenario: Dict, verbose: bool = True):
    """Executa um cenário de teste do Gatekeeper"""
    from app.agents.sdr.gatekeeper import gatekeeper_graph

    print(f"\n{'='*60}")
    print(f"GATEKEEPER: {scenario['name']}")
    print(f"{'='*60}")

    if verbose and scenario.get("conversation_history"):
        print("\nHistórico:")
        for turn in scenario["conversation_history"]:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"  {prefix} {turn['content']}")

    if scenario.get("latest_message"):
        print(f"\nÚltima msg recebida: \"{scenario['latest_message']}\"")

    # Conta tentativas (permite override para testar fallback de max attempts)
    attempt_count = scenario.get("attempt_count_override", len([
        t for t in scenario.get("conversation_history", [])
        if t["role"] == "agent"
    ]))

    # Invoca o grafo
    result = gatekeeper_graph.invoke({
        "clinic_name": scenario["clinic_name"],
        "conversation_history": scenario.get("conversation_history", []),
        "latest_message": scenario.get("latest_message"),
        "current_hour": datetime.now().hour,
        "attempt_count": attempt_count,
    })

    print(f"\n📤 Resposta do agente:")
    print(f"   Mensagem: \"{result['response_message']}\"")
    print(f"   Stage: {result['conversation_stage']}")
    print(f"   Contato extraído: {result.get('extracted_manager_contact')}")
    print(f"   Nome extraído: {result.get('extracted_manager_name')}")
    print(f"   Enviar msg: {result['should_send_message']}")
    print(f"\n💭 Reasoning: {result['reasoning']}")

    return result


def run_closer_test(scenario: Dict, verbose: bool = True):
    """Executa um cenário de teste do Closer"""
    from app.agents.sdr.closer import closer_graph

    print(f"\n{'='*60}")
    print(f"CLOSER: {scenario['name']}")
    print(f"{'='*60}")

    if verbose and scenario.get("conversation_history"):
        print("\nHistórico:")
        for turn in scenario["conversation_history"]:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"  {prefix} {turn['content']}")

    if scenario.get("latest_message"):
        print(f"\nÚltima msg recebida: \"{scenario['latest_message']}\"")

    # Conta tentativas (permite override para testar fallback 4 — max attempts)
    attempt_count = scenario.get("attempt_count_override", len([
        t for t in scenario.get("conversation_history", [])
        if t["role"] == "agent"
    ]))

    # Gera slots disponíveis (permite override do cenário para testar edge cases)
    available_slots = scenario.get("available_slots_override", get_available_slots())

    # Invoca o grafo
    result = closer_graph.invoke({
        "manager_name": scenario["manager_name"],
        "manager_phone": scenario["manager_phone"],
        "clinic_name": scenario["clinic_name"],
        "clinic_specialty": scenario.get("clinic_specialty", "saúde"),
        "conversation_history": scenario.get("conversation_history", []),
        "latest_message": scenario.get("latest_message"),
        "available_slots": available_slots,
        "current_hour": scenario.get("current_hour_override", datetime.now().hour),
        "attempt_count": attempt_count,
    })

    print(f"\n📤 Resposta do agente:")

    # Trata múltiplas mensagens
    messages = result["response_message"].split("|||")
    for i, msg in enumerate(messages, 1):
        if len(messages) > 1:
            print(f"   Mensagem {i}: \"{msg.strip()}\"")
        else:
            print(f"   Mensagem: \"{msg.strip()}\"")

    print(f"   Stage: {result['conversation_stage']}")
    print(f"   Reunião confirmada: {result['meeting_confirmed']}")
    if result.get("meeting_datetime"):
        print(f"   Data/hora: {result['meeting_datetime']}")
    print(f"   Enviar msg: {result['should_send_message']}")
    print(f"\n💭 Reasoning: {result['reasoning']}")

    # Verifica expectativa
    if scenario.get("expected_stage"):
        expected = scenario["expected_stage"]
        actual = result["conversation_stage"]
        status = "✅" if actual == expected else "⚠️"
        print(f"\n{status} Stage esperado: {expected}, obtido: {actual}")

    return result


def run_interactive_gatekeeper():
    """Modo interativo para testar Gatekeeper"""
    from app.agents.sdr.gatekeeper import gatekeeper_graph

    print("\n" + "="*60)
    print("MODO INTERATIVO - GATEKEEPER")
    print("="*60)

    clinic_name = input("\nNome da clínica: ").strip() or "Clínica Teste"
    conversation_history = []

    print(f"\nIniciando conversa com {clinic_name}...")
    print("(Digite 'sair' para encerrar)\n")

    while True:
        # Conta tentativas
        attempt_count = len([t for t in conversation_history if t["role"] == "agent"])

        # Se primeira mensagem ou após resposta humana
        latest_message = None
        if conversation_history and conversation_history[-1]["role"] == "human":
            latest_message = conversation_history[-1]["content"]

        # Invoca agente
        result = gatekeeper_graph.invoke({
            "clinic_name": clinic_name,
            "conversation_history": conversation_history,
            "latest_message": latest_message,
            "current_hour": datetime.now().hour,
            "attempt_count": attempt_count,
        })

        print(f"🤖 Agente: {result['response_message']}")
        print(f"   [Stage: {result['conversation_stage']}]")

        if result.get("extracted_manager_contact"):
            print(f"   ✅ Contato extraído: {result['extracted_manager_contact']}")

        # Adiciona ao histórico
        conversation_history.append({
            "role": "agent",
            "content": result["response_message"]
        })

        # Verifica se acabou
        if not result["should_send_message"] or result["conversation_stage"] in ["success", "failed"]:
            print("\n[Conversa encerrada]")
            break

        # Input do usuário (simula recepção)
        user_input = input("\n👤 Recepção: ").strip()
        if user_input.lower() == "sair":
            break

        conversation_history.append({
            "role": "human",
            "content": user_input
        })


def run_interactive_closer():
    """Modo interativo para testar Closer"""
    from app.agents.sdr.closer import closer_graph

    print("\n" + "="*60)
    print("MODO INTERATIVO - CLOSER")
    print("="*60)

    manager_name = input("\nNome do gestor (ex: Dr. Carlos): ").strip() or "Dr. Teste"
    clinic_name = input("Nome da clínica: ").strip() or "Clínica Teste"
    specialty = input("Especialidade (odonto/estética/etc): ").strip() or "saúde"

    conversation_history = []
    available_slots = get_available_slots()

    print(f"\nIniciando conversa com {manager_name} da {clinic_name}...")
    print("(Digite 'sair' para encerrar)\n")

    while True:
        # Conta tentativas
        attempt_count = len([t for t in conversation_history if t["role"] == "agent"])

        # Se primeira mensagem ou após resposta humana
        latest_message = None
        if conversation_history and conversation_history[-1]["role"] == "human":
            latest_message = conversation_history[-1]["content"]

        # Invoca agente
        result = closer_graph.invoke({
            "manager_name": manager_name,
            "manager_phone": "11999999999",
            "clinic_name": clinic_name,
            "clinic_specialty": specialty,
            "conversation_history": conversation_history,
            "latest_message": latest_message,
            "available_slots": available_slots,
            "current_hour": datetime.now().hour,
            "attempt_count": attempt_count,
        })

        # Mostra mensagens (pode ter múltiplas)
        messages = result["response_message"].split("|||")
        for msg in messages:
            print(f"🤖 Agente: {msg.strip()}")
            conversation_history.append({
                "role": "agent",
                "content": msg.strip()
            })

        print(f"   [Stage: {result['conversation_stage']}]")

        if result.get("meeting_confirmed"):
            print(f"   ✅ Reunião agendada: {result['meeting_datetime']}")

        # Verifica se acabou
        if not result["should_send_message"] or result["conversation_stage"] in ["scheduled", "lost"]:
            print("\n[Conversa encerrada]")
            break

        # Input do usuário (simula gestor)
        user_input = input("\n👤 Gestor: ").strip()
        if user_input.lower() == "sair":
            break

        conversation_history.append({
            "role": "human",
            "content": user_input
        })


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Testes dos agentes SDR")
    parser.add_argument("--gatekeeper", action="store_true", help="Rodar cenários do Gatekeeper")
    parser.add_argument("--closer", action="store_true", help="Rodar cenários do Closer")
    parser.add_argument("--interactive", action="store_true", help="Modo interativo")
    parser.add_argument("--all", action="store_true", help="Rodar todos os cenários")

    args = parser.parse_args()

    # Se nenhum argumento, mostra ajuda
    if not any([args.gatekeeper, args.closer, args.interactive, args.all]):
        parser.print_help()
        print("\nExemplos:")
        print("  python -m app.agents.sdr.test_sdr_agents --gatekeeper")
        print("  python -m app.agents.sdr.test_sdr_agents --closer")
        print("  python -m app.agents.sdr.test_sdr_agents --interactive")
        print("  python -m app.agents.sdr.test_sdr_agents --all")
        return

    # Inicializa DSPy
    print("Inicializando DSPy...")
    init_dspy()
    print("DSPy inicializado!\n")

    # Modo interativo — sem log (é interativo, não faz sentido)
    if args.interactive:
        print("\nEscolha o agente:")
        print("1. Gatekeeper (coletar contato)")
        print("2. Closer (agendar reunião)")
        choice = input("\nOpção (1/2): ").strip()

        if choice == "1":
            run_interactive_gatekeeper()
        elif choice == "2":
            run_interactive_closer()
        else:
            print("Opção inválida")
        return

    # Determina qual agente para nomear o log
    agent_label = "all"
    if args.gatekeeper and not args.closer:
        agent_label = "gatekeeper"
    elif args.closer and not args.gatekeeper:
        agent_label = "closer"

    # Inicia logger (após init_dspy para ter settings disponível)
    logger = setup_logger(agent_label)

    # Contadores globais de pass/fail
    total_passed = 0
    total_failed = 0
    failures = []

    # Cenários Gatekeeper
    if args.gatekeeper or args.all:
        print("\n" + "#"*60)
        print("# TESTES GATEKEEPER")
        print("#"*60)

        g_passed = g_failed = 0
        for scenario in GATEKEEPER_SCENARIOS:
            try:
                result = run_gatekeeper_test(scenario)
                scenario_ok = True
                fail_reasons = []

                # Check 1: Stage classification
                expected = scenario.get("expected_stage")
                actual = result["conversation_stage"]
                if expected and actual != expected:
                    scenario_ok = False
                    fail_reasons.append(f"stage: esperado={expected}, obtido={actual}")

                # Check 2: should_send_message (if annotated)
                if "expected_should_continue" in scenario:
                    if result.get("should_send_message") != scenario["expected_should_continue"]:
                        scenario_ok = False
                        fail_reasons.append(
                            f"should_send_message: esperado={scenario['expected_should_continue']}, "
                            f"obtido={result.get('should_send_message')}"
                        )

                if scenario_ok:
                    g_passed += 1
                else:
                    g_failed += 1
                    reason_str = " | ".join(fail_reasons)
                    failures.append(f"GATEKEEPER | {scenario['name']} | {reason_str}")
            except Exception as e:
                g_failed += 1
                failures.append(f"GATEKEEPER | {scenario['name']} | ERRO: {e}")
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")

        total_passed += g_passed
        total_failed += g_failed
        total_g = g_passed + g_failed
        print(f"\n{'='*60}")
        print(f"GATEKEEPER: {g_passed}/{total_g} ({100*g_passed//total_g if total_g else 0}%)")
        print(f"{'='*60}")

    # Cenários Closer
    if args.closer or args.all:
        print("\n" + "#"*60)
        print("# TESTES CLOSER")
        print("#"*60)

        c_passed = c_failed = 0
        for scenario in CLOSER_SCENARIOS:
            try:
                result = run_closer_test(scenario)
                expected = scenario.get("expected_stage")
                actual = result["conversation_stage"]
                scenario_ok = True
                fail_reasons = []

                # Check 1: Stage classification
                if expected and actual != expected:
                    scenario_ok = False
                    fail_reasons.append(f"stage: esperado={expected}, obtido={actual}")

                # Check 2: meeting_confirmed (if annotated)
                if "expected_meeting_confirmed" in scenario:
                    if result.get("meeting_confirmed") != scenario["expected_meeting_confirmed"]:
                        scenario_ok = False
                        fail_reasons.append(
                            f"meeting_confirmed: esperado={scenario['expected_meeting_confirmed']}, "
                            f"obtido={result.get('meeting_confirmed')}"
                        )

                # Check 3: should_send_message (if annotated)
                if "expected_should_continue" in scenario:
                    if result.get("should_send_message") != scenario["expected_should_continue"]:
                        scenario_ok = False
                        fail_reasons.append(
                            f"should_send_message: esperado={scenario['expected_should_continue']}, "
                            f"obtido={result.get('should_send_message')}"
                        )

                # Check 4: meeting_datetime ISO format (if annotated)
                if scenario.get("expected_datetime_format") == "iso":
                    dt_val = result.get("meeting_datetime")
                    if not dt_val:
                        scenario_ok = False
                        fail_reasons.append("meeting_datetime: esperado ISO, obtido=None")
                    else:
                        try:
                            datetime.fromisoformat(dt_val)
                        except (ValueError, TypeError):
                            scenario_ok = False
                            fail_reasons.append(f"meeting_datetime: formato inválido '{dt_val}'")

                if scenario_ok:
                    c_passed += 1
                else:
                    c_failed += 1
                    reason_str = " | ".join(fail_reasons)
                    failures.append(f"CLOSER | {scenario['name']} | {reason_str}")
            except Exception as e:
                c_failed += 1
                failures.append(f"CLOSER | {scenario['name']} | ERRO: {e}")
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")

        total_passed += c_passed
        total_failed += c_failed
        total_c = c_passed + c_failed
        print(f"\n{'='*60}")
        print(f"CLOSER: {c_passed}/{total_c} ({100*c_passed//total_c if total_c else 0}%)")
        print(f"{'='*60}")

    # Sumário final
    total = total_passed + total_failed
    pct = 100 * total_passed // total if total else 0
    print(f"\n{'='*60}")
    print(f"RESULTADO FINAL: {total_passed}/{total} ({pct}%)")
    if failures:
        print(f"\n⚠️  FALHAS ({len(failures)}):")
        for f in failures:
            print(f"   • {f}")
    else:
        print("✅ Todos os cenários passaram!")
    print(f"{'='*60}")
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    logger.close()


if __name__ == "__main__":
    main()
