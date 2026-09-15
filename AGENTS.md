# Standing product documentation and reporting requirement

This requirement comes from the product owner and applies alongside the ongoing implementation/release task. It does not replace or narrow that task.

- Maintain `docs/PRODUCT_EVOLUTION.md` as the living product history and PM handoff. Read its current snapshot before meaningful work.
- After every meaningful product, UX, evaluation, security, architecture or release-readiness milestone, update its top “Changes since the previous update,” relevant history/current-state sections and milestone ledger in the same work cycle.
- Record what changed, why, the user/trust/operating problem, exact evidence, verification, uncertainty, affected product areas and any superseded claim. Preserve mistakes and corrections. Distinguish documented facts, observations, PM inference and hypotheses.
- Separate deployed functionality, remote main, other committed branches, uncommitted work and proposals. Verify delivery against Git/deployment evidence; a successful test or commit is not deployment.
- Keep engineering, evaluator-validity, security, deployment, usability, customer and commercial evidence distinct. Never turn synthetic tests, authored fixtures or agent-run workflows into customer validation or real assistant quality.
- When the owner asks for a project update, provide the complete self-contained 17-part report specified in `docs/PRODUCT_EVOLUTION.md` section 13 without requiring the categories to be repeated. Brief unsolicited progress notes need not reproduce the report.
- At final completion, include the full PM-level evolution report alongside the technical summary, link `docs/PRODUCT_EVOLUTION.md`, and justify the product's maturity classification using actual evidence and remaining limits.
- Do not place credentials, raw customer inputs or personal research records in the history. Link de-identified evidence with its scope instead.
