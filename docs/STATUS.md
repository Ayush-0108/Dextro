# Status

_Last updated: 2026-10-18 (end of session 2). Team repo: https://github.com/ZERODAY-2026/Dextro (main)._

## Verified
- **Tests:** `python -m pytest -q` → 153 passed, 0 failed (Python 3.12.13, macOS, Apple M5, 16 GB), including all
  TPC-H tests, gold SQL verification, and the Chinook second-dataset test suite. CI skips the SF1 test.
- **Snowflake trial (live, run by Kanhaiya in Snowsight as ACCOUNTADMIN):** region AWS_AP_SOUTH_1; masking policy
  created → **Enterprise edition or higher**; SNOWFLAKE_SAMPLE_DATA present, TPCH_SF1.ORDERS = 1,500,000 rows;
  test database dropped. Owner user: TYPE null, has_password true, has_mfa false → app uses its own key-pair user.
- **Repo hygiene:** no `.env`, keys, `CLAUDE.local.md`, `private/` or data in git; account identifier and login
  name absent from the whole history (checked before pushing).
- **Local Ollama Gemma model:** `gemma4:12b` (7.7 GB) downloaded and verified via `ollama list`.

## Not verified
- `snowflake/01_setup.sql` has **not** been run (no DATAMIND_DB, roles, masking policies or DATAMIND_APP yet).
- Sign-in: quick start is now password on the trial (exempt from Snowflake's MFA rollout, per Snowflake docs);
  key pair for `DATAMIND_APP` is optional. Neither has been tried against the live account yet.
- No `.env`: `python -m datamind check` fails on both sides (`SNOWFLAKE_ACCOUNT` missing; `GEMINI_API_KEY` missing).
- Gemma has **never** been called live. Defaults: `GEMMA_BACKEND=api`, `GEMMA_MODEL=gemma-4-31b-it`. Google's docs list
  that id, `system_instruction` and `thinking_level` high/minimal, matching our client; free-tier rate limits are
  unknown until the first eval, which now records requests, 429s, waits and latency (audit C5). Local fallback:
  Ollama `gemma4:12b` (downloaded and ready).
- No eval has been run against Snowflake + Gemma. No accuracy numbers exist. No hold-out file exists.
- `check-gold` against Snowflake not run (gold SQL only verified on DuckDB, two scales).
- Streamlit app not opened against live services.
- Participant guide PDF not read: `private/` does not exist on this Mac (checked 2026-10-18, session 3). Rubric
  below comes from `CLAUDE.md`'s summary; common rubric C1–C8, gates and S1–S10 not re-mapped yet.

## Done (commits, oldest first)
| Commit | What | Why |
|---|---|---|
| 2d78ff9 | Import codebase + OSS extras; ignore `private/` | baseline from the zips |
| e5dbd84 | `docs/AUDIT.md` | Phase 0: 23 reproduced findings |
| 1a2364a | Compiler fixes (A1, B1, A5, A6) | HAVING/ORDER BY double counting; unsafe plan values; period filters |
| a2e20f6 | Comparison fixes (A2, D2) | 150000 vs 149990 counted as equal; percent rescaling touched years |
| 9e058e1 | Number checker (A3, A4) | leading questions verified their own number; 2.5x / ranges unchecked |
| 842e5c4 | Validator + write guard (B2–B4) | table functions, Cortex, cartesian joins passed; guard false positives |
| 8400e28 | Pipeline (A7, D3) | empty agreement = "high"; masked aggregates read as missing |
| fa3dec2 | Executor (C2, C6) | no reconnect after session expiry; role switch shared across sessions |
| 2093e81 | Gemini client (C3, C4) | no timeout; ignored retryDelay; no system-instruction fallback |
| f4e6ba1 | Docs | audit progress, test counts |
| eac2e88 | Merge Dextro initial commit | join the team repo's history, keep our README |
| 9e2f5ce | README → Dextro URLs | badge and clone command pointed at the old repo |
| c3601c2 | Key-pair DATAMIND_APP service user (C1) | password-only sign-in at risk from Snowflake's MFA rollout |
| 1289d3e | Password sign-in on trials, key pair optional | trials are exempt from the MFA rollout; judges shouldn't need keys |
| cb15747 | Gemini usage + latency in eval reports; Ollama 12B | measure rate limits (C5); 26B too tight for 16 GB |
| 7463735 | Docs: Dextro — DataMind title, quick start, audit updates | repo vs product name; docs match code |
| f31bcbb | .env inline-comment fix + `scripts/make_env.py` | copied .env.example broke config; secrets typed locally, never in chat |
| 0424fc4 | Eval: follow-ups, also_ok/forbid, 15 new dev items | measure follow-ups and adversarial input (Phase 3) |

## Audit findings (`docs/AUDIT.md`)
Fixed and tested: A1–A7, B1–B4, C2, C6, D2, D3 (High: A1, A2, A3, B1, B2). Code-fixed, live behaviour unverified:
C3, C4. C1 fixed in scripts, not yet run. Open: C5 (rate limits, measure live), D1 (dev few-shot leakage → report
hold-out as the headline), E1 (guide unread, no eval), E2 (docs: Python version, `gemma4:12b` tag), E4 (draft-model
identifiers). None marked won't-fix.

## Rubric (PS1 track; source: CLAUDE.md summary — re-check against the guide)
| Criterion | Pts | State | Evidence / gap |
|---|---|---|---|
| Correctness on unseen questions | 20 | **weak (unmeasured)** | harness + 51 dev items + gold SQL; zero Gemma runs; no hold-out |
| NL interaction / follow-ups | 10 | ok (untested live) | router rewrite + history; no live follow-up tests |
| Evidence / traceability | 15 | strong (offline) | SQL, query id, QUERY_TAG, AST explanation, number check (now stricter) |
| Snowflake depth | 15 | ok (scripted, not run) | roles, masking, monitor, tags, Time Travel demo in scripts |
| Gemma depth | 12 | ok (untested live) | router, planner, SQL, repair, narrator |
| Ambiguity / errors / unsafe | 12 | ok | router categories, write guard, hardened validator; no adversarial suite yet |
| Reusability (2nd dataset) | 8 | **strong (verified offline)** | Chinook dataset (MIT, pinned), DDL setup, loader, semantic model (role-playing employee/manager, many-to-many playlist_track), 22-item eval set with 100% verified gold SQL, tests/test_chinook.py |
| UX | 8 | ok (unreviewed) | Streamlit evidence tabs; never run live |
Common rubric (30%): not mapped — its criteria aren't in CLAUDE.md; needs the guide.

## Risks
- **Trust cap:** if correctness lands < 25% the PS1 score caps at 50. Unmeasured until the first eval.
- **Gate P2/G2:** if `gemma-4-31b-it` isn't served on the free API or rate limits are tight, nothing answers.
- **Gate G2:** setup script and key-pair flow unproven on a live account.
- **Trial expiry ~2026-11-17**; deadline/judging dates unknown.
- Rubric unverified against the guide; common criteria unmapped.

## Next (in order)
1. Run `01_setup.sql` (expect 6001215 / 1500000 / 150000), then `.env` with password sign-in.
2. Gemini key → `python -m datamind check`; then `check-gold --independent duckdb`.
3. First `python -m datamind eval` baseline; triage; log numbers below.

## Open questions (ask Kanhaiya)
- Deadline and judging dates? Team members/roles; who writes the hold-out set?
- Save the guide PDF into `~/DataMind/private/` (folder doesn't exist yet), then map C1–C8, G1–G5/P1–P3, S1–S10.
- Second dataset (Phase 4).

## Eval results log
| Date | Model | Split | Overall | Notes |
|---|---|---|---|---|
| – | – | – | – | no run yet |
