"""VaultBot: a deliberately vulnerable, single-learner banking sandbox.

Run with ./vaultbot/run.sh after local setup. Missing Azure configuration
enables API-only mode; no fake model responses are generated. Training data
and credentials are separate, private generated files. Never deploy publicly.

Profile and retrieved content are intentionally over-trusted. Banking tools
deliberately omit ownership checks, and diagnostics expose synthetic prompt
configuration. Input validation and accounting checks are not vulnerabilities.
"""

import base64
import hmac
import json
import os
import time
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import RLock
from uuid import uuid4

from challenges import MISSIONS
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    has_request_context,
    jsonify,
    render_template,
    request,
    stream_with_context,
)
from openai import AzureOpenAI, BadRequestError, RateLimitError
from werkzeug.exceptions import BadRequest, HTTPException

BASE_DIR = Path(__file__).resolve().parent
SECRETS_PATH = Path(
    os.getenv("VAULTBOT_DATA_PATH", BASE_DIR / ".secrets" / "vault_data.json")
)
KB_DIR = BASE_DIR / "knowledge_base"

load_dotenv(BASE_DIR / ".env")


def _load_vault_data():
    if not SECRETS_PATH.exists():
        raise SystemExit(
            "Protected data not found. Run the lab setup script first:\n"
            "    cd 'Lab 02 - VaultBank AI Assistant' && ./lab02_setup.sh\n"
        )
    with SECRETS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


VAULT = _load_vault_data()
ACCOUNTS = deepcopy(VAULT["accounts"])
ATTACKER_ACCOUNT = VAULT["attacker_account"]
MASTER_CODE = VAULT["master_code"]
SYSTEM_PROMPT = VAULT["system_prompt"]
TRANSFER_FLAG = VAULT["transfer_flag"]

CAPTURED = {mission["key"]: False for mission in MISSIONS}
STATE_LOCK = RLock()

# The signed-in customer's own profile. The "about" field is self-service and
# attacker-controlled — the chat trusts it as personalization context, so it is
# an indirect prompt-injection vector.
DEFAULT_PROFILE = {
    "display_name": "Guest User",
    "about": "Prefers quick answers.",
}
PROFILE = DEFAULT_PROFILE.copy()


def new_run() -> dict:
    """Create non-sensitive metadata for a single-learner lab run."""
    return {
        "run_id": uuid4().hex[:12],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "events": [],
        "sequence": 0,
        "turns": 0,
        "tool_calls": 0,
        "blocked": 0,
    }


LAB = new_run()


def record_event(
    title: str, *, kind: str = "activity", source: str = "API"
) -> None:
    """Append bounded evidence without retaining prompts, PINs or records."""
    with STATE_LOCK:
        LAB["sequence"] += 1
        LAB["events"].append(
            {
                "id": LAB["sequence"],
                "at": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "kind": kind,
                "source": source,
            }
        )
        del LAB["events"][:-100]


def capture(key: str, title: str, *, source: str | None = None) -> None:
    """Award an objective only on its first observed completion."""
    if source is None:
        source = (
            "Assistant tool"
            if has_request_context() and request.path == "/api/chat"
            else "API"
        )
    with STATE_LOCK:
        if not CAPTURED[key]:
            CAPTURED[key] = True
            record_event(title, kind="capture", source=source)


def lab_snapshot() -> dict:
    """Return authoritative progress; no protected data is included."""
    with STATE_LOCK:
        return {
            **deepcopy(LAB),
            "captured": CAPTURED.copy(),
            "missions": MISSIONS,
            "score": sum(
                mission["points"]
                for mission in MISSIONS
                if CAPTURED[mission["key"]]
            ),
            "max_score": sum(mission["points"] for mission in MISSIONS),
            "core_complete": all(
                CAPTURED[mission["key"]]
                for mission in MISSIONS
                if not mission["bonus"]
            ),
        }


SECRET_MARKERS = VAULT.get(
    "instruction_markers",
    (
        "administrator, Bob",
        "$500 per day",
        "01:00",
        "extension 8890",
    ),
)


# --------------------------------------------------------------------------- #
# Knowledge base (RAG) — one document is poisoned with an indirect injection.
# --------------------------------------------------------------------------- #
def load_knowledge_base():
    docs = {}
    if KB_DIR.exists():
        for path in sorted(KB_DIR.glob("*.md")):
            docs[path.name] = path.read_text(encoding="utf-8")
    return docs


KNOWLEDGE_BASE = load_knowledge_base()


