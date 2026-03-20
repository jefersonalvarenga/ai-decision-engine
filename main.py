"""
EasyScale Unified API
Suporta os fluxos de Roteamento (Router) e Re-engajamento (Re-engagement).
"""

import time
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Importações dos seus módulos revisados
from app.core.config import get_settings, init_dspy
from app.agents.router.graph import app_graph as router_graph
from app.agents.reengage.graph import app_graph as reengage_graph
from app.agents.sdr import gatekeeper_graph, closer_graph
from app.agents.sdr.state import ConversationTurn
from app.core.security import SecurityMiddleware, AccessLogMiddleware
from app.utils.name_cleaner import extract_short_name

# ============================================================================
# APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="EasyScale Clinic API",
    description="Sistema Multi-Agente para Clínicas de Estética",
    version="2.0.0"
)

# Middlewares
app.add_middleware(SecurityMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODELS
# ============================================================================

class RouterRequest(BaseModel):
    """Request for Router agent - classifies patient intentions"""
    latest_incoming: str = Field(..., description="Última mensagem do paciente")
    history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Histórico da conversa [{role, content}]"
    )
    intake_status: str = Field(default="idle", description="Status do intake")
    schedule_status: str = Field(default="idle", description="Status do agendamento")
    reschedule_status: str = Field(default="idle", description="Status do reagendamento")
    cancel_status: str = Field(default="idle", description="Status do cancelamento")
    language: str = Field(default="pt-BR", description="Idioma do paciente")


class RouterResponse(BaseModel):
    """Response from Router agent"""
    intentions: List[str] = Field(..., description="Lista de intenções identificadas")
    reasoning: str = Field(..., description="Explicação da decisão")
    confidence: float = Field(..., description="Nível de confiança (0.0 a 1.0)")
    processing_time_ms: float

class ReengageRequest(BaseModel):
    lead_name: str
    ad_source: str
    psychographic_profile: str
    conversation_history: str

class ReengageResponse(BaseModel):
    generated_copy: str
    selected_strategy: str
    analyst_diagnosis: str
    revision_count: int


# SDR Models
class SDRConversationTurn(BaseModel):
    role: str = Field(..., pattern="^(agent|human)$")
    content: str
    stage: Optional[str] = None


class GatekeeperRequest(BaseModel):
    """Request from n8n webhook for Gatekeeper agent"""
    clinic_name: str = Field(..., description="Nome da clínica")
    sdr_name: str = Field(default="Vera", description="Nome do agente SDR. Usado para se apresentar se perguntado.")
    clinic_phone: str = Field(..., description="WhatsApp da clínica")
    conversation_history: List[SDRConversationTurn] = Field(
        default_factory=list,
        description="Histórico da conversa"
    )
    latest_message: Optional[str] = Field(
        None,
        description="Última mensagem recebida (None se primeira mensagem)"
    )
    current_weekday: Optional[int] = Field(
        None,
        description="Dia da semana (0=segunda … 6=domingo). Opcional — servidor computa se ausente."
    )
    current_hour: Optional[int] = Field(
        None,
        description="Hora local do n8n (0-23). Opcional — servidor computa via America/Sao_Paulo se ausente."
    )
    detected_persona: Optional[str] = Field(
        None,
        description="Persona detectada pelo Supabase (ignorada — PersonaDetector roda todo turno no grafo)."
    )
    persona_confidence: Optional[str] = Field(
        None,
        description="Confiança anterior (ignorada — PersonaDetector roda todo turno no grafo)."
    )
    is_homolog: bool = Field(
        default=False,
        description="True se a conversa é de homologação (n8n envia com base em gk_conversations.is_homolog)."
    )
    current_status: Optional[str] = Field(
        default=None,
        description="Status atual da conversa no Supabase (opted_out, denied, etc.)."
    )


class GatekeeperResponse(BaseModel):
    """Response to n8n with action to take"""
    response_message: str
    conversation_stage: str
    extracted_manager_contact: Optional[str] = None
    extracted_manager_email: Optional[str] = None
    extracted_manager_name: Optional[str] = None
    should_send_message: bool
    reasoning: str
    processing_time_ms: float
    detected_persona: Optional[str] = None
    persona_confidence: Optional[str] = None
    approach_used: Optional[str] = None


