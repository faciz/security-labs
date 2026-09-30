"""Test evaluation plumbing without calling a model or cloud scanner."""

import asyncio
import json
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
import redteam_vaultbot as redteam
from dotenv import dotenv_values


def evaluation_fixture(counts, filtered=0):
    records = []
    for category, total in counts.items():
        for _ in range(total):
            records.append(
                {
                    "risk_category": category,
                    "attack_success": False,
                    "risk_assessment": {
                        category: {"severity_label": "Very low"}
                    },
                    "conversation": [
                        {
                            "role": "assistant",
                            "content": (
                                redteam.FILTER_NOTICE
                                if len(records) < filtered
                                else "A synthetic model response"
                            ),
                        }
                    ],
                }
            )
    totals = {f"{category}_total": total for category, total in counts.items()}
    return {
        "scorecard": {
            "risk_category_summary": [
                {
                    **totals,
                    "overall_total": len(records),
                    "overall_asr": 0,
                    "overall_successful_attacks": 0,
                }
            ]
        },
        "attack_details": records,
    }


def test_given_missing_case_when_assessed_then_run_is_partial():
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 2)
    counts = {**plan, "sexual": 1}

    health = redteam.assess_run(evaluation_fixture(counts, filtered=4), plan)

    assert health["status"] == "partial"
    assert (health["planned"], health["scored"], health["unscored"]) == (
        8,
        7,
        1,
    )
    assert health["response_sources"] == {
        "service_filter": 4,
        "model_response": 0,
        "unknown": 3,
    }
    assert health["model_only_asr"] is None
    assert "8 planned, 7 scored, 1 unscored" in redteam.summarize_health(
        health
    )


def test_given_full_coverage_when_assessed_then_run_is_complete():
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 1)

    health = redteam.assess_run(evaluation_fixture(plan), plan)

    assert health["status"] == "complete"
    assert health["unscored"] == 0


def test_given_unscored_record_when_assessed_then_it_is_not_counted():
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 1)
    data = evaluation_fixture(plan)
    data["attack_details"][0]["risk_assessment"] = None

    health = redteam.assess_run(data, plan)

    assert health["status"] == "partial"
    assert health["scored"] == 3
    assert health["unscored"] == 1


def test_given_legacy_run_without_plan_when_assessed_then_unverified():
    data = evaluation_fixture(dict.fromkeys(redteam.RISK_CATEGORIES, 1))

    health = redteam.assess_run(data)

    assert health["status"] == "unverified"
    assert health["planned"] is None
    assert "planned count unavailable" in redteam.summarize_health(health)


def test_given_mismatched_counts_when_assessed_then_summary_is_not_trusted():
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 2)
    data = evaluation_fixture({**plan, "sexual": 1})
    data["scorecard"]["risk_category_summary"][0]["overall_total"] = 8

    health = redteam.assess_run(data, plan)

    assert health["status"] == "partial"
    assert health["scored"] == 7
    assert health["issues"]


def test_given_api_provenance_when_assessed_then_filtering_is_separate():
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 1)
    data = evaluation_fixture(plan, filtered=2)
    data["attack_details"][-1]["attack_success"] = True
    outcomes = [
        {
            "outcome": "service_filter",
            "response_hash": sha256(
                redteam.FILTER_NOTICE.encode()
            ).hexdigest(),
        },
        {
            "outcome": "model_response",
            "response_hash": sha256(b"A synthetic model response").hexdigest(),
        },
    ]

    health = redteam.assess_run(data, plan, outcomes)

    assert health["response_sources"] == {
        "service_filter": 2,
        "model_response": 2,
        "unknown": 0,
    }
    assert health["model_only_asr"] == 50.0
    assert health["source_evidence"] == "API response status"


@pytest.mark.parametrize("status", ["ok", "filtered"])
def test_given_response_status_when_called_then_provenance_is_recorded(
    mocker, status
):
    client = mocker.AsyncMock()
    client.post.return_value = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost/api/chat"),
        json={"status": status, "reply": "Synthetic response"},
    )
    context = mocker.patch.object(redteam.httpx, "AsyncClient")
    context.return_value.__aenter__.return_value = client
    outcomes = []
    token = redteam.RUN_OUTCOMES.set(outcomes)
    try:
        asyncio.run(redteam.vaultbot_callback("Synthetic query"))
    finally:
        redteam.RUN_OUTCOMES.reset(token)

    assert outcomes == [
        {
            "outcome": "model_response"
            if status == "ok"
            else "service_filter",
            "http_status": 200,
            "response_hash": sha256(b"Synthetic response").hexdigest(),
        }
    ]
    assert "Synthetic query" not in json.dumps(outcomes)
    assert "Synthetic response" not in json.dumps(outcomes)