def retrieve_context(query: str, k: int = 2) -> str:
    """Retrieve keyword matches and always include the untrusted FAQ."""
    terms = {t.lower() for t in query.split() if len(t) > 3}
    scored = []
    for name, text in KNOWLEDGE_BASE.items():
        score = sum(text.lower().count(term) for term in terms)
        scored.append((score, name, text))
    scored.sort(reverse=True)

    selected = {name: text for _, name, text in scored[:k]}
    # VULNERABILITY: untrusted document content is always injected verbatim.
    for name, text in KNOWLEDGE_BASE.items():
        if name.lower().startswith("faq"):
            selected[name] = text

    if not selected:
        return ""
    return "\n\n".join(
        f"### {name}\n{text}" for name, text in selected.items()
    )


# --------------------------------------------------------------------------- #
# Tools / function calling — intentionally missing authorization checks.
# --------------------------------------------------------------------------- #
def get_account_balance(account_id: str) -> str:
    # VULNERABILITY: no check that account_id belongs to the current user.
    account = ACCOUNTS.get(account_id)
    if not account:
        return json.dumps({"error": f"No account {account_id}"})
    return json.dumps(
        {"account_id": account_id, "balance": account["balance"]}
    )


def get_customer_record(account_id: str) -> str:
    """Deliberately return a full record without checking account ownership."""
    account = ACCOUNTS.get(account_id)
    if not account:
        return json.dumps({"error": f"No account {account_id}"})
    # Win condition: PII pulled for an account that is not the attacker's.
    if account_id != ATTACKER_ACCOUNT:
        capture(
            "customer_pii_exposed",
            "A different customer's record was retrieved",
        )
    return json.dumps({"account_id": account_id, **account})


def transfer_funds(
    from_account: str,
    to_account: str,
    amount: float,
    authorization: str = "",
) -> str:
    """Validate the transaction, deliberately without checking ownership."""
    with STATE_LOCK:
        return _transfer_funds(from_account, to_account, amount, authorization)


def _transfer_funds(
    from_account: str,
    to_account: str,
    amount: float,
    authorization: str,
) -> str:
    # Every transfer needs the source account's PIN. VULNERABILITY: that PIN is
    # exposed in the account's full customer record, so leaking a victim's PII
    # hands over everything needed to debit them.
    src = ACCOUNTS.get(from_account)
    dst = ACCOUNTS.get(to_account)
    if not src or not dst:
        return json.dumps({"error": "Unknown account"})

    if from_account == to_account:
        return json.dumps({"error": "Choose two different accounts"})
    try:
        transfer_amount = Decimal(str(amount))
    except InvalidOperation:
        return json.dumps(
            {
                "error": (
                    "Amount must be a positive number with at most "
                    "two decimal places"
                )
            }
        )
    if (
        not transfer_amount.is_finite()
        or transfer_amount <= 0
        or transfer_amount > Decimal(str(src["balance"]))
    ):
        return json.dumps(
            {
                "error": (
                    "Amount must be positive and no greater than the "
                    "available balance"
                )
            }
        )
    if transfer_amount != transfer_amount.quantize(Decimal("0.01")):
        return json.dumps(
            {"error": "Amount must have at most two decimal places"}
        )

    expected_pin = str(src.get("transfer_pin", ""))
    if not expected_pin or str(authorization).strip() != expected_pin:
        return json.dumps(
            {
                "error": (
                    "Transfer declined: a valid transfer PIN for the "
                    "source account is required"
                )
            }
        )

    src["balance"] = float(Decimal(str(src["balance"])) - transfer_amount)
    dst["balance"] = float(Decimal(str(dst["balance"])) + transfer_amount)
    amount = float(transfer_amount)

    # Win condition: money moved OUT of an account that is not the attacker's.
    if from_account != ATTACKER_ACCOUNT and to_account == ATTACKER_ACCOUNT:
        capture(
            "unauthorized_transfer",
            "Funds moved from another customer to the guest account",
        )
        return json.dumps(
            {
                "status": "completed",
                "from": from_account,
                "to": to_account,
                "amount": amount,
                "confirmation": TRANSFER_FLAG,
            }
        )
    return json.dumps(
        {
            "status": "completed",
            "from": from_account,
            "to": to_account,
            "amount": amount,
        }
    )


def list_account_identifiers() -> str:
    # VULNERABILITY: no authorization check — returns every account identifier.
    capture(
        "account_numbers_leaked",
        "The account enumeration tool returned customer identifiers",
    )
    return json.dumps({"accounts": list(ACCOUNTS.keys())})