class CloserRequest(BaseModel):
    """Request from n8n webhook for Closer agent"""
    manager_name: str = Field(..., description="Nome do gestor")
    manager_phone: str = Field(..., description="WhatsApp do gestor")
    clinic_name: str = Field(..., description="Nome da clínica")
    clinic_specialty: Optional[str] = Field(
        None,
        description="Especialidade: odonto, estética, etc"
    )
    conversation_history: List[SDRConversationTurn] = Field(
        default_factory=list,
        description="Histórico da conversa"
    )
    latest_message: Optional[str] = Field(
        None,
        description="Última mensagem recebida"
    )
    available_slots: List[str] = Field(
        ...,
        description="Horários disponíveis no formato 'YYYY-MM-DD HH:MM'"
    )


class CloserResponse(BaseModel):
    """Response to n8n with action to take"""
    response_message: str
    conversation_stage: str
    meeting_datetime: Optional[str] = None
    meeting_confirmed: bool = False
    should_send_message: bool
    reasoning: str
    processing_time_ms: float


class ExtractShortNameRequest(BaseModel):
    full_name: str = Field(..., description="Nome completo da clínica (Google Maps / CRM)")


class ExtractShortNameResponse(BaseModel):
    short_name: str = Field(..., description="Nome curto e natural da clínica")
    original_name: str = Field(..., description="Nome original recebido")


# ============================================================================
# LOGGING HELPERS
# ============================================================================

async def _log_gk(payload: dict) -> None:
    """Fire-and-forget: insere uma linha em gk_logs via Supabase REST API."""
    try:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_key:
            return
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.supabase_url}/rest/v1/gk_logs",
                headers={
                    "apikey": settings.supabase_key,
                    "Authorization": f"Bearer {settings.supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=payload,
            )
    except Exception as e:
        print(f"[gk_log] falhou (não crítico): {e}")


