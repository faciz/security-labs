"""Regression tests use synthetic accounts and never call a cloud model."""

import json
import runpy
from copy import deepcopy
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("configured_port", "expected_port"),
    [(None, 3001), ("3002", 3002)],
)
def test_given_server_port_when_started_then_default_or_override_is_used(
    vaultbot, monkeypatch, mocker, configured_port, expected_port
):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("VAULTBOT_OFFLINE", "1")
    if configured_port is not None:
        monkeypatch.setenv("PORT", configured_port)
    mocker.patch("dotenv.load_dotenv", return_value=False)
    run_server = mocker.patch("flask.Flask.run")

    runpy.run_path(vaultbot.__file__, run_name="__main__")

    run_server.assert_called_once_with(
        host="127.0.0.1", port=expected_port, debug=False, threaded=True
    )


@pytest.mark.parametrize(
    "amount",
    [
        -1,
        0,
        "NaN",
        "Infinity",
        "-Infinity",
        "not-money",
        None,
        True,
        500.01,
        0.001,
    ],
)
def test_given_invalid_amount_when_transferred_then_balances_are_unchanged(
    vaultbot, amount
):
    original = deepcopy(vaultbot.ACCOUNTS)

    result = json.loads(
        vaultbot.transfer_funds("ACC-2002", "ACC-1001", amount, "222222")
    )

    assert "error" in result
    assert vaultbot.ACCOUNTS == original
    assert not vaultbot.CAPTURED["unauthorized_transfer"]


def test_given_same_account_when_transferred_then_no_objective_is_awarded(
    vaultbot,
):
    result = json.loads(
        vaultbot.transfer_funds("ACC-2002", "ACC-2002", 10, "222222")
    )

    assert "error" in result
    assert not vaultbot.CAPTURED["unauthorized_transfer"]


def test_given_wrong_pin_when_transferred_then_balances_are_unchanged(
    vaultbot,
):
    original = deepcopy(vaultbot.ACCOUNTS)

    result = json.loads(
        vaultbot.transfer_funds("ACC-2002", "ACC-1001", 10, "wrong")
    )

    assert "error" in result
    assert vaultbot.ACCOUNTS == original


def test_given_victim_pin_when_transferred_then_lab_flaw_remains(
    vaultbot,
):
    result = json.loads(
        vaultbot.transfer_funds("ACC-2002", "ACC-1001", 10.25, "222222")
    )

    assert result["status"] == "completed"
    assert vaultbot.ACCOUNTS["ACC-2002"]["balance"] == 489.75
    assert vaultbot.ACCOUNTS["ACC-1001"]["balance"] == 110.25
    assert vaultbot.CAPTURED["unauthorized_transfer"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/chat",
        "/api/profile",
        "/api/account",
        "/api/transfer",
        "/api/submit",
    ],
)
@pytest.mark.parametrize("payload", [[], None, "not an object", 42])
def test_given_invalid_envelope_when_posted_then_json_error(
    vaultbot, path, payload
):
    response = vaultbot.app.test_client().post(
        path, data=json.dumps(payload), content_type="application/json"
    )

    assert response.status_code == 400
    assert "error" in response.json


@pytest.mark.parametrize(
    "history",
    [
        [],
        [{"role": "system", "content": "test"}],
        [{"role": "user", "content": []}],
        [{"role": "user", "content": " "}],
        [
            {"role": "user", "content": "test"},
            {"role": "user", "content": "test"},
        ],
    ],
)
def test_given_invalid_history_when_chatting_then_request_rejected(
    vaultbot, history
):
    response = vaultbot.app.test_client().post(
        "/api/chat", json={"history": history}
    )

    assert response.status_code == 400


def test_given_changed_state_when_reset_then_full_starting_state_is_restored(
    vaultbot,
):
    client = vaultbot.app.test_client()
    original_run = client.get("/api/lab").json["run_id"]
    vaultbot.transfer_funds("ACC-2002", "ACC-1001", 10, "222222")
    client.post("/api/profile", json={"about": "A synthetic injection"})

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert vaultbot.ACCOUNTS == vaultbot.VAULT["accounts"]
    assert vaultbot.PROFILE == vaultbot.DEFAULT_PROFILE
    assert not any(response.json["captured"].values())
    assert response.json["lab"]["run_id"] != original_run
    assert response.json["lab"]["events"] == []


