# Security policy

## Reporting a vulnerability

Do not include credentials, customer data, or a working exploit against the live service in a public issue. Use GitHub private vulnerability reporting **if the repository owner has enabled it**; otherwise contact the owner privately to establish a reporting channel. Include an affected commit, a minimal local reproduction using fictional data, impact, and a temporary mitigation. This repository does not establish a response-time commitment or a monitored security inbox.

## Supported beta boundary

- The new native default `APP_ACCESS_MODE=hosted-session` provides anonymous, isolated, temporary custom workspaces on the main site. It accepts approved non-sensitive inputs, visitor-entered provider keys and guarded public HTTPS assistant connections. No owner credential or configured persistent database is exposed to visitors. Exact deployment status is recorded in the release review; a source change alone is not live verification.
- `APP_ACCESS_MODE=public-demo` remains an optional restricted sample installation. The product owner did not approve making this the only main-site workflow.
- `APP_ACCESS_MODE=local` remains an optional developer/trusted-operator mode with Streamlit bound to `127.0.0.1`. Never expose its shared single-user persistent workspace publicly. Customers should not need this mode to use the product.
- Managed persistent hosting requires `APP_ACCESS_MODE=authenticated`, `APP_ENV=production`, trusted proxy/OIDC authentication, provisioned identities and memberships, current supported PostgreSQL, and validated infrastructure controls. These operational requirements have not been certified by the beta tests.
- Credential values belong in password fields/session memory or an approved private runtime. Saved target configurations contain `secret://NAME` references. Known credentials echoed by a target are discarded before evidence persistence; do not put any secret in source documents, datasets, prompts, filenames, URLs, or Git.
- Hosted uploads have strict byte, row, archive and extracted-text limits. Parsing runs in a separate process with a scrubbed environment and time/CPU/output limits; Linux also enforces an address-space limit. This is resource containment, not an operating-system sandbox or malware scan. Production document ingestion still fails closed without its required scanner. OCR, durable workers, stronger sandboxing, backups, monitoring and infrastructure validation remain managed-production requirements.

See [Security and privacy](docs/SECURITY_AND_PRIVACY.md) for exact configuration, data handling, and verification limits, and [the design-partner review](docs/design-partner/security-review.md) for findings and tests. Local improvements do not change the live deployment until the owner approves a release.
