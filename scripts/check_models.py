"""Diagnostic: show which LLM providers are configured for this environment.

Replaces the previous Gemini-only model lister. Reports which provider chain
entries have credentials and what model each will use.
"""

import sys
from pathlib import Path

# Allow running this script directly from the repo root.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from dotenv import load_dotenv

from src import llm_client

load_dotenv()


def main() -> int:
    if not llm_client.reinit():
        print(
            "No LLM providers configured. Set at least one of:\n"
            "  CEREBRAS_API_KEY  (recommended)\n"
            "  GROQ_API_KEY\n"
            "  OPENROUTER_API_KEY"
        )
        return 1

    active = llm_client.active_providers()
    print("Configured LLM provider chain (tried in order):")
    for idx, name in enumerate(active, 1):
        provider = next(
            (p for p in llm_client._PROVIDERS if p.name == name), None
        )
        if provider:
            print(f"  {idx}. {provider.name:<10}  model={provider.model}  base_url={provider.base_url}")
        else:
            print(f"  {idx}. {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
