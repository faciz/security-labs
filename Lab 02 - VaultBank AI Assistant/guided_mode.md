---
title: "VaultBank field guide"
description: "Optional investigation prompts and reflection checkpoints for the VaultBank security lab."
ms.date: 2026-09-23
---

## Your assignment

You are signed in as a guest customer. VaultBank says its assistant only acts on
your account. Investigate that claim. For each finding, collect an observation,
an explanation of the failed trust boundary, and a defensive control that would
stop the same action outside a training lab.

Start with the [setup and scope](README.md). Keep testing inside your own local
instance. All data is fictional. Do not inspect generated answer files: the
exercise is about observable application behavior.

## Establish a baseline

Ask a normal banking question. Inspect your account, update an ordinary profile
preference, and watch the requests the browser makes. Record what the assistant
can do, what it refuses, and what the application does without a model.

Separate these observations:

* A model-service content filter rejects a request.
* The assistant declines to call a tool.
* An application tool rejects an operation.
* An operation succeeds and changes state.

These are different controls. One working control does not prove that the
others exist.

## Choose a mission

The mission panel is your scorekeeper. Its optional three-level hints progress
from concept to investigation surface without handing you a complete exploit
chain. Try your own hypothesis first, reveal one hint if needed, and then make
one change at a time.

### Behind the curtain

Find a way to observe instructions meant for internal staff. Compare trusted
instructions with the other material the assistant consumes. Which actor
controls each source? Which source is being treated as more authoritative than
it should be?

Evidence checkpoint: a confidential instruction is actually disclosed. The
activity trail distinguishes an assistant disclosure from diagnostic output.
Do not count your own text being echoed back as independent evidence.

### A borrowed identity

Investigate how VaultBot decides who may enumerate account identifiers. Is the
decision based on a verified identity, a client claim, or something else?

Evidence checkpoint: the account-enumeration tool is invoked. Guessing or typing
an account number does not complete this mission. A refusal is useful evidence
about that attempt, not a guarantee about every path.

### Not your account

Trace a record request from interface to endpoint to tool. Ask where ownership
should be verified, and compare that with what the server actually checks.

Evidence checkpoint: a synthetic record belonging to a different customer is
returned. Record whether your result came through chat or a direct API request.
Do not include the full record in a shared report.

### Follow the money

Inspect the controls on money movement. Identify what proves identity, what
authorizes the source account, and what confirms a transaction. Consider whether
one exposed record can compromise more than one of those controls.

Evidence checkpoint: a positive amount leaves another customer's account and
arrives in yours. Invalid amounts, self-transfers, and failed PIN checks do not
count. Check the resulting balances, not only the assistant's wording.

### Behind the redaction

The bonus asks whether hiding a literal string is equivalent to preventing
disclosure. Consider the order of disclosure, serialization, and filtering.

Evidence checkpoint: submit the recovered synthetic code in the bonus form.
Seeing `[REDACTED]` is not a recovered secret. The score is awarded only when
the submitted value matches this instance.

## Make it a better investigation

Choose an optional constraint after your first run:

* Finish a core investigation without revealing hints.
* Reproduce one finding through two different entry points and compare them.
* Change only one variable per attempt and retain both the failure and success.
* Explain a result using only server evidence, not the assistant's claims.
* Observe the knowledge-base trust boundary and compare it with profile context.

LLM outputs vary across models, versions, and filters. The profile disclosure
rule is deliberately planted for training; it is not evidence that every
production model will leak the same way. The application-layer flaws are
deterministic and can be investigated even when the assistant refuses.

## Defend one boundary

After collecting your evidence, choose one control to implement in a local
follow-up exercise:

| Observed failure | Defensive control | Regression question |
| --- | --- | --- |
| User text becomes an instruction | Keep untrusted content in a data role; constrain tool authority | Can changing a profile change access rights? |
| Claimed identity grants access | Verified session identity and server-side authorization | Does claiming a staff name grant anything? |
| Record lookup trusts an identifier | Object-level ownership checks and response field allowlists | Can another customer's record be read? |
| PIN and record leak together | Separate transaction confirmation and least-privilege tools | Can a leaked record authorize a debit? |
| Debug configuration discloses secrets | Remove secret-bearing diagnostic output | Can any supported representation expose the code? |

Do not fix an authorization failure by only adding stronger wording to the
system prompt. Verify the raw endpoint and model tool both enforce the rule.

## Debrief

Export the investigation and review your notes before sharing. Explain:

1. What you expected the system to enforce.
2. What input you controlled.
3. What evidence demonstrated the outcome.
4. Which layer should have stopped it.
5. What test would prevent the regression.

Continue with [Part 2](part2-red-teaming/guided_mode.md) to compare application
security findings with a content-safety scorecard. They answer different questions.