def test_given_http_failure_when_recorded_then_only_safe_metadata_is_kept(
    mocker,
):
    client = mocker.AsyncMock()
    client.post.return_value = httpx.Response(
        502,
        request=httpx.Request("POST", "http://localhost/api/chat"),
        json={
            "error": "PRIVATE PAYLOAD",
            "diagnostics": {
                "category": "upstream_timeout",
                "error_id": "a" * 32,
                "upstream_request_id": "person@example.test",
                "prompt": "PRIVATE PAYLOAD",
                "token": "PRIVATE TOKEN",
            },
        },
    )
    context = mocker.patch.object(redteam.httpx, "AsyncClient")
    context.return_value.__aenter__.return_value = client
    outcomes = []
    token = redteam.RUN_OUTCOMES.set(outcomes)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(redteam.vaultbot_callback("PRIVATE QUERY"))
    finally:
        redteam.RUN_OUTCOMES.reset(token)

    assert outcomes == [
        {
            "outcome": "error",
            "http_status": 502,
            "category": "upstream_timeout",
            "error_id": "a" * 32,
        }
    ]


def test_given_partial_saved_run_when_summarized_then_exit_is_nonzero(
    tmp_path, capsys, mocker
):
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 2)
    data = evaluation_fixture({**plan, "sexual": 1}, filtered=4)
    (tmp_path / "evaluation_results.json").write_text(json.dumps(data))
    preflight = mocker.patch.object(redteam, "preflight")

    result = redteam.main(
        ["--summary", str(tmp_path), "--expected-per-category", "2"]
    )

    assert result == 2
    assert "PARTIAL" in capsys.readouterr().out
    preflight.assert_not_called()


@pytest.mark.parametrize(
    "missing,execution_error", [(0, False), (1, False), (8, True)]
)
def test_given_sdk_completion_when_running_then_health_controls_exit(
    tmp_path, monkeypatch, mocker, capsys, missing, execution_error
):
    sdk = pytest.importorskip("azure.ai.evaluation.red_team")
    mocker.patch("azure.identity.DefaultAzureCredential")
    mocker.patch.object(redteam, "preflight")
    monkeypatch.setenv(
        "AZURE_AI_PROJECT", "https://example.test/api/projects/training"
    )
    plan = dict.fromkeys(redteam.RISK_CATEGORIES, 2)
    counts = {**plan, "sexual": 2 - missing} if missing < 2 else {}
    report = evaluation_fixture(counts, filtered=4)
    output = tmp_path / "new-run"

    async def sdk_scan(**kwargs):
        assert kwargs["target"] is redteam.vaultbot_target
        assert kwargs["parallel_execution"] is False
        assert kwargs["max_parallel_tasks"] == 1
        destination = Path(kwargs["output_path"])
        destination.mkdir()
        outcomes = redteam.RUN_OUTCOMES.get()
        assert outcomes is not None
        for record in report["attack_details"]:
            reply = record["conversation"][0]["content"]
            outcomes.append(
                {
                    "outcome": (
                        "service_filter"
                        if reply == redteam.FILTER_NOTICE
                        else "model_response"
                    ),
                    "response_hash": sha256(reply.encode()).hexdigest(),
                }
            )
        if missing:
            outcomes.append(
                {
                    "outcome": "error",
                    "http_status": 502,
                    "category": "upstream_timeout",
                    "error_id": "a" * 32,
                }
            )
        if execution_error:
            raise RuntimeError("PRIVATE SDK ERROR")
        (destination / "evaluation_results.json").write_text(
            json.dumps(report)
        )

    scan = mocker.AsyncMock(side_effect=sdk_scan)
    mocker.patch.object(sdk, "RedTeam").return_value.scan = scan

    result = redteam.main(
        ["--yes", "--num-objectives", "2", "--output", str(output)]
    )

    assert result == (2 if missing else 0)
    metadata = json.loads((output / redteam.RUN_HEALTH_FILE).read_text())
    assert metadata["status"] == ("partial" if missing else "complete")
    assert metadata["planned"] == 8
    assert metadata["scored"] == 8 - missing
    assert metadata["unscored"] == missing
    assert metadata["execution_failed"] is execution_error
    assert len(metadata["target_failures"]) == bool(missing)
    if not execution_error:
        assert metadata["response_sources"]["service_filter"] == 4
        assert metadata["response_sources"]["model_response"] == 4 - missing
        original = (output / "evaluation_results.json").read_bytes()
        assert redteam.main(["--summary", str(output)]) == result
        assert (output / "evaluation_results.json").read_bytes() == original
    captured = capsys.readouterr()
    assert "PRIVATE SDK ERROR" not in captured.out + captured.err
    assert redteam.RUN_OUTCOMES.get() is None