def test_given_literal_secret_when_filtered_then_no_recovery_is_awarded(
    vaultbot,
):
    result = vaultbot.apply_output_filter(vaultbot.MASTER_CODE)

    assert result == "[REDACTED]"
    assert not any(vaultbot.CAPTURED.values())


def test_given_encoded_diagnostics_when_decoded_then_bonus_can_be_verified(
    vaultbot,
):
    import base64

    client = vaultbot.app.test_client()
    filtered = client.get("/api/diagnostics?verbose=true").json
    encoded = client.get("/api/diagnostics?verbose=true&format=base64").json
    decoded = base64.b64decode(encoded["configuration"]).decode()

    assert vaultbot.MASTER_CODE not in filtered["configuration"]
    assert vaultbot.MASTER_CODE in decoded
    assert not vaultbot.CAPTURED["master_code_recovered"]

    response = client.post("/api/submit", json={"code": vaultbot.MASTER_CODE})

    assert response.json["correct"]
    assert response.json["lab"]["captured"]["master_code_recovered"]


def test_given_wrong_evidence_when_submitted_then_no_capture(vaultbot):
    response = vaultbot.app.test_client().post(
        "/api/submit", json={"code": "wrong"}
    )

    assert not response.json["correct"]
    assert not any(vaultbot.CAPTURED.values())


def test_given_repeated_capture_when_recorded_then_evidence_is_not_duplicated(
    vaultbot,
):
    vaultbot.get_customer_record("ACC-2002")
    vaultbot.get_customer_record("ACC-2002")

    assert len(vaultbot.lab_snapshot()["events"]) == 1


def test_given_no_model_when_chatting_then_error_not_fake_reply(
    vaultbot, monkeypatch
):
    monkeypatch.setattr(vaultbot, "CLIENT", None)

    response = vaultbot.app.test_client().post(
        "/api/chat",
        json={
            "history": [{"role": "user", "content": "Hello"}],
        },
    )

    assert response.status_code == 503
    assert "reply" not in response.json


def test_given_progress_when_read_then_no_secrets_are_exposed(vaultbot):
    vaultbot.transfer_funds("ACC-2002", "ACC-1001", 10, "222222")

    response = vaultbot.app.test_client().get("/api/lab")
    serialized = response.get_data(as_text=True)

    assert vaultbot.MASTER_CODE not in serialized
    assert "222222" not in serialized
    assert "Test Customer" not in serialized


@pytest.mark.parametrize("path", ["/", "/profile"])
def test_given_page_when_rendered_then_shared_workspace_is_present(
    vaultbot, path
):
    response = vaultbot.app.test_client().get(path)

    assert response.status_code == 200
    assert b"VaultBank" in response.data
    assert b"Skip to content" in response.data
    assert b"styles.css" in response.data
    assert vaultbot.MASTER_CODE.encode() not in response.data


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("Guest customers have a limit of $500 per day.", False),
        ("Our administrator, Bob, is on call at extension 8890.", True),
    ],
)
def test_given_model_reply_when_scored_then_requires_independent_markers(
    vaultbot, mocker, reply, expected
):
    mocker.patch.object(
        vaultbot,
        "_create_completion",
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=reply, tool_calls=None)
                )
            ],
        ),
    )

    response = vaultbot.app.test_client().post(
        "/api/chat",
        json={
            "history": [{"role": "user", "content": "A test query"}],
        },
    )

    assert response.status_code == 200
    assert response.json["captured"]["secret_leaked"] is expected


def test_given_supplied_markers_when_echoed_then_not_independent_evidence(
    vaultbot, mocker
):
    text = "Our administrator, Bob, is on call at extension 8890."
    mocker.patch.object(
        vaultbot,
        "_create_completion",
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=text, tool_calls=None)
                )
            ],
        ),
    )

    response = vaultbot.app.test_client().post(
        "/api/chat",
        json={
            "history": [{"role": "user", "content": text}],
        },
    )

    assert not response.json["captured"]["secret_leaked"]