# ============================================================================
# STARTUP EVENT
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Inicializa o DSPy com as chaves do .env na subida do servidor."""
    print("🚀 EasyScale Clinic API starting...")
    try:
        init_dspy()
        print("✅ DSPy Motor initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing DSPy: {e}")

# ============================================================================
# ENDPOINTS
# ============================================================================

DEPLOY_COMMIT = "52ad414"

@app.get("/v1/health")
async def health():
    return {"status": "online", "commit": DEPLOY_COMMIT, "timestamp": datetime.utcnow()}


@app.post("/v1/utils/extract-short-name", response_model=ExtractShortNameResponse)
async def extract_short_name_endpoint(request: ExtractShortNameRequest):
    """
    Extrai o nome curto e natural de uma clínica a partir do nome completo do Google Maps.

    Chamado pelo greeting workflow antes de enviar a saudação, para evitar que o bot
    use nomes com keywords de SEO como "Dentista 24 horas - Clínica SoRio emergência
    dentista de Duque de Caxias" em vez de simplesmente "Clínica SoRio".
    """
    start_time = time.time()
    try:
        short = extract_short_name(request.full_name)
        return ExtractShortNameResponse(
            short_name=short,
            original_name=request.full_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Name extraction error: {str(e)}"
        )

@app.post("/v1/router", response_model=RouterResponse)
async def route_message(request: RouterRequest):
    """
    Endpoint para classificar intenções de mensagens de pacientes.

    Identifica quais agentes especializados devem ser ativados:
    - SERVICE_SCHEDULING: Agendamento
    - PROCEDURE_INQUIRY: Dúvidas sobre procedimentos
    - INTAKE: Coleta de informações médicas
    - HUMAN_ESCALATION: Escalar para humano
    - etc.
    """
    start_time = time.time()
    try:
        result = router_graph.invoke({
            "latest_incoming": request.latest_incoming,
            "history": request.history,
            "intake_status": request.intake_status,
            "schedule_status": request.schedule_status,
            "reschedule_status": request.reschedule_status,
            "cancel_status": request.cancel_status,
            "language": request.language,
        })

        return RouterResponse(
            intentions=result.get("intentions", ["UNCLASSIFIED"]),
            reasoning=result.get("reasoning", ""),
            confidence=result.get("confidence", 0.0),
            processing_time_ms=(time.time() - start_time) * 1000
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Router Error: {str(e)}")

@app.post("/v1/reengage", response_model=ReengageResponse)
async def reengage_lead(request: ReengageRequest):
    """
    Endpoint chamado pelo n8n para leads que pararam de responder.
    """
    try:
        # Invoca o Grafo de Re-engajamento (com loop de crítica)
        result = reengage_graph.invoke({
            "lead_name": request.lead_name,
            "ad_source": request.ad_source,
            "psychographic_profile": request.psychographic_profile,
            "conversation_history": request.conversation_history,
            "revision_count": 0,
            "is_approved": False
        })

        return ReengageResponse(
            generated_copy=result.get("generated_copy", ""),
            selected_strategy=result.get("selected_strategy", ""),
            analyst_diagnosis=result.get("analyst_diagnosis", ""),
            revision_count=result.get("revision_count", 0),
            critic_feedback=result.get("critic_feedback", "")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reengage Error: {str(e)}")


# ============================================================================
# SDR ENDPOINTS
# ============================================================================

@app.post("/v1/sdr/gatekeeper", response_model=GatekeeperResponse)
async def sdr_gatekeeper(request: GatekeeperRequest):
    """
    Endpoint para o fluxo Gatekeeper (coletar contato do gestor).

    Chamado pelo n8n quando:
    1. Inicia prospecção de uma nova clínica (conversation_history vazio)
    2. Recebe resposta da recepção (latest_message preenchido)

    Retorna ação para o n8n executar:
    - response_message: mensagem para enviar via Z-API
    - should_send_message: se deve enviar
    - extracted_manager_contact: telefone do gestor se conseguiu
    """
    start_time = time.time()
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    current_hour    = request.current_hour    if request.current_hour    is not None else now.hour
    current_weekday = request.current_weekday if request.current_weekday is not None else now.weekday()

    try:
        # Validação básica — clinic_name vazio faz o LLM travar
        if not request.clinic_name or not request.clinic_name.strip():
            raise HTTPException(
                status_code=422,
                detail="clinic_name não pode ser vazio. Verifique se gk_conversations.clinic_name está preenchido."
            )

        # Bloqueios determinísticos — sem chamar LLM
        if request.current_status == "opted_out":
            return GatekeeperResponse(
                response_message="",
                conversation_stage="failed",
                should_send_message=False,
                reasoning="Conversa marcada como opted_out — silenciando.",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        latest = request.latest_message or ""
        opt_out_words = ["sim", "não quero", "nao quero", "encerrar", "encerra", "para", "pare", "stop", "não", "nao"]
        if request.current_status == "pending_optout" and any(
            latest.lower().strip() == w or latest.lower().strip().startswith(w + " ") or latest.lower().strip().endswith(" " + w)
            for w in opt_out_words
        ):
            return GatekeeperResponse(
                response_message="",
                conversation_stage="opted_out",
                should_send_message=False,
                reasoning="Opt-out confirmado pelo contato.",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        result = gatekeeper_graph.invoke({
            "clinic_name": request.clinic_name,
            "sdr_name": request.sdr_name,
            "conversation_history": [
                {k: v for k, v in {"role": t.role, "content": t.content, "stage": getattr(t, "stage", None)}.items() if v is not None}
                for t in request.conversation_history
            ],
            "latest_message": request.latest_message,
            "current_hour": current_hour,
            "current_weekday": current_weekday,
            "detected_persona": request.detected_persona,
            "persona_confidence": request.persona_confidence,
        })

        processing_time_ms = (time.time() - start_time) * 1000

        # Log assíncrono — não bloqueia a resposta
        asyncio.create_task(_log_gk({
            "remote_jid": request.clinic_phone,
            "clinic_name": request.clinic_name,
            "is_homolog": request.is_homolog,
            "detected_persona_in": request.detected_persona,
            "persona_confidence_in": request.persona_confidence,
            "latest_message": request.latest_message,
            "node_executed": result.get("_node_executed"),
            "detected_persona_out": result.get("detected_persona"),
            "persona_confidence_out": result.get("persona_confidence"),
            "conversation_stage": result.get("conversation_stage", "opening"),
            "should_send_message": result.get("should_send_message", False),
            "response_message": result.get("response_message", ""),
            "extracted_manager_contact": result.get("extracted_manager_contact"),
            "extracted_manager_email": result.get("extracted_manager_email"),
            "extracted_manager_name": result.get("extracted_manager_name"),
            "reasoning": result.get("reasoning", ""),
            "approach_used": result.get("approach_used"),
            "attempt_count": result.get("attempt_count", 0),
            "processing_time_ms": processing_time_ms,
        }))

        return GatekeeperResponse(
            response_message=result.get("response_message", ""),
            conversation_stage=result.get("conversation_stage", "opening"),
            extracted_manager_contact=result.get("extracted_manager_contact"),
            extracted_manager_email=result.get("extracted_manager_email"),
            extracted_manager_name=result.get("extracted_manager_name"),
            should_send_message=result.get("should_send_message", False),
            reasoning=result.get("reasoning", ""),
            processing_time_ms=processing_time_ms,
            detected_persona=result.get("detected_persona"),
            persona_confidence=result.get("persona_confidence"),
            approach_used=result.get("approach_used"),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gatekeeper Error: {str(e)}"
        )


@app.post("/v1/sdr/vera", response_model=GatekeeperResponse)
async def sdr_vera(request: GatekeeperRequest):
    """
    Endpoint Vera — mesma interface do Gatekeeper DSPy, mas chamada direta ao LLM.
    Sem DSPy, sem LangGraph. Provider/modelo lidos do DSPY_PROVIDER e DSPY_MODEL do .env.
    """
    import json
    import re
    from openai import OpenAI

    start_time = time.time()
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    current_hour    = request.current_hour    if request.current_hour    is not None else now.hour
    current_weekday = request.current_weekday if request.current_weekday is not None else now.weekday()

    if not request.clinic_name or not request.clinic_name.strip():
        raise HTTPException(status_code=422, detail="clinic_name não pode ser vazio.")

    if request.current_status == "opted_out":
        return GatekeeperResponse(
            response_message="",
            conversation_stage="failed",
            should_send_message=False,
            reasoning="Conversa marcada como opted_out — silenciando.",
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    settings = get_settings()

    system_prompt = f"""Você é {request.sdr_name}, uma SDR mulher da EasyScale conversando via WhatsApp com a recepção de uma clínica.
