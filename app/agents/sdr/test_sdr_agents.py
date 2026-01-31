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
from datetime import datetime, timedelta
from typing import List, Dict
import json  # <--- ADICIONE ESTA LINHA AQUI

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.core.config import init_dspy


# ============================================================================
# TEST SCENARIOS - GATEKEEPER
# ============================================================================

# Carregando do arquivo externo
with open('test_gatekeeper_cases.json', 'r', encoding='utf-8') as f:
    GATEKEEPER_SCENARIOS = json.load(f)




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

# Carregando do arquivo externo
with open('test_closer_cases.json', 'r', encoding='utf-8') as f:
    CLOSER_SCENARIOS = json.load(f)


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

    # Conta tentativas
    attempt_count = len([
        t for t in scenario.get("conversation_history", [])
        if t["role"] == "agent"
    ])

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

    # Verifica expectativa
    if scenario.get("expected_stage"):
        expected = scenario["expected_stage"]
        actual = result["conversation_stage"]
        status = "✅" if actual == expected else "⚠️"
        print(f"\n{status} Stage esperado: {expected}, obtido: {actual}")

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

    # Conta tentativas
    attempt_count = len([
        t for t in scenario.get("conversation_history", [])
        if t["role"] == "agent"
    ])

    # Gera slots disponíveis
    available_slots = get_available_slots()

    # Invoca o grafo
    result = closer_graph.invoke({
        "manager_name": scenario["manager_name"],
        "manager_phone": scenario["manager_phone"],
        "clinic_name": scenario["clinic_name"],
        "clinic_specialty": scenario.get("clinic_specialty", "saúde"),
        "conversation_history": scenario.get("conversation_history", []),
        "latest_message": scenario.get("latest_message"),
        "available_slots": available_slots,
        "current_hour": datetime.now().hour,
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

    # Modo interativo
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

    # Cenários Gatekeeper
    if args.gatekeeper or args.all:
        print("\n" + "#"*60)
        print("# TESTES GATEKEEPER")
        print("#"*60)

        for scenario in GATEKEEPER_SCENARIOS:
            try:
                run_gatekeeper_test(scenario)
            except Exception as e:
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")

    # Cenários Closer
    if args.closer or args.all:
        print("\n" + "#"*60)
        print("# TESTES CLOSER")
        print("#"*60)

        for scenario in CLOSER_SCENARIOS:
            try:
                run_closer_test(scenario)
            except Exception as e:
                print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")

    print("\n" + "="*60)
    print("Testes concluídos!")
    print("="*60)


if __name__ == "__main__":
    main()
