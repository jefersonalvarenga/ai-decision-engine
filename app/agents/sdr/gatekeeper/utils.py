"""
Gatekeeper utilities — shared helpers for safe attribute access.
"""


def safe_str(val, default: str = "") -> str:
    """
    Safely convert any DSPy output field to string.
    GLM-5 occasionally returns non-string types (int, list, None)
    for fields declared as str in the DSPy Signature.
    """
    if val is None:
        return default
    if isinstance(val, str):
        return val
    return str(val)
