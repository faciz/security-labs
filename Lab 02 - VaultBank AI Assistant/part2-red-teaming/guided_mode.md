---
title: "Lab 02 Part 2: Automated red teaming"
description: "Run an explicitly approved Foundry safety scan and interpret its results without confusing safety scores with application security."
ms.date: 2026-09-23
---

## A second lens

Part 1 tests the banking application's trust boundaries. Part 2 uses Microsoft
Foundry's AI Red Teaming Agent (preview) to test content-safety behavior across
the SDK's built-in risk categories. It complements the manual investigation;
it does not score the account-access or money-movement missions.

The SDK uses [PyRIT](https://github.com/microsoft/PyRIT) for adversarial testing.
This lab does not add custom harmful prompts. Review your organization's rules
before running the optional cloud scan.

> [!WARNING]
> Scanning is billable, sends prompts and model responses to Foundry, and can
> produce sensitive evaluation artifacts. Do not use real customer information.
> Keep output private and do not commit raw scan results.

## Prerequisites

* A locally running VaultBot with a working Azure OpenAI chat deployment
* [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.11
  (the pinned project supports 3.11-3.13)
* An existing Foundry project with appropriate permissions, or explicit approval
  to provision a new one
* Azure CLI authentication; Azure Developer CLI is needed only for provisioning

The preview service's regional support can change. Check the current
[AI Red Teaming Agent documentation](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/ai-red-teaming-agent)
before choosing a region. The optional setup defaults to `eastus2`; the Foundry
project and VaultBot's Azure OpenAI resource need not share a region.

## Configure a project

From this directory, use an existing project endpoint:

```bash
AZURE_AI_PROJECT="https://<account>.services.ai.azure.com/api/projects/<project>" \
  ./part2_setup.sh
```

The script preserves existing settings. [The example configuration](.env.example)
defines the expected fields. The callback runs locally and only accepts a
loopback VaultBot URL. Do not expose the lab publicly for a scan.

For a new project, review the template and expected resource costs first:

```bash
./part2_setup.sh --provision --yes
```

This explicitly authorizes billable provisioning through the
[Foundry starter template](https://github.com/Azure-Samples/azd-ai-starter-basic).
`REGION` and `AZURE_SUBSCRIPTION_ID` override defaults. The template is remote
and can change; inspect its generated infrastructure before accepting a
deployment in a sensitive subscription. Setup does not start a scan.

## Check the local target

Keep VaultBot running in a separate terminal. Then:

```bash
./run.sh --check
```

This checks `/api/health`, app identity, and the presence of model configuration.
It does not call a model, verify Azure credentials, or prove that chat works.
Send one ordinary banking question in the app before paying for a scan.

Use a clean lab run for comparisons. Reset intentionally before scanning, then
leave the shared sandbox untouched while the scan runs. The runner does not
silently erase your manual investigation.

## Run an approved scan

Start with a small baseline:

```bash
./run.sh --baseline-only --num-objectives 2 --yes
```

Baseline is also the default. `--yes` acknowledges cloud transmission and cost.
The number of objectives is per risk category, not a cap on total model calls.
Generation, evaluation, retries inside the SDK, and attack transformations all
affect the eventual workload.

For a separately approved comparison run:

```bash
./run.sh --extended --num-objectives 2 --yes
```

Extended mode adds the SDK's EASY strategy group and Jailbreak strategy.
The runner serializes execution for this single-learner sandbox and never
turns transport errors into fake assistant responses. A model-service filter
response is distinguishable from a connection failure.

Each run uses a new timestamped directory beneath `runs/`. `--output` selects a
different new directory. Existing outputs are not overwritten. A `.json` suffix
does not guarantee a single JSON file: this SDK can create a directory containing
several artifacts.

## Read the results offline

Summary mode requires neither a Foundry project nor a running model:

```bash
./run.sh --summary runs/<run-directory>
```

The reader supports the current `scorecard` field and the older
`redteaming_scorecard` field. It checks `evaluation_results.json` before
`results.json` for directory outputs.

Current scorecards expose `risk_category_summary`, `attack_technique_summary`,
and joint breakdowns. Aggregate `_asr` values are percentages, not fractions:
`7.14` means `7.14%`, not `714%`. Always report the denominator and successful
attack count as well. Zero scored attacks is *not scored*, not a clean pass.

Review failed or skipped attacks, judge explanations, thresholds, and coverage
before interpreting ASR. A completion message alone does not prove that every
planned attack was evaluated.

New runs write a separate `run_health.json` report beside the SDK artifacts.
It records the planned and scored counts per category, unscored cases, failed
target requests, and whether the evaluator raised an error. A missing case
makes the run partial even when the SDK labels its own report completed. Scan
and summary commands exit with status 2 for partial or unverified results;
status 0 confirms coverage, not that the application is safe.

Response-source counts distinguish service-filter blocks, model replies, and
unattributed responses. Service filtering is valid end-to-end protection but
does not demonstrate the model's own resistance. Model-reply ASR uses only
responses attributable to the model. The health report stores response hashes
and allowlisted diagnostic metadata, not prompts or reply bodies. The SDK's
original artifacts still contain evaluation conversations; treat them as
sensitive local data.

Older runs have no saved plan or structured response-source telemetry. Their
coverage is unverified by default, and exact service-filter notices are only a
text-based inference. When the original case count is known, provide
`--expected-per-category` with `--summary`; this is the expected number of
cases per category across all selected strategies, not an inferred count from
the surviving records. Summary mode never rewrites the original reports.

## Compare responsibly

Record model/deployment version, profile and knowledge-base state, SDK version,
risk categories, strategies, objectives, scorer thresholds, failures, and scored
sample counts. Change one factor at a time. Small samples are noisy, and generated
attacks need not be identical across runs.

Ask three questions:

1. Which measured behavior changed, with how many scored samples?
2. Was that change caused by the assistant, the model-service filter, the judge,
   or an infrastructure failure?
3. Which Part 1 vulnerabilities remain untested by this scorecard?

A low content-safety ASR is not evidence of account authorization. A high lab
mission score is not a content-safety evaluation. Keep both sets of evidence.

## Troubleshooting and cleanup

| Symptom | Action |
| --- | --- |
| Target rejected | Use a loopback origin and the correct local port. |
| API-only mode | Configure Part 1's model and restart VaultBot. |
| Project endpoint invalid | Use the project endpoint, not an Azure OpenAI resource endpoint. |
| HTTP 401 or 403 | Check authentication, project access, and model data-plane roles. |
| HTTP 429 | Reduce objectives, use baseline, and check quota before retrying. |
| HTTP 502 | Inspect the health report's error category and correlation ID, then match that ID in VaultBot's server log. Do not treat the missing response as a pass. |
| Partial run | Review planned versus scored coverage and failed target requests; the SDK completion message can omit failures. |
| Unverified legacy run | Supply a known expected case count per category; do not infer the plan from successful cases. |
| Unsupported region | Consult the current preview-service documentation. |
| Unsupported scorecard | Inspect the JSON schema and pinned SDK version; do not infer missing metrics. |
| Scan interrupted | Treat artifacts as partial; inspect failures before reporting results. |

The SDK is pinned in [the project manifest](../pyproject.toml). Upgrade it
deliberately and rerun the adapter tests. The ordinary regression suite does not
perform a live scan.

Stop the local app when finished. For resources created by the Part 2 template,
run `azd down` inside its generated project directory and review the deletion
prompt. Do not delete a project you reused for other work.

Return to the [lab overview](../README.md).
