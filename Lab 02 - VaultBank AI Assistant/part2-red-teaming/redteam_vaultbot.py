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
import re
import sys
import tempfile
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
RISK_CATEGORIES = ("violence", "hate_unfairness", "sexual", "self_harm")
FILTER_NOTICE = "The model service's safety filter blocked this request."
RUN_OUTCOMES: ContextVar[list[dict] | None] = ContextVar(
    "run_outcomes", default=None
)
RUN_HEALTH_FILE = "run_health.json"
ERROR_CATEGORIES = {
    "upstream_timeout",
    "upstream_connection",
    "upstream_bad_request",
    "upstream_authentication",
    "upstream_permission",
    "upstream_not_found",
    "upstream_rate_limit",
    "upstream_http_error",
    "unexpected_error",
    "http_error",
    "connection_error",
    "timeout",
    "invalid_response",
}


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


def sanitized_outcome(value: dict) -> dict:
    """Allow only bounded diagnostic metadata in the run-health artifact."""
    outcome = value.get("outcome")
    if not isinstance(outcome, str) or outcome not in {
        "model_response",
        "service_filter",
        "unknown",
        "error",
    }:
        raise ValueError("Unsupported target outcome in run metadata.")
    result = {"outcome": outcome}
    for key in ("http_status", "upstream_status"):
        status = value.get(key)
        if isinstance(status, int) and not isinstance(status, bool):
            if 100 <= status <= 599:
                result[key] = status
    category = value.get("category")
    if isinstance(category, str) and category in ERROR_CATEGORIES:
        result["category"] = category
    patterns = {
        "error_id": r"[a-f0-9]{32}",
        "upstream_request_id": r"(?:req_)?[a-fA-F0-9-]{16,64}",
        "response_hash": r"[a-f0-9]{64}",
    }
    for key, pattern in patterns.items():
        identifier = value.get(key)
        if isinstance(identifier, str) and re.fullmatch(pattern, identifier):
            result[key] = identifier
    return result


async def vaultbot_callback(query: str) -> str:
    """Return a reply, retaining its provenance separately from its text."""
    outcome = {"outcome": "error", "category": "invalid_response"}
    try:
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
        outcome["http_status"] = response.status_code
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("VaultBot returned a malformed response.")
        reply = data.get("reply")
        if (
            data.get("status") not in {None, "ok", "filtered"}
            or not isinstance(reply, str)
            or not reply.strip()
        ):
            raise ValueError("VaultBot returned no evaluable reply.")
        outcome = {
            "outcome": {
                "ok": "model_response",
                "filtered": "service_filter",
            }.get(data.get("status"), "unknown"),
            "http_status": response.status_code,
            "response_hash": sha256(reply.strip().encode("utf-8")).hexdigest(),
        }
        return reply
    except httpx.HTTPStatusError as error:
        outcome["category"] = "http_error"
        try:
            payload = error.response.json()
            diagnostics = (
                payload.get("diagnostics")
                if isinstance(payload, dict)
                else None
            )
            if isinstance(diagnostics, dict):
                outcome.update(
                    {
                        key: diagnostics[key]
                        for key in (
                            "category",
                            "error_id",
                            "upstream_status",
                            "upstream_request_id",
                        )
                        if key in diagnostics
                    }
                )
        except ValueError:
            pass
        raise
    except httpx.TimeoutException:
        outcome["category"] = "timeout"
        raise
    except httpx.RequestError:
        outcome["category"] = "connection_error"
        raise
    finally:
        outcomes = RUN_OUTCOMES.get()
        if outcomes is not None:
            outcomes.append(sanitized_outcome(outcome))


async def vaultbot_target(
    messages: list[dict],
    stream: bool = False,
    session_state: str | None = None,
    context: dict | None = None,
) -> dict:
    """Use the evaluator's native async contract without wrapping failures."""
    if stream or not messages:
        raise ValueError("Use non-streaming evaluation with a user message.")
    reply = await vaultbot_callback(messages[-1]["content"])
    return {"messages": [{"role": "assistant", "content": reply}]}


def read_evaluation(path: Path) -> dict:
    """Load a scorecard with its case records when available."""
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
                return data
        if "risk_category_summary" in data:
            return data
    raise ValueError(
        "No supported scorecard found. Select evaluation_results.json "
        "or its containing directory."
    )


def extract_scorecard(data: dict) -> dict:
    """Accept both SDK scorecard containers and legacy bare scorecards."""
    return data.get("scorecard", data.get("redteaming_scorecard", data))


def read_scorecard(path: Path) -> dict:
    """Support current directory output and older single-file scorecards."""
    return extract_scorecard(read_evaluation(path))


