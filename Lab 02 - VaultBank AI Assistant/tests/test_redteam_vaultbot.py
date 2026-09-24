"""Test evaluation plumbing without importing or calling the cloud scanner."""

import asyncio
import json

import httpx
import pytest
import redteam_vaultbot as redteam
from dotenv import dotenv_values


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
