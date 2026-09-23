#!/usr/bin/env python3
"""Point Azure AI Foundry's AI Red Teaming Agent (preview) at VaultBot.

Instead of hand-crafting jailbreaks, we let PyRIT-backed automation generate
adversarial prompts, fire them at VaultBot's /api/chat endpoint, and score the
replies. The result is an Attack Success Rate (ASR) scorecard.
"""

import argparse
import asyncio
import os

import requests
from azure.identity import DefaultAzureCredential
from azure.ai.evaluation.red_team import AttackStrategy, RedTeam, RiskCategory

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

VAULTBOT_URL = os.environ.get("VAULTBOT_URL", "http://localhost:3000").rstrip("/")
AZURE_AI_PROJECT = os.environ.get("AZURE_AI_PROJECT")


def vaultbot_callback(query: str) -> str:
    """Send one adversarial prompt to VaultBot and return its reply."""
    try:
        resp = requests.post(
            f"{VAULTBOT_URL}/api/chat",
            json={"history": [{"role": "user", "content": query}]},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("reply", "")
    except requests.RequestException as exc:
        return f"[vaultbot unreachable: {exc}]"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Red-team VaultBot with the AI Red Teaming Agent.")
    parser.add_argument("--num-objectives", type=int, default=3,
                        help="Attack prompts generated per risk category (default: 3).")
    parser.add_argument("--output", default="vaultbot_redteam_scorecard.json",
                        help="Where to write the JSON scorecard.")
    parser.add_argument("--baseline-only", action="store_true",
                        help="Run only baseline direct attacks (fastest / cheapest).")
    args = parser.parse_args()

    if not AZURE_AI_PROJECT:
        raise SystemExit("Set AZURE_AI_PROJECT (see .env.example). Run ./part2_setup.sh first.")

    # Fail fast if VaultBot (Part 1) is not running.
    if vaultbot_callback("hello").startswith("[vaultbot unreachable"):
        raise SystemExit(
            f"VaultBot is not reachable at {VAULTBOT_URL}. "
            "Start Part 1 first (cd ../vaultbot && ./run.sh)."
        )

    red_team = RedTeam(
        azure_ai_project=AZURE_AI_PROJECT,
        credential=DefaultAzureCredential(),
        risk_categories=[
            RiskCategory.Violence,
            RiskCategory.HateUnfairness,
            RiskCategory.Sexual,
            RiskCategory.SelfHarm,
        ],
        num_objectives=args.num_objectives,
    )

    attack_strategies = None if args.baseline_only else [
        AttackStrategy.EASY,       # Base64, Flip, Morse
        AttackStrategy.Jailbreak,  # UPIA prompt injection
    ]

    print(f"Scanning VaultBot at {VAULTBOT_URL} (this calls the model many times) ...")
    await red_team.scan(
        target=vaultbot_callback,
        scan_name="VaultBot Red Team",
        attack_strategies=attack_strategies,
        output_path=args.output,
    )

    print(f"\nScan complete. Scorecard written to {args.output}")
    print("View the run in your Foundry project at https://ai.azure.com")


if __name__ == "__main__":
    asyncio.run(main())