def assess_run(
    data: dict,
    planned: dict | None = None,
    outcomes: list[dict] | None = None,
    *,
    execution_failed: bool = False,
) -> dict:
    """Reconcile coverage and sources without copying conversations."""
    if planned is not None and (
        not isinstance(planned, dict)
        or set(planned) != set(RISK_CATEGORIES)
        or any(
            type(total) is not int or total < 1 for total in planned.values()
        )
    ):
        raise ValueError("Invalid per-category plan in run metadata.")
    if outcomes is not None:
        outcomes = [sanitized_outcome(outcome) for outcome in outcomes]
    scorecard = extract_scorecard(data)
    rows = scorecard.get("risk_category_summary", [])
    if isinstance(rows, dict):
        rows = [rows]
    aggregate = {}
    for row in rows:
        if isinstance(row, dict):
            aggregate.update(row)
    details = data.get("attack_details")
    records = details if isinstance(details, list) else []
    scored = Counter()
    sources = Counter()
    provenance = {}
    for outcome in outcomes or []:
        if outcome.get("response_hash"):
            provenance.setdefault(outcome["response_hash"], set()).add(
                outcome["outcome"]
            )
    model_successes = 0
    invalid_records = 0
    for record in records:
        if (
            not isinstance(record, dict)
            or record.get("risk_category") not in RISK_CATEGORIES
            or not isinstance(record.get("attack_success"), bool)
            or not isinstance(record.get("risk_assessment"), dict)
            or not isinstance(
                record["risk_assessment"].get(record["risk_category"]), dict
            )
        ):
            invalid_records += 1
            continue
        scored[record["risk_category"]] += 1
        conversation = record.get("conversation")
        reply = next(
            (
                message.get("content", "")
                for message in reversed(
                    conversation if isinstance(conversation, list) else []
                )
                if isinstance(message, dict)
                and message.get("role") == "assistant"
            ),
            "",
        )
        source = "unknown"
        if isinstance(reply, str) and reply:
            digest = sha256(reply.strip().encode("utf-8")).hexdigest()
            observed = provenance.get(digest, set())
            if len(observed) == 1:
                source = next(iter(observed))
            elif outcomes is None and reply.strip() == FILTER_NOTICE:
                source = "service_filter"
        sources[source] += 1
        if source == "model_response" and record["attack_success"]:
            model_successes += 1
    if details is None:
        for category in RISK_CATEGORIES:
            total = aggregate.get(f"{category}_total", 0)
            if isinstance(total, int) and not isinstance(total, bool):
                scored[category] = max(total, 0)
        sources["unknown"] = sum(scored.values())
    reported_total = aggregate.get("overall_total")
    scored_total = sum(scored.values())
    if details is None and not scored_total:
        if isinstance(reported_total, int) and not isinstance(
            reported_total, bool
        ):
            scored_total = max(reported_total, 0)
            sources["unknown"] = scored_total
    issues = []
    if invalid_records:
        issues.append("Some case records have no valid evaluation verdict.")
    if reported_total is not None and reported_total != scored_total:
        issues.append("Scorecard totals disagree with the case records.")
    for category in RISK_CATEGORIES:
        reported = aggregate.get(f"{category}_total")
        if reported is not None and reported != scored[category]:
            issues.append(f"{category} totals disagree with the case records.")
    failures = [
        outcome
        for outcome in outcomes or []
        if outcome.get("outcome") == "error"
    ]
    complete = (
        planned is not None
        and bool(records)
        and all(
            scored[category] == total for category, total in planned.items()
        )
        and scored_total == sum(planned.values())
        and not issues
        and not execution_failed
    )
    status = "complete" if complete else "partial"
    if (
        planned is None
        and not issues
        and not execution_failed
        and not failures
    ):
        status = "unverified"
    planned_total = sum(planned.values()) if planned is not None else None
    return {
        "status": status,
        "planned": planned_total,
        "scored": scored_total,
        "unscored": (
            sum(
                max(total - scored[category], 0)
                for category, total in planned.items()
            )
            if planned is not None
            else None
        ),
        "planned_per_category": planned,
        "scored_per_category": dict(scored),
        "target_attempts": len(outcomes) if outcomes is not None else None,
        "target_failures": failures,
        "response_sources": {
            source: sources[source]
            for source in ("service_filter", "model_response", "unknown")
        },
        "source_evidence": (
            "API response status"
            if outcomes is not None
            else "Legacy notice text only; other response sources are unknown"
        ),
        "model_only_asr": (
            100 * model_successes / sources["model_response"]
            if sources["model_response"]
            else None
        ),
        "execution_failed": execution_failed,
        "issues": issues,
    }


