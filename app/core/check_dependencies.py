#!/usr/bin/env python3
"""
Dependency Checker for EasyScale

Verifies that all required dependencies are installed and importable.
Run this before deploying to catch issues early.
"""

import sys
import importlib
from typing import List, Tuple


def check_import(module_name: str, package_name: str = None) -> Tuple[bool, str]:
    """
    Try to import a module and return status.

    Args:
        module_name: Name of module to import
        package_name: Name of package to install (if different from module)

    Returns:
        Tuple of (success: bool, message: str)
    """
    package = package_name or module_name
    try:
        importlib.import_module(module_name)
        return True, f"✅ {module_name} (from {package})"
    except ImportError as e:
        return False, f"❌ {module_name} - Missing! Install with: pip install {package}"
    except Exception as e:
        return False, f"⚠️  {module_name} - Error: {str(e)}"


def main():
    """Check all required dependencies."""

    print("=" * 70)
    print("  EasyScale Dependency Checker")
    print("=" * 70)
    print()

    # Core dependencies
    dependencies = [
        # FastAPI stack
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn[standard]"),
        ("pydantic", "pydantic"),
        ("pydantic_settings", "pydantic-settings"),

        # AI/ML
        ("dspy", "dspy-ai"),
        ("langgraph", "langgraph"),
        ("langchain", "langchain"),
        ("langchain_core", "langchain-core"),

        # LLM providers (at least one required)
        ("openai", "openai"),
        # ("anthropic", "anthropic"),  # Optional
        # ("groq", "groq"),  # Optional

        # Database
        ("supabase", "supabase"),

        # Utilities
        ("dotenv", "python-dotenv"),
        ("httpx", "httpx"),
    ]

    print("Checking dependencies...")
    print("-" * 70)

    results = []
    for module, package in dependencies:
        success, message = check_import(module, package)
        results.append((success, message))
        print(message)

    print()
    print("=" * 70)

    # Summary
    success_count = sum(1 for success, _ in results if success)
    total_count = len(results)

    if success_count == total_count:
        print(f"✅ ALL CHECKS PASSED ({success_count}/{total_count})")
        print()
        print("Your environment is ready!")
        return 0
    else:
        failed_count = total_count - success_count
        print(f"⚠️  SOME CHECKS FAILED ({failed_count} failures, {success_count} successes)")
        print()
        print("Fix missing dependencies with:")
        print("  pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
