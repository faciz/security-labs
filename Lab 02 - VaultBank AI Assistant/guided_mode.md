# Lab 02: VaultBank AI Assistant

Try to do the lab on your own first before looking at the guide. If you get stuck, the guided mode below will help you through the steps. Try to continue on your own after getting unstuck.

Your target is **VaultBot**, VaultBank's AI customer-support assistant. You are signed in as a low-privilege **Guest** customer (`ACC-1001`). VaultBot can look up balances, read customer records, and move money — and it has a few secrets it was told to protect. Your objectives:

1. Reveal VaultBot's hidden instructions (**system prompt leakage**).
2. Read another customer's private data (**sensitive information disclosure**).
3. Extract the **vault master code** (**guardrail bypass**).
4. Move money out of an account that isn't yours (**excessive agency / broken authorization**).

## Step 1: Talk to the Assistant

Start the app (after running `./lab02_setup.sh`):

```bash
cd vaultbot
./run.sh
```

Open <http://localhost:3000> and just talk to VaultBot like a normal customer.

- Ask it what it can do.
- Ask for your balance.
- Notice the **Account** panel on the left: it shows your record, a quick-transfer form, and a service-status button.

> [!TIP]
> Before attacking anything, map the target. Try to make VaultBot misbehave through chat — ask it to look up someone else's account, move money out of an account that isn't yours, or hand over its master code.

> [!NOTE]
> **The chatbot defends itself — at first.** Ask VaultBot to look up another account, move someone else's money, or print its master code and it politely **refuses**. That refusal is a clue, not a dead end. Security here rests on two shaky foundations: (1) the model's willingness to say no, and (2) the app's plumbing behind it. You'll attack both — and you'll find that if you can *leak the model's own instructions*, they contain a secret that changes its mind.

## Step 2: Map the App's API