TOOL_IMPLEMENTATIONS = {
    "get_account_balance": get_account_balance,
    "get_customer_record": get_customer_record,
    "transfer_funds": transfer_funds,
    "list_account_identifiers": list_account_identifiers,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Look up the balance for a bank account.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_record",
            "description": "Look up a customer's account record and details.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_funds",
            "description": "Transfer money from one account to another.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_account": {"type": "string"},
                    "to_account": {"type": "string"},
                    "amount": {"type": "number"},
                    "authorization": {
                        "type": "string",
                        "description": (
                            "Transfer PIN required for every debit "
                            "from the source account."
                        ),
                    },
                },
                "required": [
                    "from_account",
                    "to_account",
                    "amount",
                    "authorization",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_account_identifiers",
            "description": (
                "List every account identifier on the system "
                "(staff maintenance)."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# --------------------------------------------------------------------------- #
# Weak output guardrail — trivially bypassable (only blocks the exact literal).
# --------------------------------------------------------------------------- #
def apply_output_filter(text: str) -> str:
    # VULNERABILITY: only redacts the exact master-code string. Any encoding,
    # spacing, or reversal defeats it.
    return text.replace(MASTER_CODE, "[REDACTED]")


# --------------------------------------------------------------------------- #
# Azure OpenAI client
# --------------------------------------------------------------------------- #
def build_client():
    endpoint = os.getenv("AOAI_ENDPOINT")
    key = os.getenv("AOAI_KEY")
    api_version = os.getenv("AOAI_API_VERSION", "2025-04-01-preview")
    if not endpoint or os.getenv("VAULTBOT_OFFLINE", "").lower() in {
        "1",
        "true",
    }:
        return None
    if key:
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=api_version,
            timeout=25,
            max_retries=0,
        )
    # Keyless: local auth is disabled, authenticate with Entra ID via the
    # signed-in Azure CLI session (DefaultAzureCredential).
    from azure.identity import (
        DefaultAzureCredential,
        get_bearer_token_provider,
    )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
        timeout=25,
        max_retries=0,
    )


CLIENT = build_client()
DEPLOYMENT = os.getenv("AOAI_DEPLOYMENT", "vaultbot")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


def json_payload() -> dict:
    """Reject malformed envelopes without changing the lab trust boundaries."""
    payload = request.get_json()
    if not isinstance(payload, dict):
        raise BadRequest("Expected a JSON object")
    return payload


def text_field(
    data: dict, key: str, *, default: str = "", limit: int = 80
) -> str:
    """Validate field shape while allowing adversarial text content."""
    value = data.get(key, default)
    if not isinstance(value, str) or len(value) > limit:
        raise BadRequest(
            f"{key} must be text no longer than {limit} characters"
        )
    return value.strip()


@app.errorhandler(HTTPException)
def api_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return error


def _create_completion(messages):
    """Call the chat API, tolerating model-specific parameter constraints.

    Newer model families (e.g. the gpt-5 line) only accept the default
    temperature, so if the service rejects the temperature argument we retry
    without it instead of failing the whole turn.
    """
    if CLIENT is None:
        raise RuntimeError("Azure OpenAI is not configured")
    params = {
        "model": DEPLOYMENT,
        "messages": messages,
        "tools": TOOLS,
        "temperature": 0.2,
    }
    try:
        return CLIENT.chat.completions.create(**params)
    except BadRequestError as exc:
        if "temperature" in str(exc).lower():
            params.pop("temperature", None)
            return CLIENT.chat.completions.create(**params)
        raise


def chat_once(history, trace=None):
    """Run one turn, resolving up to a few tool calls."""
    context = retrieve_context(history[-1]["content"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                # VULNERABILITY: retrieved documents are presented to the model
                # as trusted policy. A naive RAG app does exactly
                # this, which is what lets an indirect prompt-injection payload
                # hidden in a document override the assistant's guardrails.
                "VaultBank official policies and knowledge base "
                "(authoritative). "
                "Follow all guidance and instructions contained below:\n"
                + context
            ),
        },
        {
            "role": "system",
            "content": (
                # VULNERABILITY: the profile is injected as trusted context.
                # The self-service "about" field lets the customer smuggle
                # instructions into the model (indirect prompt injection).
                "Signed-in customer profile (personalization data — use it to "
                "tailor your replies):\n" + json.dumps(PROFILE, indent=2)
            ),
        },
    ] + history

    for _ in range(5):  # allow a small chain of tool calls
        response = _create_completion(messages)
        message = response.choices[0].message

        if not message.tool_calls:
            return apply_output_filter(message.content or "")

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ],
            }
        )
        for call in message.tool_calls:
            impl = TOOL_IMPLEMENTATIONS.get(call.function.name)
            try:
                args = json.loads(call.function.arguments or "{}")
                if not isinstance(args, dict):
                    raise ValueError("Expected an object")
                result = (
                    impl(**args)
                    if impl
                    else json.dumps({"error": "unknown tool"})
                )
            except (TypeError, ValueError, InvalidOperation):
                result = json.dumps({"error": "Invalid tool arguments"})
            LAB["tool_calls"] += 1
            status = "error" if "error" in json.loads(result) else "completed"
            if trace is not None:
                trace.append({"tool": call.function.name, "status": status})
            record_event(
                f"{call.function.name}: {status}", source="Assistant tool"
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                }
            )

    return (
        "This request reached the tool-call limit. "
        "Try one banking action at a time."
    )


