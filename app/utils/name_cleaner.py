"""
Clinic Name Cleaner - DSPy module for extracting natural short names.

Problem: clinic names from Google Maps contain SEO keywords, making the
greeting sound robotic ("Dentista 24 horas - Clínica SoRio emergência
dentista de Duque de Caxias" → should be "Clínica SoRio").
"""

import dspy


class ExtractShortNameSignature(dspy.Signature):
    """
    Você recebe o nome completo de uma clínica como aparece no Google Maps.
    Esse nome geralmente contém palavras de SEO, localização, especialidade, etc.

    Sua tarefa: extrair apenas o NOME CURTO E NATURAL que as pessoas da
    clínica usam no dia a dia — o nome que a recepcionista reconheceria
    imediatamente quando alguém ligar.

    === REGRAS ===

    ✅ PRESERVE:
    - Nome próprio da clínica (ex: "SoRio", "Odonto Sorriso", "Bella Forma")
    - Prefixo de tipo quando faz parte do nome ("Clínica X", "Instituto Y", "Centro Z")
    - Sobrenome do dono quando é o nome da clínica ("Clínica Dr. Santos")

    ❌ REMOVA:
    - Palavras de SEO/especialidade no início ou fim:
      "dentista", "odontologia", "estética", "dermatologia", "pilates", etc.
    - Sufixos de localização: "de São Paulo", "do Rio", "de Duque de Caxias", etc.
    - Sufixos de horário: "24 horas", "24h", "plantão", etc.
    - Separadores com o que vem antes: "Dentista 24 horas - [NOME]" → "[NOME]"
    - Palavras genéricas redundantes: "clínica de estética", "consultório odontológico"

    === EXEMPLOS ===

    "Dentista 24 horas - Clínica SoRio emergência dentista de Duque de Caxias"
    → "Clínica SoRio"

    "Odonto Sorriso - Clínica Odontológica em São Paulo"
    → "Odonto Sorriso"

    "Clínica de Estética Bella Forma - Procedimentos Estéticos RJ"
    → "Bella Forma"

    "Instituto de Fisioterapia e Pilates Movimento Pleno Campinas"
    → "Movimento Pleno"

    "Dr. Carlos Mendes - Ortodontia e Implantes"
    → "Dr. Carlos Mendes"

    "Clínica Saúde Total"
    → "Clínica Saúde Total"

    "Studio Corpo e Alma - Estética Avançada - Botafogo Rio de Janeiro"
    → "Studio Corpo e Alma"

    === REGRA FINAL ===
    Se o nome for curto e já natural (≤ 4 palavras, sem SEO óbvio), retorne-o como está.
    Nunca invente um nome que não esteja no original.
    """

    full_name: str = dspy.InputField(
        desc="Nome completo da clínica como aparece no Google Maps"
    )
    short_name: str = dspy.OutputField(
        desc="Nome curto e natural da clínica (ex: 'Clínica SoRio'). Apenas o nome, sem explicações."
    )


class ClinicNameCleaner(dspy.Module):
    """Extrai o nome curto e natural de uma clínica a partir do nome completo do Google Maps."""

    def __init__(self):
        super().__init__()
        self.extract = dspy.Predict(ExtractShortNameSignature)

    def forward(self, full_name: str) -> str:
        """
        Returns the short name for the clinic.
        Falls back to the original name if extraction fails or returns empty.
        """
        if not full_name or not full_name.strip():
            return full_name

        try:
            result = self.extract(full_name=full_name.strip())
            short = (result.short_name or "").strip()

            # Sanity check: short name must be non-empty and ≤ original length
            if short and len(short) <= len(full_name):
                return short
        except Exception:
            pass

        return full_name  # fallback: original name is always safe


# Singleton instance (reused across requests)
_cleaner: ClinicNameCleaner | None = None


def get_cleaner() -> ClinicNameCleaner:
    global _cleaner
    if _cleaner is None:
        _cleaner = ClinicNameCleaner()
    return _cleaner


def extract_short_name(full_name: str) -> str:
    """Module-level convenience function."""
    return get_cleaner().forward(full_name)
