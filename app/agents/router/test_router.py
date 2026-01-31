"""
Testes locais para o Router Agent

Execute com:
    python -m app.agents.router.test_router

Ou para testar cenários específicos:
    python -m app.agents.router.test_router --interactive
"""

import os
import sys
import argparse
import json
from datetime import datetime
from typing import Dict
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.core.config import init_dspy


# ============================================================================
# TEST SCENARIOS
# ============================================================================

ROUTER_SCENARIOS = [
    # Scheduling
    {
        "name": "Agendamento direto",
        "latest_incoming": "Quero agendar uma consulta para segunda-feira",
        "history": [],
        "expected_intentions": ["SERVICE_SCHEDULING"],
    },
    {
        "name": "Agendamento com procedimento",
        "latest_incoming": "Gostaria de marcar uma sessão de botox",
        "history": [],
        "expected_intentions": ["SERVICE_SCHEDULING", "PROCEDURE_INQUIRY"],
    },

    # Ad conversion
    {
        "name": "Resposta a anúncio",
        "latest_incoming": "Vi o anúncio do Fotona com 20% de desconto, quero saber mais",
        "history": [],
        "expected_intentions": ["AD_CONVERSION", "PROCEDURE_INQUIRY"],
    },
    {
        "name": "Conversão de oferta",
        "latest_incoming": "Quero aproveitar a promoção que vocês mandaram",
        "history": [],
        "expected_intentions": ["OFFER_CONVERSION"],
    },

    # Intake / Medical
    {
        "name": "Resposta de intake",
        "latest_incoming": "Sim, tenho alergia a dipirona e uso anticoagulante",
        "history": [
            {"role": "agent", "content": "Você possui alguma alergia ou usa medicamentos?"}
        ],
        "intake_status": "in_progress",
        "expected_intentions": ["INTAKE"],
    },
    {
        "name": "Dúvida médica",
        "latest_incoming": "O procedimento dói? Preciso de anestesia?",
        "history": [],
        "expected_intentions": ["MEDICAL_ASSESSMENT"],
    },

    # Rescheduling / Cancellation
    {
        "name": "Reagendamento",
        "latest_incoming": "Preciso remarcar minha consulta de terça para quinta",
        "history": [],
        "expected_intentions": ["SERVICE_RESCHEDULING"],
    },
    {
        "name": "Cancelamento",
        "latest_incoming": "Não vou poder ir na consulta, quero cancelar",
        "history": [],
        "expected_intentions": ["SERVICE_CANCELLATION"],
    },

    # Session management
    {
        "name": "Início de sessão",
        "latest_incoming": "Oi, boa tarde!",
        "history": [],
        "expected_intentions": ["SESSION_START"],
    },
    {
        "name": "Encerramento",
        "latest_incoming": "Ok, obrigado! Até mais!",
        "history": [
            {"role": "agent", "content": "Sua consulta está confirmada para segunda às 14h."}
        ],
        "expected_intentions": ["SESSION_CLOSURE"],
    },

    # Escalation
    {
        "name": "Pedido de humano",
        "latest_incoming": "Quero falar com uma pessoa de verdade, não com robô",
        "history": [],
        "expected_intentions": ["HUMAN_ESCALATION"],
    },

    # General info
    {
        "name": "Informação geral",
        "latest_incoming": "Qual o endereço da clínica?",
        "history": [],
        "expected_intentions": ["GENERAL_INFO"],
    },

    # Procedure inquiry
    {
        "name": "Dúvida sobre procedimento",
        "latest_incoming": "Quanto custa uma harmonização facial?",
        "history": [],
        "expected_intentions": ["PROCEDURE_INQUIRY"],
    },

    # Complex / Multiple intentions
    {
        "name": "Múltiplas intenções",
        "latest_incoming": "Oi! Vi o anúncio do Instagram, quanto custa o peeling e qual o endereço?",
        "history": [],
        "expected_intentions": ["SESSION_START", "AD_CONVERSION", "PROCEDURE_INQUIRY", "GENERAL_INFO"],
    },
]


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_router_test(scenario: Dict, verbose: bool = True):
    """Executa um cenário de teste do Router"""
    from app.agents.router import app_graph

    print(f"\n{'='*60}")
    print(f"ROUTER: {scenario['name']}")
    print(f"{'='*60}")

    print(f"\nMensagem: \"{scenario['latest_incoming']}\"")

    if scenario.get("history"):
        print("\nHistórico:")
        for turn in scenario["history"]:
            prefix = "🤖" if turn["role"] == "agent" else "👤"
            print(f"  {prefix} {turn['content']}")

    # Invoca o grafo
    result = app_graph.invoke({
        "latest_incoming": scenario["latest_incoming"],
        "history": scenario.get("history", []),
        "intake_status": scenario.get("intake_status", "idle"),
        "schedule_status": scenario.get("schedule_status", "idle"),
        "reschedule_status": scenario.get("reschedule_status", "idle"),
        "cancel_status": scenario.get("cancel_status", "idle"),
        "language": scenario.get("language", "pt-BR"),
    })

    print(f"\n📤 Resultado:")
    print(f"   Intenções: {result['intentions']}")
    print(f"   Confiança: {result['confidence']:.2f}")
    print(f"\n💭 Reasoning: {result['reasoning']}")

    # Verifica expectativa
    if scenario.get("expected_intentions"):
        expected = set(scenario["expected_intentions"])
        actual = set(result["intentions"])

        # Verifica se todas as esperadas estão presentes
        missing = expected - actual
        extra = actual - expected

        if not missing:
            print(f"\n✅ Intenções esperadas encontradas")
        else:
            print(f"\n⚠️ Intenções faltando: {missing}")

        if extra:
            print(f"   Intenções extras: {extra}")

    return result


