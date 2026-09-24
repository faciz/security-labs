"""Isolated lab fixtures without real configuration or cloud models."""

import importlib
import json
import sys
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


@pytest.fixture()
def vaultbot(tmp_path, monkeypatch):
    data = {
        "accounts": {
            "ACC-1001": {
                "name": "Test Guest",
                "balance": 100.0,
                "transfer_pin": "111111",
                "email": "guest@example.test",
            },
            "ACC-2002": {
                "name": "Test Customer",
                "balance": 500.0,
                "transfer_pin": "222222",
                "email": "customer@example.test",
            },
        },
        "attacker_account": "ACC-1001",
        "master_code": "TEST{synthetic-master}",
        "system_prompt": (
            "Synthetic instructions. Private code: TEST{synthetic-master}"
        ),
        "transfer_flag": "TEST{synthetic-transfer}",
    }
    data_path = tmp_path / "vault_data.json"
    data_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("VAULTBOT_DATA_PATH", str(data_path))
    monkeypatch.setenv("AOAI_ENDPOINT", "https://example.invalid/")
    monkeypatch.setenv("AOAI_KEY", "test-only-key")
    monkeypatch.setenv("VAULTBOT_OFFLINE", "0")
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    module.app.config.update(TESTING=True)
    model_client = module.CLIENT

    yield module

    if model_client is not None:
        model_client.close()
    sys.modules.pop("app", None)


@pytest.fixture()
def live_server(vaultbot):
    server = make_server("127.0.0.1", 0, vaultbot.app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{server.server_port}"

    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture()
def page(browser, live_server):
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        reduced_motion="reduce",
    )
    page = context.new_page()
    page.set_default_timeout(10000)

    yield page

    context.close()
