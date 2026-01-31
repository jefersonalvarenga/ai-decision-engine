import dspy
import os
from dotenv import load_dotenv
from typing import List, Optional
import warnings
import json  # <--- ADICIONE ESTA LINHA AQUI

# Silenciador de avisos do Mac
warnings.filterwarnings("ignore")
import urllib3
urllib3.disable_warnings()

load_dotenv()

# 1. Configuração do Motor
turbo = dspy.LM('openai/gpt-4o-mini', api_key=os.getenv("OPENAI_API_KEY"), max_tokens=800)
dspy.settings.configure(lm=turbo, adapter=dspy.ChatAdapter())

# 2. Signature "Realidade EasyScale"
class RouterSignature(dspy.Signature):
    """
    You are a router agent responsible for identifying which specialized agents (domains) need to be activated to fully address the patient's current message and needs in a conversational flow via WhatsApp.
    
    CRITICAL CONTEXT: 
    This system is a high-conversion sales funnel for a **high-end aesthetic clinic** (private pay only). 
    The primary goal is to convert leads (often from Instagram ads) into paying patients for **high-cost procedures**. 
    The router must prioritize intentions that indicate a strong purchase intent (e.g., SERVICE_SCHEDULING, PROCEDURE_INQUIRY, AD_CONVERSION) and handle all inquiries with a premium, conversion-focused approach.

    Routing Instructions:
    1. Focus on the most recent message (`latest_incoming`). Use `history` to understand the messages exchanges between the lead/patient and the multiple agents present in this system.
    2. Intentions Enumerators: The list of valid intentions is defined by the IntentType Enum.
        - 'SESSION_START': The patient initiates the conversation (e.g., "Hello", "Good morning").
        - 'SESSION_CLOSURE': The patient explicitly ends the conversation (e.g., "Thank you, bye", "I'm done").
        - 'SERVICE_SCHEDULING': The patient expresses interest in booking a service or appointment, OR the patient is actively discussing scheduling details (e.g., "When can I do the procedure?", "Is Tuesday the only time?", "I'm doing pilates at that time"). This activates the specialized Scheduling Agent.
        - 'SERVICE_RESCHEDULING': The patient requests to change an existing appointment. This activates the specialized Rescheduling Agent.
        - 'SERVICE_CANCELLATION': The patient requests to cancel an existing appointment. This activates the specialized Cancellation Agent.
        - 'INTAKE': The patient is responding to clinical probes (intake), providing medical history relevant to aesthetic procedures. This activates the specialized Intake Assessment Agent.
        - 'MEDICAL_ASSESSMENT': The patient is asking a spontaneous medical question, often related to the safety or efficacy of aesthetic treatments. This activates the specialized Medical Assessment Agent.
        - 'PROCEDURE_INQUIRY': The patient asks about a specific aesthetic procedure, treatment, or service offered (e.g., "How much is a facelift?", "Tell me about the recovery for liposuction"). This is a high-priority conversion signal and activates the specialized Procedure Inquiry Agent.
        - 'AD_CONVERSION': The patient mentions or refers to a specific advertisement or campaign. This is a high-priority conversion signal.
        - 'ORGANIC_INQUIRY': The patient is making a general, non-ad-related inquiry about services.
        - 'OFFER_CONVERSION': The patient is responding to a specific promotional offer. This is a high-priority conversion signal.
        - 'REENGAGEMENT_RECOVERY': The patient is responding to a re-engagement message from the agent after a period of inactivity.
        - 'GENERAL_INFO': The patient asks for institutional or general information (e.g., address, opening hours, general pricing). Given the high-cost context, the response should be premium and immediately attempt to guide the patient back to a conversion-focused intention (e.g., SERVICE_SCHEDULING or PROCEDURE_INQUIRY). This activates the specialized General Info Agent.
        - 'IMAGE_ASSESSMENT': The patient sends an image or indicates a need for image analysis (e.g., "I'm sending a picture of my rash").
        - 'HUMAN_ESCALATION': The patient explicitly requests to speak to a human agent (e.g., "I want to talk to a person"). This is a high-priority signal.
        - 'UNCLASSIFIED': None of the above intentions clearly represent the message content.
    
    4. Analyze the entire phrase and include ALL applicable intentions. This is CRITICAL, as including all intentions ensures that ALL necessary specialized agents are activated to fully address the patient's needs and questions. Failing to include an intention will prevent the corresponding agent from being activated.

    Confidence Notes (Suggestion):
    - 0.90–1.00: clear and explicit
    - 0.60–0.89: probable with some ambiguity
    - <0.60: uncertain / weak context
    """
    
    latest_message = dspy.InputField(desc="Mensagem atual do lead")
    history = dspy.InputField(desc="Últimas interações para contexto")
    ad_conversion_status = dspy.InputField(desc="idle, in_progress, completed")
    intake_status = dspy.InputField(desc="idle, in_progress, completed")
    schedule_status = dspy.InputField(desc="idle, in_progress, completed")
    reschedule_status = dspy.InputField(desc="idle, in_progress, completed")
    cancel_status = dspy.InputField(desc="idle, in_progress, completed")
    is_ad_click = dspy.InputField(desc="Boolean: True se o lead veio de um anúncio agora")
    ad_metadata = dspy.InputField(desc="Informações da campanha/oferta (ex: Fotona 20% OFF)")
    language = dspy.InputField(desc="Idioma de resposta do raciocínio (ex: PT-BR)")

    intents: List[str] = dspy.OutputField(desc="Lista de intenções detectadas")
    reasoning = dspy.OutputField(desc="Explicação curta do porquê em PT-BR")

# 3. O Simulador de Realidade
def run_easyscale_test():
    router = dspy.ChainOfThought(RouterSignature)
    
    # Carregando do arquivo externo
    with open('test_cases.json', 'r', encoding='utf-8') as f:
        test_cases = json.load(f)

    print("\n--- 🏥 EASYSCALE ROUTER: TESTE DE CAMPO ---\n")
    for case in test_cases:
        pred = router(**case)
        print(f"📥 MSG RECEBIDA: {case['latest_message']}")
        print(f"🎯 INTENÇÕES: {pred.intents}")
        print(f"PENSAMENTO: {getattr(pred, 'reasoning', getattr(pred, 'rationale', 'N/A'))}")
        print(f"📢 AD_FLAG: {case['is_ad_click']}")
        print("-" * 50)

if __name__ == "__main__":
    run_easyscale_test()