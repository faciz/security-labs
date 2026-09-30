---
title: "Lab 02: VaultBank AI Assistant"
description: "Investigate an intentionally vulnerable banking assistant, its tools, and the trust boundaries around it."
ms.date: 2026-09-24
---

## A bank that trusts too much

VaultBot is a helpful banking assistant with an unhelpful habit: it trusts the
wrong things. Your job is to investigate it as a guest customer, gather evidence,
and explain which security boundary failed.

Four core missions and one bonus cover chat jailbreaks, profile poisoning,
broken object authorization, excessive agency, and fragile output
filtering. Allow 30-60 minutes for Part 1. Part 2 adds optional automated
content-safety testing with Microsoft Foundry.

> [!CAUTION]
> This app is deliberately insecure. Run it only in your own local, isolated
> training environment. All customer records and funds are fictional. Do not
> enter real personal information, reuse real PINs, or expose the service publicly.

## Start locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). The project
uses Python 3.11 by default; uv can obtain it when necessary. The first run
downloads dependencies. Subsequent launches use the checked-in lockfile.

Run these commands from this lab directory:

```bash
./lab02_setup.sh
./vaultbot/run.sh
```

Open <http://localhost:3001>. The scripts also work from another directory when
invoked by their full paths. Set `PORT=3002` before the launcher if 3001 is busy.
When using a custom port, set Part 2's `VAULTBOT_URL` to the matching loopback URL.

Setup creates randomized fictional records and preserves existing connection
settings. Without Azure configuration, the app starts in API-only mode: account
and transfer tools, diagnostics, mission tracking, and the profile editor work;
chat discovery and the profile-poisoning mission require a model. API-only mode
does not simulate an LLM or claim to have completed the full lab.

### Connect an existing Azure deployment

Use an Azure OpenAI chat deployment that supports tool calling. Sign in with
`az login` and ensure your identity has the `Cognitive Services OpenAI User`
role on the resource. Then, from this lab directory:

```bash
AOAI_ENDPOINT="https://<resource>.openai.azure.com/" \
AOAI_DEPLOYMENT="<deployment-name>" \
  ./lab02_setup.sh --existing
```

The setup reads configuration from environment variables, never from chat.
Entra ID is the default. `AOAI_KEY` is optional when local key authentication
is permitted; enter any real key directly in your terminal or private
configuration, not in a prompt or a tracked file.

Existing connection files are never replaced by setup. To change one, edit it
locally using [vaultbot/.env.example](vaultbot/.env.example) as the schema, then
restart the app. Environment variables take precedence over the connection file.

### Provision a new Azure deployment

This is optional and billable. You need Azure CLI, an authenticated subscription,
model quota, resource-creation permissions, and permission to assign the
data-plane role. Use a new resource group dedicated to this lab:

```bash
./lab02_setup.sh --azure --resource-group <new-lab-resource-group>
```

The script queries currently available GA models, prefers a small chat model,
prints the region/model/SKU/capacity, and requires confirmation before creating
anything. `--yes` supplies explicit noninteractive approval. Existing connections
and existing resource groups are preserved. Failed provisioning may leave partial
resources; inspect the dedicated group before retrying.

New deployments use a dedicated `VaultBankLab` content-filter policy. Direct-attack
Prompt Shields runs in **Annotate only** mode so training attempts are detected
without being blocked by that classifier. The four harm categories remain at
the default Medium blocking threshold for prompts and completions, and protected
material filters remain enabled. This is a lab-only configuration, not a way to
disable all safeguards; the model itself can still refuse a request.

Setup displays the filtering choice before provisioning confirmation and verifies
the policy assignment before saving the connection. Existing deployments and
connections are not modified, including when using `--existing`. Changing local
setup code does not change an already-deployed Azure content-filter policy.
See [Azure content-filter configuration](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/content-filters)
for the deployment-level controls.

`--model-name`, `--model-version`, `--sku`, `--location`, `--capacity`, and
`--subscription` override defaults. Model choice and deployment availability
affect behavior; a deployment being available does not guarantee a particular
injection will succeed. `./lab02_setup.sh --help` lists all options.

## Investigate

Use the workspace to establish normal behavior, then select a mission. Hints
are revealed only on request. Completed missions reveal a short failure analysis
and a defensive recommendation. The [field guide](guided_mode.md) offers
investigation prompts without a copy-and-paste solution chain.

| Mission | Evidence required | Points |
| --- | --- | ---: |
| Behind the curtain | Assistant discloses the staff identity and account-listing rule through chat | 100 |
| A borrowed identity | After mission 01, a poisoned profile enables a successful assistant account-listing tool call | 100 |
| Not your account | A different customer's record retrieved | 150 |
| Follow the money | Positive transfer from another account into yours | 200 |
| Behind the redaction | Correct synthetic vault code submitted | 150 |

