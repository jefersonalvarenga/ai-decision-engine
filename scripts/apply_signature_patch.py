"""
apply_signature_patch.py — Aplica o patch JSON gerado pelo analyze_eval_report.py na signature.

Lê signature_patch.json (produzido por analyze_eval_report.py --patch-output),
substitui a docstring da GatekeeperSignature e grava signature.py atualizado.

Uso:
    python scripts/apply_signature_patch.py \
        --patch signature_patch.json \
        --target app/agents/sdr/gatekeeper/signature.py

Saída:
    Exit 0 → mudanças aplicadas (signature.py foi modificado)
    Exit 1 → erro irrecuperável
    Exit 2 → nada para aplicar (patch inválido ou score já ok)
"""

import re
import sys
import json
import argparse


# ============================================================================
# APPLY
# ============================================================================

def apply(patch_path: str, target_path: str) -> int:
    """Aplica o patch. Retorna 0 se aplicou, 2 se não havia o que aplicar."""

    with open(patch_path, encoding="utf-8") as f:
        patch = json.load(f)

    new_docstring = patch.get("new_docstring", "").strip()
    rationale = patch.get("rationale", "—")
    low_scenarios = patch.get("low_scenarios", [])
    avg_score = patch.get("avg_score", "?")

    if not new_docstring:
        print("⚠️  Patch vazio (new_docstring ausente). Nada a aplicar.", file=sys.stderr)
        return 2

    # Garante que o docstring está envolvido em triple-quotes
    if not new_docstring.startswith('"""'):
        new_docstring = '"""' + new_docstring
    if not new_docstring.endswith('"""'):
        new_docstring = new_docstring + '"""'

    with open(target_path, encoding="utf-8") as f:
        original = f.read()

    # Substituir a docstring da classe GatekeeperSignature
    # Padrão: class GatekeeperSignature(dspy.Signature):\n    """..."""
    pattern = re.compile(
        r'(class GatekeeperSignature\(dspy\.Signature\):)\s*("""[\s\S]*?""")',
        re.DOTALL,
    )
    match = pattern.search(original)

    if not match:
        print(
            "❌ Não encontrei 'class GatekeeperSignature(dspy.Signature):' + docstring "
            f"em {target_path}",
            file=sys.stderr,
        )
        return 1

    old_docstring = match.group(2)
    # Indenta o novo docstring com 4 espaços (padrão de classe Python)
    indented = "\n".join(
        ("    " + line if line.strip() else line)
        for line in new_docstring.splitlines()
    )

    new_content = original.replace(
        match.group(0),
        f"{match.group(1)}\n{indented}",
        1,
    )

    if new_content == original:
        print("ℹ️  Patch aplicado mas nenhuma mudança detectada (conteúdo idêntico).")
        return 2

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Patch aplicado em: {target_path}")
    print(f"   Score anterior: {avg_score}")
    print(f"   Cenários corrigidos: {', '.join(low_scenarios)}")
    print(f"   Rationale: {rationale}")
    print(f"   Docstring: {len(old_docstring)} → {len(new_docstring)} chars")
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica patch JSON na docstring da GatekeeperSignature"
    )
    parser.add_argument(
        "--patch", default="signature_patch.json",
        help="Arquivo JSON com o patch (padrão: signature_patch.json)"
    )
    parser.add_argument(
        "--target", default="app/agents/sdr/gatekeeper/signature.py",
        help="Arquivo signature.py a modificar (padrão: app/agents/sdr/gatekeeper/signature.py)"
    )
    args = parser.parse_args()

    import os
    if not os.path.exists(args.patch):
        print(f"ℹ️  Arquivo de patch não encontrado: {args.patch} — nada a aplicar.")
        sys.exit(2)
    if not os.path.exists(args.target):
        print(f"❌ Target não encontrado: {args.target}", file=sys.stderr)
        sys.exit(1)

    code = apply(args.patch, args.target)
    sys.exit(code)


if __name__ == "__main__":
    main()
