# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected secret exposure, authorization bypass,
cross-workspace access, unsafe file handling, or remote-code-execution problem.
Use GitHub's private vulnerability reporting for this repository. Include a
minimal reproduction, affected commit, impact, and any temporary mitigation.

## Supported deployment posture

- The Streamlit public demo is synthetic, non-production, and must use explicit
  single-user mode without proprietary data.
- Production requires PostgreSQL, `APP_ENV=production`, authenticated proxy/OIDC
  identity, TLS, runtime-managed secrets, database backups, retention settings,
  error monitoring, and network egress controls.
- API keys and external target credentials must be referenced as
  `secret://NAME`. They must never appear in database fields, logs, or exports.
- File size, decompression, row, column, and extracted-character limits are
  enforced before indexing. Image-only PDFs need a separately secured OCR worker.

See `docs/SECURITY_AND_PRIVACY.md` for the threat model and operational checklist.