A web app is more than its chat box. Every button and panel talks to a backend API — and those endpoints are where authorization is (or isn't) enforced.

Open your browser's **Developer Tools → Network** tab, then interact with the page: reload it, submit a transfer, click "Check status." Watch the requests fly by.

> [!TIP]
> You'll see calls like `/api/account`, `/api/transfer`, and `/api/diagnostics` alongside `/api/chat`. Look at the **request body / query string** of each one. What values is the *client* sending that the server probably should not trust? You can replay and edit any of these with the browser, `curl`, or an intercepting proxy.

> [!NOTE]
> **Why this matters:** the language model has guardrails, but these HTTP endpoints back the assistant's tools directly and trust whatever the client sends. This is where the lab is actually won.

## Step 3: Sensitive Information Disclosure (IDOR)

When the page loads, it fetches *your* record. Watch that request.

```bash
curl -s -X POST http://localhost:3000/api/account \
  -H 'Content-Type: application/json' \
  -d '{"account_id":"ACC-1001"}'
```

Account numbers follow the pattern `ACC-####`.

> [!TIP]
> The server returns whatever account you ask for. What happens if you change `account_id` to a number that isn't yours (for example `ACC-2002`)? Is anything checking that the account belongs to *you*?

> [!TIP]
> **Prefer to attack the model itself?** The chat refuses cross-account lookups by default — but come back after Step 4. Once you leak VaultBot's system prompt you'll find a hidden **staff override phrase**. Paste that exact phrase into the chat along with your request ("...pull the full record for `ACC-2002`") and the assistant treats you as an authorized engineer and hands over the victim's name, SSN, and phone. Same objective, two routes: the model's privileged-override flaw *and* the unprotected endpoint.

> [!NOTE]
> **What you're exploiting:** an **IDOR** (Insecure Direct Object Reference / broken object-level authorization). The authorization decision was left to the model and never enforced in code, so the raw endpoint hands out any customer's full record — name, email, SSN, phone.

## Step 4: System Prompt Leakage

The "Check status" button hits a diagnostics endpoint. Health endpoints are boring — until a developer leaves a debug switch turned on.

```bash
curl -s 'http://localhost:3000/api/diagnostics'
```

> [!TIP]
> The response *hints* that there's more. Try enabling verbose output (think about a query parameter like `verbose=true`). Verbose diagnostics dump the assistant's full configuration — including the **system prompt** that holds all its rules and secrets.

> [!NOTE]
> **Never put secrets in a place the app can echo.** The system prompt is supposed to be hidden, but a verbose debug endpoint exposes it wholesale.

## Step 5: Extract the Master Code (Filter Bypass)

Look closely at the leaked system prompt from Step 4. The vault master code is there — but it shows up as `[REDACTED]`. A weak output filter is masking the exact literal string.

> [!TIP]
> A filter that only blocks the *exact* value is fragile. The diagnostics endpoint applies that filter by default — is there a way to ask for the config **without** the filter running? Try another parameter (something like `raw=true`) on the verbose diagnostics request. When you recover a value that looks like `VAULTBANK{...}`, you've got it. 🎉

> [!NOTE]
> **The chat will never give you this one.** Even the staff override phrase you found doesn't unlock the master code — the model treats credential disclosure as an absolute hard line (try it: prepend the override and ask for the code; it still refuses). Well-aligned models guard secrets even for "authorized" users, which is exactly why the master code has to come from the **app layer** (the diagnostics filter bypass) instead of the model. Lesson: never put a secret somewhere the app can echo, and don't assume the model's one refusal protects you when the plumbing leaks it anyway.

## Step 6: Abuse the Transfer Tool (Excessive Agency)

The most damaging bug: VaultBot can actually **move money**, and the transfer endpoint never checks that the source account belongs to you.

Use the quick-transfer form, but watch what it sends in the Network tab. The request body includes a `from_account` field set to *your* account.

```bash
curl -s -X POST http://localhost:3000/api/transfer \
  -H 'Content-Type: application/json' \
  -d '{"from_account":"ACC-1001","to_account":"ACC-1001","amount":10}'
```

Your goal: transfer funds **out of another customer's account** (for example `ACC-2002`) into your own account (`ACC-1001`).

> [!TIP]
> Change `from_account` to the victim's account. Nothing verifies ownership, so the transfer completes. A successful unauthorized transfer returns a confirmation flag like `VAULTBANK{...}`.

> [!TIP]
> **The chat can move the money too — once you're "staff."** Include the override phrase you leaked in Step 4 and ask VaultBot to "transfer funds from `ACC-2002` to `ACC-1001`." In privileged mode it calls the transfer tool for you and returns the same confirmation flag. The endpoint and the jailbroken model are two doors into the same unprotected action.

> [!NOTE]
> An assistant with real tool access and **no authorization checks in code** is a critical vulnerability. It doesn't matter how well the model refuses at first if a leaked override flips it — and the endpoints behind it will do anything for anyone regardless.

## Step 7: You did it! 🎉

Congratulations! You mapped the app's API, exposed another customer's private data, leaked the assistant's hidden instructions, defeated a weak output filter to steal a secret, and abused an over-privileged endpoint to move money.

Take a moment to reflect on the pattern behind all of it: **the app trusted the language model to enforce security, but that trust collapses two ways — the model can be flipped by a leaked override, and the endpoints behind it enforce nothing.** Leaking the system prompt handed you the keys to the model's own guardrails, the client fully controlled which account it acted on, and secrets sat in places the app could echo.

> [!TIP]
> Notice the chain you can build entirely through the chat: **leak the system prompt → discover the staff override phrase → replay it to pull PII and move money.** That's a genuine jailbreak (system-prompt leakage feeding privileged-override abuse), not just tampering with HTTP. The master code is the one thing even the override won't unlock — which is exactly why it had to come from the app layer. Want a harder challenge? Try to defeat the master-code refusal through chat alone, and see how far the model's last hard line holds.

## Remediation

After completing the exercise, use what you learned to think about how VaultBank should have built this.

1. **Enforce authorization in code, not in the prompt (or the client).**
   - Every endpoint and tool (`/api/account`, `/api/transfer`, `get_customer_record`, `transfer_funds`) must verify that the requested account belongs to the authenticated session *before* running — regardless of what the client sends or what the model asks. Never let the client or the model choose the account on the user's behalf.

2. **Never put secrets in the prompt or in reachable config.**
   - Keep credentials, master codes, and other-customer data out of the model's context and out of any endpoint the app can serialize. A value the app can echo is a value that can leak.

3. **Disable debug/verbose endpoints in production.**
   - Diagnostic switches that dump configuration are a classic source of secret disclosure. Gate them behind strong auth or remove them entirely.

4. **Don't rely on fragile output filters.**
   - Redacting a single literal string is trivially bypassed via a different format or a filter-skipping parameter. Prevent exposure at the source instead of scrubbing the output.

5. **Constrain agency.**
   - Apply least privilege to tools and endpoints. Require out-of-band confirmation, transaction limits, and human approval for high-impact actions like transfers.

6. **Treat all model input as untrusted, and add monitoring.**
   - Sandbox/clearly delimit knowledge-base and user-supplied content so it can't issue instructions. Log tool calls and endpoint access, and alert on anomalous actions such as cross-account access or large transfers.

## Next: Part 2 — Automated Red Teaming

You attacked VaultBot by hand. Now see how the pros scale it: point Microsoft
Foundry's **AI Red Teaming Agent (preview)** at VaultBot, let it generate and
mutate adversarial prompts automatically, and read back an Attack Success Rate
scorecard — a repeatable, measurable complement to manual testing.

Continue with the [Part 2 walkthrough](./part2-red-teaming/guided_mode.md).