def test_given_legacy_summary_without_plan_when_read_then_exit_is_unverified(
    tmp_path, capsys
):
    report = evaluation_fixture(dict.fromkeys(redteam.RISK_CATEGORIES, 1))
    (tmp_path / "evaluation_results.json").write_text(json.dumps(report))

    result = redteam.main(["--summary", str(tmp_path)])

    assert result == 2
    output = capsys.readouterr().out
    assert "UNVERIFIED" in output
    assert "Failed target requests: unavailable" in output
    assert not (tmp_path / redteam.RUN_HEALTH_FILE).exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://public.example.test",
        "http://localhost@external.test",
        "http://127.0.0.1/path",
        "http://localhost?token=secret",
    ],
)
def test_given_external_or_ambiguous_target_when_validated_then_rejected(url):
    with pytest.raises(ValueError, match="loopback"):
        redteam.validate_target(url)


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:3000", "http://localhost:3001/", "http://[::1]:3000"],
)
def test_given_local_target_when_validated_then_accepted(url):
    assert redteam.validate_target(url) == url.rstrip("/")


def test_given_health_preflight_when_called_then_chat_is_not_used(mocker):
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "http://localhost/api/health"),
        json={
            "service": "VaultBot",
            "lab": "02",
            "model_configured": True,
        },
    )
    request = mocker.patch.object(redteam.httpx, "get", return_value=response)

    redteam.preflight("http://localhost")

    request.assert_called_once_with(
        "http://localhost/api/health", timeout=10, follow_redirects=False
    )


@pytest.mark.parametrize(
    "target,expected",
    [
        (None, "http://127.0.0.1:3001"),
        ("http://127.0.0.1:3002", "http://127.0.0.1:3002"),
    ],
)
def test_given_target_setting_when_checking_then_default_or_override_is_used(
    monkeypatch, mocker, target, expected
):
    monkeypatch.delenv("VAULTBOT_URL", raising=False)
    if target is not None:
        monkeypatch.setenv("VAULTBOT_URL", target)
    preflight = mocker.patch.object(redteam, "preflight")

    result = redteam.main(["--check"])

    assert result == 0
    preflight.assert_called_once_with(expected)


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (502, {"error": "unavailable"}, httpx.HTTPStatusError),
        (200, {"error": "unavailable"}, ValueError),
        (200, {"reply": "", "status": "ok"}, ValueError),
        (200, [], ValueError),
    ],
)
def test_given_target_failure_when_scanned_then_not_scored_as_reply(
    mocker, status, payload, expected
):
    client = mocker.AsyncMock()
    client.post.return_value = httpx.Response(
        status,
        request=httpx.Request("POST", "http://localhost/api/chat"),
        json=payload,
    )
    context = mocker.patch.object(redteam.httpx, "AsyncClient")
    context.return_value.__aenter__.return_value = client

    with pytest.raises(expected):
        asyncio.run(redteam.vaultbot_callback("A synthetic test query"))


@pytest.mark.parametrize(
    "target,expected",
    [
        (None, "http://127.0.0.1:3001"),
        ("http://127.0.0.1:3002", "http://127.0.0.1:3002"),
    ],
)
def test_given_real_filtered_reply_when_scanned_then_reply_is_evaluable(
    monkeypatch, mocker, target, expected
):
    monkeypatch.delenv("VAULTBOT_URL", raising=False)
    if target is not None:
        monkeypatch.setenv("VAULTBOT_URL", target)
    query = "A synthetic test query"
    client = mocker.AsyncMock()
    client.post.return_value = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost/api/chat"),
        json={
            "reply": "The model service blocked this request.",
            "status": "filtered",
        },
    )
    context = mocker.patch.object(redteam.httpx, "AsyncClient")
    context.return_value.__aenter__.return_value = client

    reply = asyncio.run(redteam.vaultbot_callback(query))

    assert reply == "The model service blocked this request."
    client.post.assert_awaited_once_with(
        f"{expected}/api/chat",
        json={"history": [{"role": "user", "content": query}]},
    )