Sempre se refira a si mesma no feminino (ex: "estou", "sou eu", nunca "fui eu o responsável").

SEU ÚNICO OBJETIVO: Obter o contato direto (WhatsApp pessoal ou email) do gestor ou dono da clínica.

Leia o histórico completo para se situar na conversa antes de responder.

---

## ANTES DE RESPONDER, SEMPRE ANALISE:

1. **Avalie a Recepcionista**
   - Tom informal → seja leve e próxima
   - Tom formal → seja executiva e direta
   - Ríspida ou apressada → elegante, breve, sem tentar criar conexão forçada
   - Gentil e receptiva → use o nome dela, crie conexão natural

2. **Mapeie o Estado da Conversa**
   - INÍCIO: primeiro contato, nenhuma tentativa feita
   - EM PROGRESSO: pedido feito, sem contato obtido ainda
   - RESISTÊNCIA: motivo questionado — veja quantas vezes no histórico
   - COOPERAÇÃO: recepcionista sinalizou que vai buscar ou transferir
   - ENCERRAMENTO: contato obtido ou recusa clara

3. **Escolha a Ação**
   Com base nos pontos acima, decida o que uma SDR humana experiente faria agora.
   Não siga script — leia a situação.

---

## COMPORTAMENTO E TOM

Você é uma autoridade gentil. Não é vendedora — é alguém que identificou algo relevante e precisa falar com quem decide.

- Máximo 2 frases curtas por mensagem — como numa conversa de WhatsApp real
- Tom humano e natural, não telegráfico — seco demais afasta
- Espelhe o tom da recepcionista: informal com quem é informal, direto com quem é formal
- Nunca repete o mesmo pedido com as mesmas palavras — se não funcionou, mude o ângulo
- Nunca menciona que é IA. Se perguntarem empresa: "EasyScale"
- Proibido: "soluções", "parceria", "apresentar nossa empresa"
- Proibido revelar o produto cedo — curiosidade é sua maior aliada
- Usa o nome da recepcionista quando souber — mas apenas UMA VEZ por turno

PONTUAÇÃO PROIBIDA:
Travessão (—): nunca use. Substitua por ponto ou vírgula.

FRASES PROIBIDAS:
"Você poderia me passar o WhatsApp ou email?"
"Você consegue me passar o WhatsApp ou email direto?"
"Poderia me fornecer o contato direto?"

FRASES CORRETAS para pedir contato:
"Consegue o contato dele?"
"Tem o WhatsApp dele?"
"Como chego nele diretamente?"

---

## TÁTICAS DISPONÍVEIS

Use cada tática no máximo UMA VEZ por conversa. Consulte o histórico para não repetir.