def run_interactive():
    """Modo interativo para testar o Router"""
    from app.agents.router import app_graph

    print("\n" + "="*60)
    print("MODO INTERATIVO - ROUTER")
    print("="*60)
    print("\nDigite mensagens para classificar.")
    print("(Digite 'sair' para encerrar)\n")

    history = []

    while True:
        message = input("\n👤 Mensagem: ").strip()
        if message.lower() == "sair":
            break

        result = app_graph.invoke({
            "latest_incoming": message,
            "history": history,
            "intake_status": "idle",
            "schedule_status": "idle",
            "reschedule_status": "idle",
            "cancel_status": "idle",
            "language": "pt-BR",
        })

        print(f"\n📤 Intenções: {result['intentions']}")
        print(f"   Confiança: {result['confidence']:.2f}")
        print(f"   Reasoning: {result['reasoning']}")

        # Adiciona ao histórico
        history.append({"role": "human", "content": message})


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Testes do Router Agent")
    parser.add_argument("--interactive", action="store_true", help="Modo interativo")
    parser.add_argument("--scenario", type=str, help="Nome do cenário específico para testar")

    args = parser.parse_args()

    # Inicializa DSPy
    print("Inicializando DSPy...")
    init_dspy()
    print("DSPy inicializado!\n")

    # Modo interativo
    if args.interactive:
        run_interactive()
        return

    # Cenário específico
    if args.scenario:
        scenario = next(
            (s for s in ROUTER_SCENARIOS if s["name"].lower() == args.scenario.lower()),
            None
        )
        if scenario:
            run_router_test(scenario)
        else:
            print(f"Cenário não encontrado: {args.scenario}")
            print("Cenários disponíveis:")
            for s in ROUTER_SCENARIOS:
                print(f"  - {s['name']}")
        return

    # Todos os cenários
    print("#"*60)
    print("# TESTES ROUTER")
    print("#"*60)

    for scenario in ROUTER_SCENARIOS:
        try:
            run_router_test(scenario)
        except Exception as e:
            print(f"\n❌ ERRO no cenário '{scenario['name']}': {e}")

    print("\n" + "="*60)
    print("Testes concluídos!")
    print("="*60)


if __name__ == "__main__":
    main()