def test_given_sdk_messages_when_targeted_then_reply_is_awaited(mocker):
    callback = mocker.patch.object(
        redteam, "vaultbot_callback", return_value="A synthetic response"
    )

    result = asyncio.run(
        redteam.vaultbot_target(
            messages=[{"role": "user", "content": "A synthetic query"}],
            stream=False,
            session_state=None,
            context={},
        )
    )

    callback.assert_awaited_once_with("A synthetic query")
    assert result == {
        "messages": [{"role": "assistant", "content": "A synthetic response"}]
    }


def test_given_target_error_when_adapted_then_not_converted_to_reply(mocker):
    mocker.patch.object(
        redteam,
        "vaultbot_callback",
        side_effect=httpx.ConnectError("Connection failed"),
    )

    with pytest.raises(httpx.ConnectError, match="Connection failed"):
        asyncio.run(
            redteam.vaultbot_target(
                messages=[{"role": "user", "content": "A synthetic query"}]
            )
        )


def test_given_sdk_when_target_registered_then_native_callback_is_used(mocker):
    strategies = pytest.importorskip(
        "azure.ai.evaluation.red_team._utils.strategy_utils"
    )
    target = mocker.patch.object(
        strategies, "_CallbackChatTarget", return_value=mocker.sentinel.target
    )

    result = strategies.get_chat_target(redteam.vaultbot_target)

    assert result is mocker.sentinel.target
    target.assert_called_once_with(callback=redteam.vaultbot_target)


@pytest.mark.parametrize("container", ["scorecard", "redteaming_scorecard"])
def test_given_scorecard_when_summarized_then_counts_and_percent_are_correct(
    tmp_path, container
):
    scorecard = {
        "risk_category_summary": [
            {
                "overall_asr": 7.14,
                "overall_total": 56,
                "overall_successful_attacks": 4,
            }
        ]
    }
    (tmp_path / "evaluation_results.json").write_text(
        json.dumps({container: scorecard}), encoding="utf-8"
    )

    summary = redteam.summarize_scorecard(redteam.read_scorecard(tmp_path))

    assert "7.14% (4/56)" in summary
    assert "does not measure account authorization" in summary


def test_given_no_scored_attacks_when_summarized_then_not_a_pass():
    summary = redteam.summarize_scorecard(
        {
            "risk_category_summary": [
                {
                    "overall_asr": 0,
                    "overall_total": 0,
                    "overall_successful_attacks": 0,
                }
            ]
        }
    )

    assert "not scored (0/0)" in summary


@pytest.mark.parametrize("value", ["0", "21", "-1"])
def test_given_excessive_objectives_when_parsed_then_rejected(value):
    with pytest.raises(SystemExit):
        redteam.create_parser().parse_args(["--num-objectives", value])


def test_given_existing_project_config_when_configured_then_preserved(
    tmp_path,
):
    destination = tmp_path / ".env"
    destination.write_text("EXISTING=yes\n", encoding="utf-8")

    redteam.configure_project(destination)

    assert destination.read_text(encoding="utf-8") == "EXISTING=yes\n"


@pytest.mark.parametrize(
    "target,expected",
    [
        (None, "http://127.0.0.1:3001"),
        ("http://127.0.0.1:3002", "http://127.0.0.1:3002"),
    ],
)
def test_given_valid_project_when_configured_then_saved_privately(
    tmp_path, monkeypatch, target, expected
):
    import stat

    monkeypatch.setenv(
        "AZURE_AI_PROJECT",
        "https://example.services.ai.azure.com/api/projects/training",
    )
    monkeypatch.delenv("VAULTBOT_URL", raising=False)
    if target is not None:
        monkeypatch.setenv("VAULTBOT_URL", target)

    redteam.configure_project(tmp_path / ".env")

    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    assert dotenv_values(tmp_path / ".env")["VAULTBOT_URL"] == expected


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "http://example.test/api/projects/test",
        "https://example.test/api/projects/",
        "https://example.test/api/projects/test?token=secret",
        "https://<your-account>.services.ai.azure.com/"
        "api/projects/<your-project>",
    ],
)
def test_given_invalid_project_when_validated_then_rejected(endpoint):
    with pytest.raises(ValueError, match="valid Foundry"):
        redteam.validate_project(endpoint)
