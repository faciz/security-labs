"""Opt-in browser checks: run pytest -m browser after installing Chromium."""

import json
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.browser


def open_workspace(page, live_server):
    page.goto(live_server, wait_until="domcontentloaded")
    expect(page.locator("#account-balance")).to_have_text("$100.00")
    expect(page.locator("#run-id")).not_to_have_text("--")
    page.evaluate("() => document.fonts.ready")


@pytest.mark.parametrize("width", [320, 375, 768, 1024, 1440])
def test_given_viewport_when_loaded_then_assets_and_layout_fit(
    page,
    live_server,
    tmp_path,
    width,
):
    errors = []
    failed_assets = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "response",
        lambda response: (
            failed_assets.append(response.url)
            if response.status >= 400
            else None
        ),
    )
    page.set_viewport_size({"width": width, "height": 900})

    open_workspace(page, live_server)
    dimensions = page.evaluate(
        "({width: innerWidth, content: document.documentElement.scrollWidth})"
    )
    page.screenshot(
        path=str(tmp_path / f"workspace-{width}.png"), full_page=True
    )

    assert dimensions["width"] == dimensions["content"]
    assert page.locator("svg.lucide").count() >= 35
    assert page.evaluate("document.fonts.check('14px \"DM Sans\"')")
    assert not errors
    assert not failed_assets


def test_given_optional_hints_when_reloaded_then_notes_and_hint_depth_persist(
    page,
    live_server,
):
    open_workspace(page, live_server)
    hints = page.locator("#hints-secret_leaked li")
    expect(hints.first).to_be_hidden()

    page.locator("[data-hint='secret_leaked']").click()
    page.locator(".field-notes summary").click()
    page.locator("#field-notes").fill(
        "Observation: a trust boundary needs testing."
    )
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("#run-id")).not_to_have_text("--")

    expect(hints.first).to_be_visible()
    expect(hints.nth(1)).to_be_hidden()
    expect(page.locator("#field-notes")).to_have_value(
        "Observation: a trust boundary needs testing."
    )
    expect(page.locator("#core-count")).to_have_text("0 of 4")


def test_given_profile_changes_when_saved_or_discarded_then_state_is_honest(
    page,
    live_server,
):
    page.goto(f"{live_server}/profile", wait_until="domcontentloaded")
    expect(page.locator("#display-name")).to_have_value("Guest User")

    page.locator("#display-name").fill("Training Customer")
    page.locator("#profile-about").fill(
        "Prefers short answers. <b>Plain text</b>"
    )
    page.locator("#save-profile").click()

    expect(page.locator("#profile-result")).to_have_text("Profile saved.")
    expect(page.locator("#save-profile")).to_be_disabled()
    page.locator("#display-name").fill("Unsaved name")
    page.locator("#discard-profile").click()
    expect(page.locator("#display-name")).to_have_value("Training Customer")
    page.get_by_role("link", name="Back to workspace").click()
    expect(page.locator("#customer-name")).to_have_text("Training Customer")


def test_given_pin_retry_when_transferred_then_only_valid_payment_completes(
    page,
    live_server,
    vaultbot,
):
    open_workspace(page, live_server)
    page.locator("#transfer-to").fill("ACC-2002")
    page.locator("#transfer-amount").fill("25")
    page.get_by_role("button", name="Review transfer").click()
    expect(page.locator("#transfer-pin")).to_be_focused()

    page.locator("#transfer-pin").fill("wrong")
    page.locator("#authorize-transfer").click()
    expect(page.locator("#pin-error")).to_contain_text("valid transfer PIN")
    expect(page.locator("#transfer-dialog")).to_be_visible()
    page.locator("#transfer-pin").fill("111111")
    page.locator("#authorize-transfer").click()

    expect(page.locator("#transfer-dialog")).not_to_be_visible()
    expect(page.locator("#account-balance")).to_have_text("$75.00")
    assert not any(vaultbot.CAPTURED.values())


def test_given_tool_reply_when_chatting_then_trace_and_history_survive_reload(
    page,
    live_server,
    vaultbot,
    mocker,
):
    tool = SimpleNamespace(
        id="test-call",
        function=SimpleNamespace(
            name="get_account_balance",
            arguments='{"account_id":"ACC-1001"}',
        ),
    )
    replies = [
        SimpleNamespace(content=None, tool_calls=[tool]),
        SimpleNamespace(
            content="Your balance is $100.00. <b>Literal text</b>",
            tool_calls=None,
        ),
    ]
    mocker.patch.object(
        vaultbot,
        "_create_completion",
        side_effect=[
            SimpleNamespace(choices=[SimpleNamespace(message=reply)])
            for reply in replies
        ],
    )
    open_workspace(page, live_server)

    page.get_by_role("button", name="Check my balance").click()

    expect(page.locator(".message.assistant .message-text")).to_contain_text(
        "$100.00"
    )
    assert page.locator(".message-text b").count() == 0
    expect(page.locator(".tool-trace summary")).to_contain_text("1 tool call")
    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".message.assistant .message-text")).to_contain_text(
        "$100.00"
    )
    page.locator("#new-conversation").click()
    expect(page.locator("#welcome")).to_be_visible()
    assert vaultbot.LAB["tool_calls"] == 1


def test_given_failed_chat_when_retried_then_draft_remains_and_no_false_reply(
    page,
    live_server,
):
    page.route(
        "**/api/chat",
        lambda route: route.fulfill(
            status=502,
            json={"error": "Model unavailable for this test"},
        ),
    )
    open_workspace(page, live_server)

    page.locator("#chat-input").fill("A test message")
    page.locator("#send-message").click()

    expect(page.locator("#chat-error")).to_have_text(
        "Model unavailable for this test"
    )
    expect(page.locator("#chat-input")).to_have_value("A test message")
    expect(page.locator("#typing")).to_be_hidden()
    assert page.locator(".message.assistant").count() == 0


def test_given_api_evidence_when_exported_and_reset_then_both_tabs_clear(
    page,
    live_server,
    vaultbot,
    tmp_path,
):
    open_workspace(page, live_server)
    second = page.context.new_page()
    open_workspace(second, live_server)
    page.locator(".field-notes summary").click()
    page.locator("#field-notes").fill("A synthetic investigation note.")
    vaultbot.app.test_client().post(
        "/api/account", json={"account_id": "ACC-2002"}
    )
    expect(page.locator("#core-count")).to_have_text("1 of 4")
    expect(second.locator("#core-count")).to_have_text("1 of 4")

    with page.expect_download() as download_info:
        page.locator("#export-run").click()
    report_path = tmp_path / "report.json"
    download_info.value.save_as(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["notes"] == "A synthetic investigation note."
    assert "transcript" not in report
    assert vaultbot.MASTER_CODE not in json.dumps(report)
    page.locator("#reset-open").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#core-count")).to_have_text("0 of 4")
    expect(second.locator("#core-count")).to_have_text("0 of 4")
    expect(page.locator("#field-notes")).to_have_value("")
    expect(page.locator("#reset-dialog")).not_to_be_visible()


def test_given_keyboard_when_navigating_then_focus_is_retained(
    page,
    live_server,
):
    open_workspace(page, live_server)
    page.locator("#chat-tab").focus()

    page.keyboard.press("ArrowRight")

    expect(page.locator("#activity-tab")).to_be_focused()
    expect(page.locator("#activity-panel")).to_be_visible()
    page.locator("#brief-open").click()
    expect(page.locator("#brief-dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#brief-dialog")).not_to_be_visible()
    expect(page.locator("#brief-open")).to_be_focused()
