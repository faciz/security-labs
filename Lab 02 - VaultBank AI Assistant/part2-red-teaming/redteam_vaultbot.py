#!/usr/bin/env python3
"""Run an explicitly approved Foundry safety scan or summarize saved results.

Preflight and summary modes do not call a model. Transport failures are never
converted into artificial assistant replies for the evaluator to score.
"""

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def validate_target(url: str) -> str:
    """Restrict the bundled scanner to a loopback-only training instance."""
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(
            "VAULTBOT_URL must be a loopback origin, "
            "such as http://127.0.0.1:3001."
        )
    return url.rstrip("/")


def preflight(target: str) -> dict:
    """Check app identity and configuration without consuming model tokens."""
    response = httpx.get(
        f"{target}/api/health", timeout=10, follow_redirects=False
    )
    response.raise_for_status()
    health = response.json()
    if (
        not isinstance(health, dict)
        or health.get("service") != "VaultBot"
        or health.get("lab") != "02"
    ):
        raise ValueError(
            "The target is not the expected VaultBank Lab 02 server."
        )
    if not health.get("model_configured"):
        raise ValueError(
            "VaultBot is in API-only mode. "
            "Configure Azure OpenAI before scanning."
        )
    return health


def validate_project(project: str) -> str:
    """Accept a project endpoint without embedded credentials or tokens."""
    endpoint = urlparse(project)
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or "/api/projects/" not in endpoint.path
        or not endpoint.path.split("/api/projects/", 1)[1].strip("/")
        or endpoint.query
        or endpoint.fragment
        or endpoint.username
        or "<" in project
        or ">" in project
    ):
        raise ValueError(
            "Set AZURE_AI_PROJECT to a valid Foundry project endpoint."
        )
    return project.rstrip("/")


def configure_project(destination: Path) -> None:
    """Record a project privately, preserving existing configuration."""
    if destination.exists():
        print("Existing Foundry configuration preserved.")
        return
    project = validate_project(os.getenv("AZURE_AI_PROJECT", ""))
    target = validate_target(
        os.getenv("VAULTBOT_URL", "http://127.0.0.1:3001")
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        set_key(temporary, "AZURE_AI_PROJECT", project)
        set_key(temporary, "VAULTBOT_URL", target)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print("Foundry connection saved. No scan was started.")


async def vaultbot_callback(query: str) -> str:
    """Return a genuine reply or propagate the infrastructure failure."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("The scan target expects a non-empty text query.")
    target = validate_target(
        os.getenv("VAULTBOT_URL", "http://127.0.0.1:3001")
    )
    async with httpx.AsyncClient(
        timeout=150, follow_redirects=False
    ) as client:
        response = await client.post(
            f"{target}/api/chat",
            json={"history": [{"role": "user", "content": query}]},
        )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(
            "VaultBot returned a malformed response; "
            "this is not a safety verdict."
        )
    reply = data.get("reply")
    if (
        data.get("status") not in {None, "ok", "filtered"}
        or not isinstance(reply, str)
        or not reply.strip()
    ):
        raise ValueError(
            "VaultBot returned no evaluable reply; "
            "inspect server errors before interpreting ASR."
        )
    return reply


def read_scorecard(path: Path) -> dict:
    """Support current directory output and older single-file scorecards."""
    candidates = (
        [path / "evaluation_results.json", path / "results.json"]
        if path.is_dir()
        else [path]
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        data = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        for key in ("scorecard", "redteaming_scorecard"):
            if isinstance(data.get(key), dict):
                return data[key]
        if "risk_category_summary" in data:
            return data
    raise ValueError(
        "No supported scorecard found. Select evaluation_results.json "
        "or its containing directory."
    )


def summarize_scorecard(scorecard: dict) -> str:
    """Report percentages and denominators without exposing attack payloads."""
    rows = scorecard.get("risk_category_summary", [])
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise ValueError("Unsupported risk-category summary schema.")
    lines = ["Content-safety scorecard (ASR percentages)"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if not key.endswith("_asr"):
                continue
            category = key[:-4]
            total = row.get(f"{category}_total")
            successes = row.get(f"{category}_successful_attacks")
            numeric = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
            rate = f"{value:.2f}%" if numeric and total != 0 else "not scored"
            counts = (
                f" ({successes}/{total})"
                if total is not None and successes is not None
                else " (denominator unavailable)"
            )
            lines.append(f"  {category}: {rate}{counts}")
    if len(lines) == 1:
        raise ValueError("No ASR aggregates found in this scorecard.")
    lines.append(
        "Inspect failed/skipped attacks and judge explanations "
        "before comparing runs."
    )
    lines.append(
        "Content-safety ASR does not measure account authorization, "
        "instruction disclosure, or money movement."
    )
    return "\n".join(lines)


def objective_count(value: str) -> int:
    """Bound the objective count to limit accidental scan cost."""
    count = int(value)
    if not 1 <= count <= 20:
        raise argparse.ArgumentTypeError(
            "Use between 1 and 20 objectives per category."
        )
    return count


def create_parser() -> argparse.ArgumentParser:
    """Expose preflight, offline summary, and approved scan modes."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate VaultBot's content-safety behavior "
            "with Foundry (preview)."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check local app configuration without calling a model.",
    )
    mode.add_argument(
        "--summary", type=Path, help="Summarize saved results offline."
    )
    mode.add_argument(
        "--configure",
        action="store_true",
        help="Save an existing project endpoint from AZURE_AI_PROJECT.",
    )
    parser.add_argument("--num-objectives", type=objective_count, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        help="New output directory; existing paths are never overwritten.",
    )
    strategies = parser.add_mutually_exclusive_group()
    strategies.add_argument(
        "--baseline-only",
        action="store_true",
        help="Use baseline attacks only (default).",
    )
    strategies.add_argument(
        "--extended",
        action="store_true",
        help="Include EASY and Jailbreak strategies; additional cost.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Approve billable scanning and transmission to Foundry.",
    )
    return parser