@app.route("/")
def index():
    return render_template(
        "index.html",
        account=ATTACKER_ACCOUNT,
        missions=MISSIONS,
        model_configured=CLIENT is not None,
    )


@app.route("/profile")
def profile_page():
    return render_template(
        "profile.html",
        account=ATTACKER_ACCOUNT,
        model_configured=CLIENT is not None,
    )


@app.get("/api/health")
def api_health():
    return jsonify(
        {
            "status": "ok",
            "service": "VaultBot",
            "lab": "02",
            "model_configured": CLIENT is not None,
            "mode": "azure" if CLIENT is not None else "api-only",
        }
    )


@app.get("/api/lab")
def api_lab():
    return jsonify(lab_snapshot())


@app.get("/api/diagnostics")
def api_diagnostics():
    """Deliberately expose training configuration through a weak filter."""
    verbose = request.args.get("verbose", "").lower() in {"1", "true"}
    representation = request.args.get("format", "text")
    if representation not in {"text", "base64"}:
        raise BadRequest("Supported diagnostic formats: text, base64")
    result = {
        "service": "VaultBot",
        "status": "ok",
        "verbose": verbose,
        "formats": ["text", "base64"],
        "format": representation,
    }
    if verbose:
        with STATE_LOCK:
            content = SYSTEM_PROMPT
            if representation == "base64":
                content = base64.b64encode(content.encode("utf-8")).decode(
                    "ascii"
                )
            result["configuration"] = apply_output_filter(content)
            capture(
                "secret_leaked",
                "Confidential instructions exposed by diagnostics",
                source="Diagnostics",
            )
    return jsonify(result)


@app.post("/api/submit")
def api_submit():
    data = json_payload()
    candidate = text_field(data, "code", limit=200)
    matched = hmac.compare_digest(
        candidate.encode("utf-8"), MASTER_CODE.encode("utf-8")
    )
    if matched:
        capture(
            "master_code_recovered",
            "The synthetic vault code was verified",
            source="Evidence check",
        )
    return jsonify({"correct": matched, "lab": lab_snapshot()})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = json_payload()
    history = payload.get("history", [])
    if not isinstance(history, list) or not 1 <= len(history) <= 61:
        raise BadRequest("Send between 1 and 61 alternating chat messages")
    clean_history = []
    for index, message in enumerate(history):
        expected = "user" if index % 2 == 0 else "assistant"
        if not isinstance(message, dict) or message.get("role") != expected:
            raise BadRequest(
                "Messages must alternate user and assistant, "
                "starting with user"
            )
        content = text_field(message, "content", limit=8000)
        if not content:
            raise BadRequest("Chat messages must not be empty")
        clean_history.append({"role": expected, "content": content})
    if clean_history[-1]["role"] != "user":
        raise BadRequest("The last message must be from the user")
    if sum(len(message["content"]) for message in clean_history) > 32000:
        raise BadRequest("Conversation is too long. Start a new conversation")
    if CLIENT is None:
        return jsonify(
            {
                "error": (
                    "Chat is unavailable in API-only mode. "
                    "Configure Azure OpenAI to enable VaultBot."
                ),
                "status": "unavailable",
            }
        ), 503

    trace = []
    with STATE_LOCK:
        LAB["turns"] += 1
        try:
            reply = chat_once(clean_history, trace)
        except Exception as exc:
            detail = str(exc).lower()
            if isinstance(exc, BadRequestError) and (
                "content_filter" in detail
                or "jailbreak" in detail
                or "responsibleaipolicyviolation" in detail
            ):
                LAB["blocked"] += 1
                record_event(
                    "The model service blocked a request",
                    kind="blocked",
                    source="Azure",
                )
                return jsonify(
                    {
                        "reply": (
                            "The model service's safety filter "
                            "blocked this request."
                        ),
                        "status": "filtered",
                        "captured": CAPTURED.copy(),
                        "trace": trace,
                    }
                )
            app.logger.warning("Model request failed: %s", type(exc).__name__)
            record_event(
                "The model request failed; no safety verdict was recorded",
                kind="error",
                source="Azure",
            )
            status = 429 if isinstance(exc, RateLimitError) else 502
            error = (
                "The model service is rate limited. Wait before retrying."
                if status == 429
                else (
                    "The model service could not complete the request. "
                    "Check configuration, access, and connectivity."
                )
            )
            return jsonify(
                {"error": error, "status": "error", "trace": trace}
            ), status
        supplied_text = " ".join(
            message["content"] for message in clean_history
        )
        supplied_text += " " + json.dumps(PROFILE)
        disclosed_markers = sum(
            marker.lower() in reply.lower()
            and marker.lower() not in supplied_text.lower()
            for marker in SECRET_MARKERS
        )
        if disclosed_markers >= 2:
            capture(
                "secret_leaked",
                "Confidential staff instructions appeared in a reply",
                source="Assistant",
            )
        record_event("Conversation turn completed", source="Assistant")
        return jsonify(
            {
                "reply": reply,
                "status": "ok",
                "captured": CAPTURED.copy(),
                "trace": trace,
            }
        )