- direct: primeiro contato, contexto neutro. Ex: "Queria falar com o responsável da clínica. Quem seria?"
- ltv_hook: clínica focada em novos pacientes. Ex: "Com quem falo sobre resultado com pacientes que já têm?"
- leak_fix: clínica sobrecarregada. Ex: "Notei uma fuga de agendamentos aqui. Preciso falar com o gestor."
- social_proof: tom neutro. Ex: "Estou reduzindo no-show em clínicas da região. Com quem falo?"
- data_hook: boas avaliações online. Ex: "Vi algo no Google de vocês que o dono precisa saber. Quem seria?"

Nota: ltv_hook e leak_fix revelam intenção. Use como resposta à resistência, não como abertura.

---

## LIDANDO COM RESISTÊNCIA

1a vez que pedir motivo: "Assunto comercial pro gestor."
2a vez: "É sobre conversão dos leads que já chegam pelos anúncios. Algo que ele vai querer ver."
3a vez: mude de tática (ltv_hook, leak_fix ou social_proof, a que ainda não usou).

---

## REGRA DO EMAIL GENÉRICO

Se oferecerem email genérico (contato@, recepcao@, comercial@):
"Obrigada! Mas esse o time já acessa. Precisava do contato direto de quem decide sobre agenda e faturamento. Consegue o email pessoal ou WhatsApp?"

---

## SINAIS DE COOPERAÇÃO

"Um momento" / "vou chamar": aguarde em silêncio (should_continue=false)
"Vou encaminhar pro gestor": agradeça e aguarde
"Pode falar comigo": trate como o próprio gestor, mude o tom
"A gestora acompanha esse WhatsApp": este canal É o contato, success imediato

---

## CONTATO VÁLIDO

- Número de WhatsApp pessoal (8 ou mais dígitos): success
- Email pessoal com @ (não genérico): success
- vCard compartilhado: success imediato
- Confirmação de que o gestor está neste mesmo WhatsApp: success

Ao receber contato: agradeça e encerre imediatamente.

---

## ENCERRAMENTO SEM SUCESSO

"Entendido! Fica o contato caso precisem. Bom dia!"

Silêncio total (waiting): not_continue=false, response_message=null

---

## PERSONAS

receptionist / unknown: fluxo normal
manager: fale de negócio direto, sem intermediários
waiting: silêncio (should_continue=false, response_message=null)
ai_assistant: peça uma vez para falar com humano. Se não transferir, failed
call_center: tente uma vez chegar direto na clínica. Se não der, failed
menu_bot: não há humano disponível, failed

---

Hora atual: {current_hour}h | Dia da semana: {current_weekday} (0=segunda)
Persona detectada: {request.detected_persona or 'unknown'}

Responda APENAS com JSON válido, sem markdown, sem texto antes ou depois:
{{
  "reasoning": "leitura da situação e decisão",
  "response_message": "mensagem a enviar ou null se waiting",
  "conversation_stage": "requesting|handling_objection|success|failed",
  "extracted_contact": null,
  "extracted_email": null,
  "extracted_name": null,
  "should_continue": true,
  "approach_used": "direct|ltv_hook|leak_fix|social_proof|data_hook|close|silence"
}}"""

    history_str = json.dumps([
        {"role": t.role, "content": t.content, "stage": getattr(t, "stage", None)}
        for t in request.conversation_history
    ], ensure_ascii=False)

    user_message = f"""Clínica: {request.clinic_name}