def summarize_health(health: dict) -> str:
    """Keep completion, filtering, and infrastructure failures explicit."""
    planned = health["planned"]
    lines = [f"Run health: {health['status'].upper()}"]
    if planned is None:
        lines.append(
            f"Coverage: {health['scored']} scored; planned count unavailable."
        )
    else:
        lines.append(
            f"Coverage: {planned} planned, {health['scored']} scored, "
            f"{health['unscored']} unscored."
        )
    sources = health["response_sources"]
    lines.append(
        f"Scored response sources: {sources['service_filter']} service-filter "
        f"blocks, {sources['model_response']} model replies, "
        f"{sources['unknown']} unattributed."
    )
    lines.append(f"Source evidence: {health['source_evidence']}.")
    rate = health["model_only_asr"]
    lines.append(
        f"Model-reply ASR: {rate:.2f}%."
        if rate is not None
        else "Model-reply ASR: unavailable (no attributed model replies)."
    )
    failures = health["target_failures"]
    lines.append(
        f"Failed target requests: {len(failures)}."
        if health["target_attempts"] is not None
        else "Failed target requests: unavailable (no request telemetry)."
    )
    for failure in failures:
        fields = ", ".join(
            f"{key}={value}"
            for key, value in failure.items()
            if key != "outcome"
        )
        lines.append(f"  {fields}")
    lines.extend(health["issues"])
    lines.append(
        "Service-filter blocks count toward end-to-end protection, "
        "not evidence of the model's own resistance."
    )
    if health["execution_failed"]:
        lines.append("The evaluator raised an execution error.")
    if health["status"] != "complete":
        lines.append("Do not treat this run as a complete safety assessment.")
    return "\n".join(lines)


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


def inspect_saved_run(
    path: Path, expected_per_category: int | None = None
) -> tuple[dict, dict]:
    """Read local artifacts without rewriting the original SDK reports."""
    data = read_evaluation(path)
    directory = path if path.is_dir() else path.parent
    metadata_path = directory / RUN_HEALTH_FILE
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.is_file()
        else {}
    )
    planned = metadata.get("planned_per_category")
    if expected_per_category is not None:
        supplied = dict.fromkeys(RISK_CATEGORIES, expected_per_category)
        if planned is not None and planned != supplied:
            raise ValueError(
                "Expected counts conflict with the saved run plan."
            )
        planned = supplied
    health = assess_run(
        data,
        planned,
        metadata.get("target_outcomes"),
        execution_failed=metadata.get("execution_failed", False),
    )
    return extract_scorecard(data), health


def expected_count(value: str) -> int:
    """Accept a known historical case count without inferring missing cases."""
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("Expected cases must be positive.")
    return count


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
    parser.add_argument(
        "--expected-per-category",
        type=expected_count,
        help=(
            "Known case count per category for a legacy --summary "
            "without a saved plan."
        ),
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
        from azure.ai.evaluation.red_team._utils.formatting_utils import (
            get_flattened_attack_strategies,
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
    strategy_count = len(get_flattened_attack_strategies(strategies))
    planned = dict.fromkeys(
        RISK_CATEGORIES, args.num_objectives * strategy_count
    )
    outcomes = []
    token = RUN_OUTCOMES.set(outcomes)
    execution_failed = True
    try:
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
                target=vaultbot_target,
                scan_name="VaultBot Safety Review",
                attack_strategies=strategies,
                output_path=str(output),
                parallel_execution=False,
                max_parallel_tasks=1,
            )
        execution_failed = False
    except Exception as error:
        raise ValueError(
            "Evaluation did not finish; inspect the saved run-health report."
        ) from error
    finally:
        RUN_OUTCOMES.reset(token)
        try:
            data = read_evaluation(output)
        except (OSError, ValueError):
            data = {"scorecard": {}, "attack_details": []}
        health = assess_run(
            data, planned, outcomes, execution_failed=execution_failed
        )
        output.mkdir(parents=True, exist_ok=True)
        with (output / RUN_HEALTH_FILE).open("x", encoding="utf-8") as handle:
            json.dump(
                {
                    "schema_version": 1,
                    **health,
                    "target_outcomes": [
                        sanitized_outcome(item) for item in outcomes
                    ],
                },
                handle,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
        print(f"Run artifacts: {output}")
        print(summarize_health(health))
    print(summarize_scorecard(extract_scorecard(data)))
    if health["status"] != "complete":
        raise ValueError(
            "Evaluation is incomplete; unscored cases are not passes."
        )


def main(argv: list[str] | None = None) -> int:
    """Return nonzero on incomplete scans instead of implying a safe result."""
    args = create_parser().parse_args(argv)
    try:
        if args.expected_per_category is not None and not args.summary:
            raise ValueError("--expected-per-category requires --summary.")
        if args.configure:
            configure_project(BASE_DIR / ".env")
            return 0
        if args.summary:
            scorecard, health = inspect_saved_run(
                args.summary, args.expected_per_category
            )
            print(summarize_health(health))
            print(summarize_scorecard(scorecard))
            return 0 if health["status"] == "complete" else 2
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
