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

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.core.config import init_dspy


# ============================================================================
# TEST SCENARIOS - GATEKEEPER
# ============================================================================

GATEKEEPER_SCENARIOS = [
    {
        "name": "Primeira mensagem",
        "clinic_name": "Clínica Bella Luna",
        "conversation_history": [],
        "latest_message": None,
        "expected_stage": "opening",
    },
    {
        "name": "Recepção confirma clínica",
        "clinic_name": "Clínica Bella Luna",
        "conversation_history": [
            {"role": "agent", "content": "Bom dia, é da clínica Bella Luna?"},
            {"role": "human", "content": "Bom dia! Sim, aqui é a Juliana. Em que posso ajudar?"},
        ],
        "latest_message": "Bom dia! Sim, aqui é a Juliana. Em que posso ajudar?",
        "expected_stage": "requesting",
    },
    {
        "name": "Recepção pergunta do que se trata",
        "clinic_name": "Clínica Bella Luna",
        "conversation_history": [
            {"role": "agent", "content": "Bom dia, é da clínica Bella Luna?"},
            {"role": "human", "content": "Sim, aqui é Juliana. Em que posso ajudar?"},
            {"role": "agent", "content": "Gostaria de falar com o gestor ou gestora da clínica."},
            {"role": "human", "content": "Pode me adiantar do que se trata?"},
        ],
        "latest_message": "Pode me adiantar do que se trata?",
        "expected_stage": "handling_objection",
    },
    {
        "name": "Recepção fornece contato",
        "clinic_name": "Clínica Bella Luna",
        "conversation_history": [
            {"role": "agent", "content": "Bom dia, é da clínica Bella Luna?"},
            {"role": "human", "content": "Sim, é sim."},
            {"role": "agent", "content": "Gostaria de falar com o gestor ou gestora da clínica."},
            {"role": "human", "content": "Do que se trata?"},
            {"role": "agent", "content": "Seria sobre assunto comercial."},
            {"role": "human", "content": "Ok, o número do Dr. Carlos é 11999887766"},
        ],
        "latest_message": "Ok, o número do Dr. Carlos é 11999887766",
        "expected_stage": "success",
    },
    {
        "name": "Recepção nega passar contato",
        "clinic_name": "Clínica Odonto Smile",
        "conversation_history": [
            {"role": "agent", "content": "Boa tarde, é da clínica Odonto Smile?"},
            {"role": "human", "content": "Sim"},
            {"role": "agent", "content": "Gostaria de falar com o gestor da clínica."},
            {"role": "human", "content": "Não passamos contato de gestor. Pode mandar email."},
        ],
        "latest_message": "Não passamos contato de gestor. Pode mandar email.",
        "expected_stage": "handling_objection",  # Ainda tenta uma vez
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
    {
        "name": "Gestor responde saudação",
        "manager_name": "Dr. Carlos",
        "manager_phone": "11999887766",
        "clinic_name": "Clínica Bella Luna",
        "clinic_specialty": "estética",
        "conversation_history": [
            {"role": "agent", "content": "Boa tarde Dr. Carlos, aqui é Jeferson da EasyScale. Tudo bem?"},
            {"role": "human", "content": "Tudo bem e você?"},
        ],
        "latest_message": "Tudo bem e você?",
        "expected_stage": "pitching",
    },
    {
        "name": "Gestor aceita conversar",
        "manager_name": "Dra. Ana",
        "manager_phone": "21988776655",
        "clinic_name": "Estética Premium",
        "clinic_specialty": "estética",
        "conversation_history": [
            {"role": "agent", "content": "Bom dia Dra. Ana, aqui é Jeferson da EasyScale. Tudo bem?"},
            {"role": "human", "content": "Tudo bem!"},
            {"role": "agent", "content": "Nossa empresa ajuda clínicas de estética a duplicarem o faturamento com ferramentas de tecnologia para a equipe de atendimento."},
            {"role": "agent", "content": "Faria sentido batermos um papo pra eu mostrar como funciona?"},
            {"role": "human", "content": "Podemos marcar sim"},
        ],
        "latest_message": "Podemos marcar sim",
        "expected_stage": "proposing_time",
    },
    {
        "name": "Gestor contrapropõe horário",
        "manager_name": "Dr. Marcos",
        "manager_phone": "47991234567",
        "clinic_name": "OdontoVida",
        "clinic_specialty": "odonto",
        "conversation_history": [
            {"role": "agent", "content": "Boa tarde Dr. Marcos, aqui é Jeferson da EasyScale. Tudo bem?"},
            {"role": "human", "content": "Tudo joia"},
            {"role": "agent", "content": "Nossa empresa ajuda clínicas de odonto a duplicarem o faturamento. Faria sentido batermos um papo?"},
            {"role": "human", "content": "Pode ser"},
            {"role": "agent", "content": "Amanhã às 15h seria um bom horário? São só 20 minutinhos."},
            {"role": "human", "content": "Pode ser 15:30?"},
        ],
        "latest_message": "Pode ser 15:30?",
        "expected_stage": "confirming",
    },
    {
        "name": "Gestor pede material primeiro",
        "manager_name": "Dr. Roberto",
        "manager_phone": "31999998888",
        "clinic_name": "Clínica Derma",
        "clinic_specialty": "dermatologia",
        "conversation_history": [
            {"role": "agent", "content": "Bom dia Dr. Roberto, aqui é Jeferson da EasyScale. Tudo bem?"},
            {"role": "human", "content": "Bom dia"},
            {"role": "agent", "content": "Nossa empresa ajuda clínicas a duplicarem o faturamento. Podemos conversar?"},
            {"role": "human", "content": "Me manda um material primeiro por email"},
        ],
        "latest_message": "Me manda um material primeiro por email",
        "expected_stage": "pitching",  # Tenta contornar
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