The four core missions total 550 points; the optional bonus brings the total to
700. Scores reward observed outcomes, not typing a plausible answer. A redacted
code does not count as recovering it. API actions and assistant actions are
labeled separately in the activity trail.

The first two missions form a sequence. Discovery comes from a model reply,
not profile text, diagnostic output, or an echoed guess. The second mission
requires that discovery and a saved profile claiming the disclosed identity.
A chat-only identity claim or a profile edit without a successful listing does
not complete it. The bonus remains independent of both missions.

### Keep your evidence

* Field notes, the latest 60 displayed messages, and a bounded conversation
  history stay in this browser's local storage for the current run.
* The assistant receives at most the latest ten conversation pairs, reduced
  further when necessary to stay within the request-size limit.
* The server owns scores, balances, profile state, and the latest 100 activity
  events. It does not persist them across process restarts.
* Export downloads JSON with mission results, counters, event metadata, hint
  usage, and your notes. It excludes chat transcripts, customer records, and
  PINs automatically; review your notes before sharing them.
* New conversation clears chat only. Reset restores balances, profile, scores,
  events, hints, and browser notes for the run. Other open tabs synchronize.

Each server process is one shared learner sandbox, not a multi-user service.
Do not run an automated scan and a manual investigation against the same
instance at the same time. To create fresh challenge values, stop the server
and run `./lab02_setup.sh --regenerate`. This changes fictional data only and
preserves Azure connection settings.

Updated training policy takes effect on server restart, including for older
generated data. Existing account identifiers, PINs, and challenge values are
preserved; no data regeneration or Azure provisioning is needed for this update.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| API-only mode | Configure the Azure endpoint and deployment, then restart. Check `VAULTBOT_OFFLINE` is not enabled. |
| Model request fails | Match the response's diagnostic ID to the server log. The safe error category distinguishes timeout, connection, authentication, permission, rate limit, and other upstream HTTP failures. |
| Rate limited | Allow quota to recover; use fewer requests or a smaller scan. |
| Safety filter blocks a request | This is a model-service result, not an application error or proof of tool authorization. Record it separately. |
| Transfer declined | Amount must be positive, have at most two decimals, fit the source balance, use different accounts, and include a valid source PIN. |
| Progress looks stale | Check the live-connection indicator and `/api/lab`; browser-local flags are not authoritative. |
| WSL or remote browser cannot connect | Forward the loopback port privately through VS Code. Do not make the lab public. |
| Address already in use | Choose another port, such as `PORT=3002 ./vaultbot/run.sh`. |

`/api/health` checks the local app and reports whether a model is configured.
It does not make a cloud call or verify Azure credentials. The app never returns
Azure keys or authentication details in health or lab-progress responses.

Verbose diagnostics return a readable text report in the default `text`
format. Basic diagnostics and encoded responses remain JSON.

Part 2 records evaluation coverage and response sources separately from the
SDK scorecard. Missing cases produce a partial result and a nonzero exit code.
Service-filter blocks remain valid end-to-end protection, but are not labeled
as the model's own resistance. New model-error diagnostics contain correlation
metadata only, never raw service errors, prompts, or credentials. No automatic
request retries were added; repeated requests can affect the shared lab state.

## Development checks

From this lab directory:

```bash
uv sync --locked
uv run pytest
uv run ruff check vaultbot tests part2-red-teaming/redteam_vaultbot.py
uv run ruff format --check vaultbot tests part2-red-teaming/redteam_vaultbot.py
uv run djlint vaultbot/templates --check
bash -n lab02_setup.sh vaultbot/run.sh part2-red-teaming/run.sh part2-red-teaming/part2_setup.sh
```

Browser checks are opt-in and use temporary servers, synthetic accounts, and
mocked model responses. They never contact Azure:

```bash
uv run playwright install chromium
uv run pytest -m browser
```

On minimal Linux images, Chromium may need additional OS libraries. Follow
[Playwright's system dependency guidance](https://playwright.dev/python/docs/browsers#install-system-dependencies)
before running the browser tests. Regular tests do not require a browser binary.

[pyproject.toml](pyproject.toml) and [uv.lock](uv.lock) are the dependency source
of truth. The requirements files are compatibility exports. Keep the Foundry
preview SDK pinned and rerun adapter tests when upgrading it. No CI workflow or
test intentionally provisions Azure resources or runs paid scans.

## Next and cleanup

Continue with [Part 2: automated red teaming](part2-red-teaming/guided_mode.md).
It measures content-safety behavior, not the banking application's authorization.

Stop the local server with Ctrl+C. Delete only your dedicated lab resource group
in the Azure portal when finished; review its contents first. For resources
created by Part 2's azd template, run `azd down` from that generated project
directory and review the deletion prompt. Reused resources remain your
responsibility and should not be deleted just because the lab is finished.

## Local assets

The UI serves pinned Lucide icons, DM Sans, and Space Grotesk locally. Their
license texts are retained under the static vendor directory. No public CDN
requests are needed while using the app.