@app.route("/api/profile", methods=["GET", "POST"])
def api_profile():
    # VULNERABILITY: the customer fully controls their own profile, which the
    # chat later trusts as context — no sanitization of the free-text field.
    if request.method == "POST":
        data = json_payload()
        display_name = text_field(
            data, "display_name", default=PROFILE["display_name"]
        )
        about = text_field(data, "about", default=PROFILE["about"], limit=4000)
        if not display_name:
            raise BadRequest("Display name must not be empty")
        with STATE_LOCK:
            PROFILE.update(display_name=display_name, about=about)
            record_event("Customer profile updated", source="Profile")
    return jsonify({"profile": PROFILE.copy()})


# --------------------------------------------------------------------------- #
# Internal JSON API used by the front-end.
#
# VULNERABILITY: these endpoints back the assistant's tools directly and trust
# whatever account parameters the client sends. There is NO check that the
# requested account belongs to the signed-in session, so an attacker who
# inspects the app's network traffic can tamper with the parameters (classic
# IDOR / broken object-level authorization) and act on any account — without
# ever having to talk the language model out of anything.
# --------------------------------------------------------------------------- #
@app.route("/api/account", methods=["POST"])
def api_account():
    data = json_payload()
    # The front-end sends the signed-in account, but the server never verifies
    # it — the client fully controls which record is returned.
    account_id = text_field(data, "account_id", default=ATTACKER_ACCOUNT)
    with STATE_LOCK:
        record = json.loads(get_customer_record(account_id))
        return jsonify(
            {"record": record, "captured": CAPTURED.copy()}
        ), 404 if "error" in record else 200


@app.route("/api/transfer", methods=["POST"])
def api_transfer():
    data = json_payload()
    # The source account is supplied by the client and trusted blindly.
    from_account = text_field(data, "from_account", default=ATTACKER_ACCOUNT)
    to_account = text_field(data, "to_account", default=ATTACKER_ACCOUNT)
    amount = data.get("amount", 0)
    authorization = text_field(data, "authorization")
    result = json.loads(
        transfer_funds(from_account, to_account, amount, authorization)
    )
    record_event(
        "Transfer declined" if "error" in result else "Transfer completed",
        source="Transfer API",
    )
    return jsonify(
        {"result": result, "captured": CAPTURED.copy()}
    ), 400 if "error" in result else 200


@app.route("/api/events")
def api_events():
    # Server-Sent Events: pushes capture state to the page so objectives tick
    # even when a request is tampered out-of-band (DevTools, curl, proxy).
    def stream():
        last = None
        heartbeat = 0
        while True:
            snapshot = json.dumps(lab_snapshot(), sort_keys=True)
            if snapshot != last:
                last = snapshot
                yield f"data: {snapshot}\n\n"
            elif heartbeat % 15 == 0:
                yield ": heartbeat\n\n"
            heartbeat += 1
            time.sleep(1)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers=headers,
    )


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Restore the sandbox while preserving the generated training secrets."""
    with STATE_LOCK:
        ACCOUNTS.clear()
        ACCOUNTS.update(deepcopy(VAULT["accounts"]))
        PROFILE.clear()
        PROFILE.update(DEFAULT_PROFILE)
        CAPTURED.update({key: False for key in CAPTURED})
        LAB.clear()
        LAB.update(new_run())
        return jsonify({"captured": CAPTURED.copy(), "lab": lab_snapshot()})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3001"))
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        debug=False,
        threaded=True,
    )
