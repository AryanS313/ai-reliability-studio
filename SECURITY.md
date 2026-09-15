# Security policy

## Reporting a vulnerability

Do not include credentials, customer data, or a working exploit against the live service in a public issue. Use GitHub private vulnerability reporting **if the repository owner has enabled it**; otherwise contact the owner privately to establish a reporting channel. Include an affected commit, a minimal local reproduction using fictional data, impact, and a temporary mitigation. This repository does not establish a response-time commitment or a monitored security inbox.

## Supported beta boundary

- The default `APP_ACCESS_MODE=public-demo` is an anonymous, sample-only experience. Each browser session receives a separate in-memory database. Custom uploads, real provider execution, and external assistant requests are disabled. A new session does not recover the previous session's evidence.
- The design-partner workflow uses explicit `APP_ACCESS_MODE=local`, `APP_ENV=development`, `AUTH_MODE=single-user` on a trusted computer with Streamlit bound to `127.0.0.1`. It persists projects in local SQLite. Never expose this mode through a public address, tunnel, or shared host.
- Shared hosting requires `APP_ACCESS_MODE=authenticated`, `APP_ENV=production`, trusted proxy/OIDC authentication, provisioned identities and memberships, current supported PostgreSQL, and validated infrastructure controls. These operational requirements have not been certified by the local beta tests.
- Credential values belong in password fields/session memory or an approved private runtime. Saved target configurations contain `secret://NAME` references. Known credentials echoed by a target are discarded before evidence persistence; do not put any secret in source documents, datasets, prompts, filenames, URLs, or Git.
- Local uploads are trusted-operator inputs. Production document ingestion fails closed without the required malware scanner. OCR, durable workers, parser isolation, backups, monitoring, and infrastructure validation remain deployment requirements.

See [Security and privacy](docs/SECURITY_AND_PRIVACY.md) for exact configuration, data handling, and verification limits, and [the design-partner review](docs/design-partner/security-review.md) for findings and tests. Local improvements do not change the live deployment until the owner approves a release.
