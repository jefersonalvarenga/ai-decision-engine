"""
Utility functions for Closer agent
"""


def safe_str(val, default="") -> str:
    """Safely coerce DSPy result attributes to string.

    GLM-5 sometimes returns malformed types (dict, list) instead of str.
    This guard prevents 'str object has no attribute items' errors.
    """
    if val is None:
        return default
    if isinstance(val, str):
        return val
    return str(val)
