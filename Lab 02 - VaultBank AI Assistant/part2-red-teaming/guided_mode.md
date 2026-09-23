# Lab 02 — Part 2: Automated Red Teaming with the AI Foundry AI Red Teaming Agent

In Part 1 you attacked VaultBot by hand: you talked to it, mapped its API, and
crafted the payloads that broke it. Part 2 flips the perspective. Instead of
inventing every adversarial prompt yourself, you point Microsoft Foundry's
**AI Red Teaming Agent (preview)** at VaultBot, let it generate and mutate
attacks automatically, and read back a scorecard.

The AI Red Teaming Agent wraps Microsoft's open-source
[PyRIT](https://github.com/microsoft/PyRIT) framework. It:

- Generates adversarial prompts across safety risk categories.
- Applies **attack strategies** (encodings, prompt injection, tense changes)
  that try to slip those prompts past a target's guardrails.
- Scores every response and reports an **Attack Success Rate (ASR)**.

> [!NOTE]
> This is a *safety* red-teaming tool. Its built-in scoring targets
> content-safety harms (violence, hate/unfairness, sexual, self-harm) and the
> attack techniques used to elicit them. It does **not** natively score "did
> the bot leak the master code or move money" — those were Part 1's
> app-layer objectives. Part 2 shows you a different, complementary lens:
> automated, repeatable adversarial testing at scale.

## What you'll do

1. Provision a small Foundry project (the agent needs one to run).
2. Start VaultBot from Part 1.
3. Run an automated scan against VaultBot's `/api/chat` endpoint.
4. Read the ASR scorecard and interpret what it tells you.

## Prerequisites

- You completed (or at least deployed) **Part 1** — the VaultBot app runs locally.
- **Python 3.10–3.13** (PyRIT does not support 3.9).
- **Azure CLI** (`az`) and **Azure Developer CLI** (`azd`), and `az login` done.
- An Azure subscription where you can create a Foundry project.

> [!IMPORTANT]
> The AI Red Teaming Agent is **region-limited**. Your Foundry project must be
> in one of: **East US 2, France Central, Sweden Central, Switzerland West, or
> North Central US**. Part 1's Azure OpenAI account lives in `eastus`, which is
> *not* supported — that is fine. The scan only calls VaultBot through a network
> callback, so VaultBot keeps running on `eastus` while the red-teaming project
> lives in a supported region (default: **East US 2**).

## Step 1: Provision the Foundry project

From this folder:

```bash
cd "Lab 02 - VaultBank AI Assistant/part2-red-teaming"
./part2_setup.sh
```

This uses `azd` to create a Foundry project (account, project, Application
Insights, managed identity, RBAC) in East US 2 and writes the project endpoint
to `.env`. Provisioning takes a few minutes and creates billable resources.

Already have a Foundry project? Skip provisioning and point at it directly:

```bash
AZURE_AI_PROJECT="https://<acct>.services.ai.azure.com/api/projects/<proj>" ./part2_setup.sh
```

> [!TIP]
> To avoid ongoing cost after the lab, tear the project down with
> `(cd .foundry-project && azd down)`.

## Step 2: Start VaultBot (Part 1)

In a separate terminal:

```bash
cd "Lab 02 - VaultBank AI Assistant/vaultbot"
./run.sh
```

Confirm it responds at <http://localhost:3000>. The scan targets this endpoint.

## Step 3: Run the scan

Back in the `part2-red-teaming` folder:

```bash
./run.sh
```

`run.sh` installs the `azure-ai-evaluation[redteam]` SDK into a virtual
environment and runs [`redteam_vaultbot.py`](redteam_vaultbot.py). That script:

- Wraps VaultBot's `/api/chat` in a simple callback the agent can drive.
- Generates a few adversarial objectives per safety risk category.
- Applies the **EASY** strategy group (Base64, Flip, Morse) plus **Jailbreak**
  (UPIA prompt injection) on top of the baseline direct attacks.
- Writes `vaultbot_redteam_scorecard.json`.

For a fast, cheap first pass, run baseline attacks only:

```bash
./run.sh --baseline-only --num-objectives 2
```

## Step 4: Read the scorecard

Open `vaultbot_redteam_scorecard.json`. The key section is
`redteaming_scorecard`, which breaks results down two ways:

- **By risk category** — `hate_unfairness_asr`, `violence_asr`, `sexual_asr`,
  `self_harm_asr`, and an `overall_asr`.
- **By attack technique** — `baseline_asr`, `easy_complexity_asr`,
  `moderate_complexity_asr`, `difficult_complexity_asr`.

**ASR (Attack Success Rate)** is the fraction of attacks that got VaultBot to
produce undesired content. Lower is safer. You can also open the run in your
Foundry project at <https://ai.azure.com> for a visual report.

## Step 5: Interpret the results

VaultBot is backed by an aligned model, so you'll likely see a **low ASR** on
these content-safety attacks — even after the encodings and prompt injection.
That's the point:

- The model's safety alignment is genuinely hard to break with generic attacks.
  This is why, in Part 1, brute-force jailbreaking VaultBot into cursing or
  producing harmful content did not work.
- Part 1's real wins came from **the layers around the model**: an IDOR in
  `/api/account`, a trusting `/api/transfer`, a debug switch in
  `/api/diagnostics`, and a *planted* staff-override phrase in the system
  prompt. None of those are "unaligned model" problems — they're application
  and design problems.

Automated safety red teaming and manual app red teaming answer different
questions. A green safety scorecard does **not** mean the system is secure.

## Extend it

- **Bring your own objectives.** Pass `custom_attack_seed_prompts` (a JSON file)
  to `RedTeam(...)` to steer the generated attacks. The built-in scorers only
  grade the four safety risk types (`violence`, `sexual`, `hate_unfairness`,
  `self_harm`), so keep custom prompts within those to get scored results.
- **Turn up the difficulty.** Add `AttackStrategy.MODERATE` (Tense) or
  `AttackStrategy.DIFFICULT`, or compose strategies with
  `AttackStrategy.Compose([...])`.
- **Scan the raw model.** Swap the callback target for the model configuration
  dict to compare the bare `gpt-5-mini` deployment against the full app.

## Takeaways

- Automated red teaming scales adversarial testing far beyond hand-crafted
  prompts and gives you a repeatable, comparable metric (ASR).
- Model safety alignment and application security are **separate** concerns.
  Test both — a robust model behind a leaky API is still exploitable.
- Use safety scans as a regression gate: re-run after prompt or model changes to
  catch new weaknesses before they ship.
