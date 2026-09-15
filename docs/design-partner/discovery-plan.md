# Design-partner discovery and validation

Status: planned research, not completed customer evidence. No outreach has been sent. Recruiting, external communications, external data access, and publishing require the owner's authorization.

## Recruit against behavior

Recruit 6–8 teams matching the [primary ICP](product-brief.md), including teams using spreadsheets/scripts and teams already using an evaluation tool. Seek a builder and domain/release owner together. Ask for a recent change and an upcoming release, not agreement that “AI reliability matters.” Exclude teams that cannot provide approved test material or a staging endpoint, need regulated certification, or have no upcoming release.

Use participant consent and a private research record. Keep names, emails, company details, recordings, and raw examples out of product analytics and this repository. Publish only permissioned, de-identified aggregate outcomes with sample size and dates.

## Interview: 30 minutes, before showing the product

1. Walk through the last assistant release. What changed, and who approved it?
2. Show how you tested it and one actual failure, with sensitive details removed.
3. How many people and how much active time did the review take? What was delayed or repeated?
4. How did you decide whether an answer, citation, or escalation was correct?
5. What did your existing tools do well? What concrete work remained?
6. What must stay inside your environment? Who can approve a pilot and a paid continuation?
7. What changes next, and when will you evaluate again?

Record observed artifacts separately from self-reported estimates and opinions. Do not infer avoided monetary harm from a seeded failure.

## Unassisted usability session

Give a neutral task: “Find out what this tool can help you decide, try the example, and explain the result.” Do not point at controls. Record elapsed time, intentional actions, completion, wrong turns, errors/recovery, and interventions. Ask the participant to explain the failure, severity, next change, evidence type, and missing evidence. Test keyboard use and a narrow viewport as separate tasks; source/AppTest verification does not establish human accessibility.

Then ask the team's engineer to connect an approved staging endpoint from the instructions, load a small reviewed dataset, run, and have the domain owner explain a finding. Record whether assistance or a custom adapter was required. Supply no production credentials and perform no calls without explicit confirmation in the product.

## Two-release pilot

- Before release 1: agree the risky behaviors, candidate/version scope, representative cases, held-out review, and data custody. Record how the team would otherwise evaluate it.
- After release 1: review false positives/negatives and investigate findings. Record whether each finding changed a decision, caused a fix, or was irrelevant.
- At the next actual release: observe whether the team initiates another evaluation, reuses its baseline, and understands comparable-case results. Do not count a scheduled demo rerun as retention.
- At pilot end: ask for a concrete continuation commitment with scope, owner, next date, and constraints. Discuss price only after a real result; record “declined” and “no answer” as well as “yes.”

## Decision rules, initially proposed

Proceed with the ICP if at least 4 of 6 qualified teams show a repeated manual review problem and at least 3 agree to test their own endpoint; these are directional small-sample thresholds, not market validation. Require at least 4 of 5 independent first-time users to complete the sample without help and explain synthetic limitations. Seek at least 3 of 5 activated teams with a second-release opportunity to repeat and compare within 30 days; extend the window explicitly when their release cycle is longer.

Reconsider the positioning if teams can reproduce the same review more simply in an existing tool, the domain owner cannot trust the evidence, integration regularly exceeds an hour, or no one returns when the next release occurs. Zero privacy/isolation incidents and zero misleading synthetic launch verdicts are mandatory regardless of conversion.

## Evidence ledger template

Keep one de-identified entry per finding: date; research method; anonymous team code kept in the private research record; observed or self-reported; workflow/trigger; artifact description without contents; frequency; consequence; existing alternative; counterevidence; proposed decision; validation outcome. Link released changes to the observed need. Never convert local agent-run tests into “customer adoption” or “time saved.”