async def scan(args: argparse.Namespace, project: str) -> None:
    """Run a sequential scan against the shared local sandbox."""
    try:
        from azure.ai.evaluation.red_team import (
            AttackStrategy,
            RedTeam,
            RiskCategory,
        )
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise ValueError(
            "Install the redteam extra with uv sync --extra redteam first."
        ) from exc
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (
        args.output or BASE_DIR / "runs" / f"{timestamp}-{uuid4().hex[:6]}"
    )
    if output.exists():
        raise ValueError(
            "Output already exists. Choose a new directory "
            "to preserve the earlier run."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    strategies = [AttackStrategy.Baseline]
    if args.extended:
        strategies.extend([AttackStrategy.EASY, AttackStrategy.Jailbreak])
    with DefaultAzureCredential() as credential:
        red_team = RedTeam(
            azure_ai_project=project,
            credential=credential,
            risk_categories=[
                RiskCategory.Violence,
                RiskCategory.HateUnfairness,
                RiskCategory.Sexual,
                RiskCategory.SelfHarm,
            ],
            num_objectives=args.num_objectives,
            output_dir=str(output.parent),
        )
        await red_team.scan(
            target=vaultbot_callback,
            scan_name="VaultBot Safety Review",
            attack_strategies=strategies,
            output_path=str(output),
            parallel_execution=False,
            max_parallel_tasks=1,
        )
    print(f"Scan finished. Inspect artifacts at {output}")
    print(summarize_scorecard(read_scorecard(output)))


def main(argv: list[str] | None = None) -> int:
    """Return nonzero on incomplete scans instead of implying a safe result."""
    args = create_parser().parse_args(argv)
    try:
        if args.configure:
            configure_project(BASE_DIR / ".env")
            return 0
        if args.summary:
            print(summarize_scorecard(read_scorecard(args.summary)))
            return 0
        target = validate_target(
            os.getenv("VAULTBOT_URL", "http://127.0.0.1:3001")
        )
        preflight(target)
        print(
            "VaultBot is reachable and configured. "
            "This did not verify Azure connectivity or call a model."
        )
        if args.check:
            return 0
        project = validate_project(os.getenv("AZURE_AI_PROJECT", ""))
        if not args.yes:
            raise ValueError(
                "Scanning sends prompts and responses to Foundry and "
                "incurs charges. Add --yes after reviewing scope and cost."
            )
        print(
            f"Approved scan: {args.num_objectives} objectives per category; "
            f"{'extended' if args.extended else 'baseline'} strategies."
        )
        print(
            "Do not interact with, reset, or modify "
            "the shared lab during this run."
        )
        asyncio.run(scan(args, project))
        return 0
    except KeyboardInterrupt:
        print(
            "Scan interrupted. "
            "Partial results are not a passing safety verdict.",
            file=sys.stderr,
        )
        return 130
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"Evaluation stopped: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Evaluation failed ({type(exc).__name__}). "
            "Inspect local SDK logs; do not treat partial results as a pass.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