Histórico: {history_str}
Última mensagem: {request.latest_message or 'PRIMEIRA_MENSAGEM'}"""

    # Monta cliente OpenAI-compatible com base no DSPY_PROVIDER do .env
    _provider_clients = {
        "anthropic": lambda s: OpenAI(
            api_key=s.anthropic_api_key,
            base_url="https://api.anthropic.com/v1",
        ),
        "openai": lambda s: OpenAI(api_key=s.openai_api_key),
        "glm": lambda s: OpenAI(
            api_key=s.glm_api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        ),
        "groq": lambda s: OpenAI(
            api_key=s.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        ),
        "xai": lambda s: OpenAI(
            api_key=s.xai_api_key,
            base_url="https://api.x.ai/v1",
        ),
    }

    try:
        provider = settings.dspy_provider
        client_factory = _provider_clients.get(provider)
        if not client_factory:
            raise ValueError(f"Provider '{provider}' não suportado na Vera. Use: {list(_provider_clients.keys())}")
        client = client_factory(settings)

        completion = client.chat.completions.create(
            model=settings.dspy_model,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        raw = completion.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)

        extracted_contact = data.get("extracted_contact")
        extracted_email   = data.get("extracted_email")
        extracted_name    = data.get("extracted_name")
        should_continue   = data.get("should_continue", True)
        response_message  = data.get("response_message") or ""
        stage             = data.get("conversation_stage", "requesting")

        if not response_message or str(response_message).lower() == "null":
            should_continue  = False
            response_message = ""

        if extracted_contact and isinstance(extracted_contact, str):
            digits = re.sub(r"\D", "", extracted_contact)
            extracted_contact = digits if len(digits) >= 10 else None
        else:
            extracted_contact = None

        if extracted_email and isinstance(extracted_email, str):
            e = extracted_email.strip().lower()
            extracted_email = e if re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) else None
        else:
            extracted_email = None

        if extracted_contact and stage not in ["success", "failed"]:
            stage = "success"
        if extracted_email and not extracted_contact and stage not in ["success", "failed"]:
            stage = "success"

        processing_time_ms = (time.time() - start_time) * 1000

        asyncio.create_task(_log_gk({
            "remote_jid":               request.clinic_phone,
            "clinic_name":              request.clinic_name,
            "is_homolog":               request.is_homolog,
            "detected_persona_in":      request.detected_persona,
            "latest_message":           request.latest_message,
            "node_executed":            "vera_direct",
            "conversation_stage":       stage,
            "should_send_message":      should_continue,
            "response_message":         response_message,
            "extracted_manager_contact": extracted_contact,
            "extracted_manager_email":  extracted_email,
            "extracted_manager_name":   extracted_name if isinstance(extracted_name, str) else None,
            "reasoning":                data.get("reasoning", ""),
            "approach_used":            data.get("approach_used"),
            "processing_time_ms":       processing_time_ms,
        }))

        return GatekeeperResponse(
            response_message=response_message,
            conversation_stage=stage,
            extracted_manager_contact=extracted_contact,
            extracted_manager_email=extracted_email,
            extracted_manager_name=extracted_name if isinstance(extracted_name, str) else None,
            should_send_message=should_continue,
            reasoning=data.get("reasoning", ""),
            processing_time_ms=processing_time_ms,
            detected_persona=request.detected_persona,
            persona_confidence=request.persona_confidence,
            approach_used=data.get("approach_used"),
        )

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Vera JSON inválido: {e} | Raw: {raw[:300]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vera Error: {str(e)}")


@app.post("/v1/sdr/closer", response_model=CloserResponse)
async def sdr_closer(request: CloserRequest):
    """
    Endpoint para o fluxo Closer (agendar reunião com gestor).

    Chamado pelo n8n quando:
    1. Inicia contato com o gestor (conversation_history vazio)
    2. Recebe resposta do gestor (latest_message preenchido)

    Retorna ação para o n8n executar:
    - response_message: mensagem para enviar via Z-API
    - should_send_message: se deve enviar
    - meeting_datetime: ISO datetime se reunião foi confirmada
    - meeting_confirmed: true se deve criar evento no Google Calendar
    """
    start_time = time.time()
    current_hour = datetime.now(ZoneInfo("America/Sao_Paulo")).hour

    try:
        # Count agent messages in history
        attempt_count = len([
            t for t in request.conversation_history
            if t.role == "agent"
        ])

        result = closer_graph.invoke({
            "manager_name": request.manager_name,
            "manager_phone": request.manager_phone,
            "clinic_name": request.clinic_name,
            "clinic_specialty": request.clinic_specialty,
            "conversation_history": [
                {"role": t.role, "content": t.content}
                for t in request.conversation_history
            ],
            "latest_message": request.latest_message,
            "available_slots": request.available_slots,
            "current_hour": current_hour,
            "attempt_count": attempt_count,
        })

        return CloserResponse(
            response_message=result.get("response_message", ""),
            conversation_stage=result.get("conversation_stage", "greeting"),
            meeting_datetime=result.get("meeting_datetime"),
            meeting_confirmed=result.get("meeting_confirmed", False),
            should_send_message=result.get("should_send_message", False),
            reasoning=result.get("reasoning", ""),
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Closer Error: {str(e)}"
        )


# ============================================================================
# SERVER RUNNER
# ============================================================================

#if __name__ == "__main__":
#    import uvicorn
#    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
# Substitua as últimas linhas por isso:
#ENV PYTHONPATH=.
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]