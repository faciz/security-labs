"""Setup checks are local-only and must preserve existing configuration."""

import json
import stat
from subprocess import CompletedProcess

import pytest
import setup_lab
from dotenv import dotenv_values


def test_given_new_lab_when_generated_then_records_are_synthetic_and_random():
    first = setup_lab.generate_vault()
    second = setup_lab.generate_vault()

    assert len(first["accounts"]) == 3
    assert first["accounts"]["ACC-1001"]["balance"] == 2450.0
    assert first["master_code"] != second["master_code"]
    assert first["transfer_flag"] != second["transfer_flag"]
    assert all(
        record["ssn"].startswith("900-")
        for record in first["accounts"].values()
    )
    assert all(
        record["email"].endswith(".test")
        for record in first["accounts"].values()
    )


def test_given_existing_data_when_setup_repeats_then_data_is_preserved(
    tmp_path,
):
    assert setup_lab.write_vault(tmp_path)
    destination = tmp_path / ".secrets" / "vault_data.json"
    original = destination.read_bytes()

    assert not setup_lab.write_vault(tmp_path)
    assert destination.read_bytes() == original
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_given_explicit_regeneration_when_setup_runs_then_values_change(
    tmp_path,
):
    setup_lab.write_vault(tmp_path)
    destination = tmp_path / ".secrets" / "vault_data.json"
    original = json.loads(destination.read_text(encoding="utf-8"))

    setup_lab.write_vault(tmp_path, regenerate=True)

    regenerated = json.loads(destination.read_text(encoding="utf-8"))
    assert original["master_code"] != regenerated["master_code"]


def test_given_existing_connection_when_saved_then_it_is_not_overwritten(
    tmp_path,
):
    destination = tmp_path / ".env"
    destination.write_text("EXISTING=yes\n", encoding="utf-8")

    with pytest.raises(ValueError, match="preserved"):
        setup_lab.save_connection(tmp_path, {})

    assert destination.read_text(encoding="utf-8") == "EXISTING=yes\n"


def test_given_connection_when_saved_then_values_round_trip_privately(
    tmp_path,
):
    settings = {
        "AOAI_ENDPOINT": "https://example.openai.azure.com/",
        "AOAI_DEPLOYMENT": "training",
        "AOAI_KEY": "test-only='value",
    }

    setup_lab.save_connection(tmp_path, settings)

    assert dotenv_values(tmp_path / ".env") == settings
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "http://example.test",
        "https://user:pass@example.test",
        "https://example.test/?key=secret",
    ],
)
def test_given_invalid_endpoint_when_saved_then_no_config_is_written(
    tmp_path, endpoint
):
    with pytest.raises(ValueError, match="HTTPS"):
        setup_lab.save_connection(tmp_path, {"AOAI_ENDPOINT": endpoint})

    assert not (tmp_path / ".env").exists()


def model_entry(
    name="gpt-4.1-mini", version="2025-04-14", lifecycle="GenerallyAvailable"
):
    return {
        "kind": "OpenAI",
        "model": {
            "name": name,
            "version": version,
            "lifecycleStatus": lifecycle,
            "capabilities": {"chatCompletion": "true"},
            "skus": [{"name": "GlobalStandard"}],
        },
    }


def test_given_model_override_when_selecting_then_name_is_honored():
    catalog = [model_entry(), model_entry("gpt-5-mini", "2025-08-07")]

    selected = setup_lab.select_model(catalog, name="gpt-5-mini")

    assert selected == ("gpt-5-mini", "2025-08-07", "GlobalStandard")


@pytest.mark.parametrize(
    "catalog",
    [
        [],
        [model_entry(lifecycle="Deprecated")],
        [model_entry("expensive-large-model")],
    ],
)
def test_given_no_approved_small_model_when_selecting_then_setup_stops(
    catalog,
):
    with pytest.raises(ValueError, match="No compatible"):
        setup_lab.select_model(catalog)


def test_given_explicit_sku_when_unsupported_then_setup_does_not_fall_back():
    with pytest.raises(ValueError, match="No compatible"):
        setup_lab.select_model([model_entry()], sku="Unsupported")


def test_given_existing_settings_when_azure_requested_then_no_cloud_calls(
    tmp_path, mocker
):
    (tmp_path / ".env").write_text("EXISTING=yes\n", encoding="utf-8")
    azure = mocker.patch.object(setup_lab, "azure_json")
    args = setup_lab.create_parser().parse_args(["--azure"])

    setup_lab.provision_connection(args, tmp_path)

    azure.assert_not_called()


def test_given_existing_resource_group_when_provisioning_then_no_mutation(
    tmp_path, mocker
):
    mocker.patch.object(setup_lab.shutil, "which", return_value="az")
    azure = mocker.patch.object(
        setup_lab,
        "azure_json",
        side_effect=[{"id": "test-subscription"}, True],
    )
    args = setup_lab.create_parser().parse_args(
        ["--azure", "--resource-group", "existing", "--yes"]
    )

    with pytest.raises(ValueError, match="already exists"):
        setup_lab.provision_connection(args, tmp_path)

    assert azure.call_count == 2
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("explicit_subscription", [None, "chosen-sub"])
def test_given_subscription_when_provisioning_then_graph_has_no_scope_flag(
    tmp_path, mocker, explicit_subscription
):
    subscription = explicit_subscription or "default-subscription"
    resource_id = (
        f"/subscriptions/{subscription}/resourceGroups/test-lab/"
        "providers/Microsoft.CognitiveServices/accounts/test-account"
    )
    responses = iter(
        [
            {"id": subscription},
            False,
            [model_entry()],
            "test-user-id",
            {},
            {
                "id": resource_id,
                "properties": {
                    "endpoint": "https://test-account.openai.azure.com/"
                },
            },
            {},
            {},
        ]
    )

    def run_azure(command, **kwargs):
        if command[1:4] == ["ad", "signed-in-user", "show"]:
            if "--subscription" in command:
                return CompletedProcess(
                    command, 2, "", "unrecognized arguments: --subscription"
                )
        return CompletedProcess(command, 0, json.dumps(next(responses)), "")

    mocker.patch.object(setup_lab.shutil, "which", return_value="az")
    runner = mocker.patch.object(
        setup_lab.subprocess, "run", side_effect=run_azure
    )
    args = setup_lab.create_parser().parse_args(
        ["--azure", "--resource-group", "test-lab", "--yes"]
    )
    args.subscription = explicit_subscription
    args.principal_id = None

    setup_lab.provision_connection(args, tmp_path)

    commands = [call.args[0] for call in runner.call_args_list]
    identity_command = commands[3]
    assert identity_command[1:4] == ["ad", "signed-in-user", "show"]
    assert "--subscription" not in identity_command
    resource_commands = commands[1:3] + commands[4:]
    assert len(resource_commands) == 6
    assert all(
        command[command.index("--subscription") + 1] == subscription
        for command in resource_commands
    )
    settings = dotenv_values(tmp_path / ".env")
    assert settings["AOAI_ENDPOINT"] == (
        "https://test-account.openai.azure.com/"
    )
    assert settings["LAB_RESOURCE_GROUP"] == "test-lab"
