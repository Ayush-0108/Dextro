# Security policy

## Reporting a vulnerability
Please don't open a public issue for security problems. Use GitHub's **Security → Report a vulnerability**
(private advisory) on this repository. We aim to respond within 7 days.

In scope: ways to make DataMind write or delete data, read tables outside the configured schema, bypass the
SQL validator or role restrictions, leak credentials, or show answers not backed by query results.

## Design notes
- DataMind connects with a read-only Snowflake role and disables secondary roles for the session.
- Model-written SQL is validated (single SELECT, modelled tables only, row cap) before it reaches Snowflake.
- Credentials are read from `.env` / environment variables and are never logged or committed.
- See `docs/ARCHITECTURE.md` → Threat model.
