# Phase 0 audit

_Date: 2026-10-18 · Baseline commit `2d78ff9` · Auditor: Claude Code_

Scope: every module in `datamind/`, the app, the Snowflake scripts, the eval set and the docs. Each code finding
was reproduced with a probe script against the real modules (inputs and outputs quoted below); none are guesses.
Live behaviour (Snowflake, Gemma) is **not** verified yet; findings that depend on it are marked _verify live_.

**Limitation:** the participant guide PDF could not be read (macOS blocks access to WhatsApp's folder). The rubric
mapping below uses the summary in `CLAUDE.md` and must be re-checked against `private/` once the PDF is saved there.

Baseline: 54 offline tests pass, 1 skipped (needs SF1 data). Python 3.12.13, pinned requirements install cleanly.

Severity: **Critical** = can break a gate or make reported results false · **High** = wrong answers or a real
security gap a judge could find · **Medium** = robustness, UX or honesty gap · **Low** = polish.

## Summary

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| A1 | High | compiler | HAVING / ORDER BY metrics skip the fan-out guard and join planning → silent double counting | open |
| A2 | High | compare | Comparison tolerance (rel 1e-4) treats 150000 vs 149990 as equal → inflated eval + false "high confidence" | open |
| A3 | High | numbers | A number echoed from the question counts as verified "context" → "Was revenue 300 million?" → "Yes, 300 million" passes | open |
| B1 | High | compiler | Model-supplied HAVING / numeric filter values rendered raw into SQL (injection of SQL fragments) | open |
| B2 | High | validator | Table functions (`TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())`, `TABLE(GENERATOR(...))`) and Cortex calls (`SNOWFLAKE.CORTEX.COMPLETE`) pass validation | open |
| C1 | High | Snowflake auth | Password-only sign-in for a non-SERVICE user is likely blocked by Snowflake's MFA rollout → app can't connect (_verify live_) | open |
| A4 | Medium | numbers | Numbers like `2.5x` and the second year in `1994-1996` are not checked; the "derived" pool (all pairwise ratios/differences of ≤60 cells) is large enough that random numbers can pass | open |
| A5 | Medium | compiler | Month/quarter/week filters compile to `DATE_TRUNC('MONTH', d) = '1995-03'` → runtime error | open |
| A7 | Medium | pipeline | Two empty results "agree" → reported as high confidence | open |
| B3 | Medium | validator | Cartesian joins (`LINEITEM a, LINEITEM b`) and `FETCH FIRST n` pass; only the 120 s timeout stops them | open |
| B4 | Medium | guard | Write-intent regex refuses "Update me on revenue…", "Drop the decimals…"; misses "Remove all customers…", "Set every discount to zero" | open |
| C2 | Medium | executor | Snowflake connection cached forever, no keep-alive or reconnect → fails after the session expires during judging | open |
| C3 | Medium | LLM | Gemini calls have no timeout; 429 retries ignore the server's retry delay; 4096-token output budget shared with thinking | open |
| C4 | Medium | LLM | Gemma on the Gemini API has historically rejected `system_instruction`; no fallback (_verify live_) | open |
| C5 | Medium | LLM | Free-tier rate limits vs 3–6 calls/question with a ~3k-token schema in each prompt (_verify live_) | open |
| C6 | Medium | app | Streamlit shares one executor across sessions; switching role is global | open |
| D1 | Medium | eval | Dev set doubles as the few-shot library; leave-one-out removes only the item itself, so near-duplicates leak → dev accuracy is optimistic | open |
| D3 | Medium | governance | Aggregates over masked columns (e.g. `AVG(c_acctbal)` as restricted role) return NULL but aren't flagged as masked | open |
| E1 | Medium | process | Guide PDF unread; README results table empty; eval never run on real Gemma; no hold-out file | open |
| E2 | Medium | docs | Python version (new Macs ship 3.14; pins tested 3.11–3.13); `gemma4:12b` likely not a real tag; test time "~6 s" is ~18 s | open |
| A6 | Low | compiler | Negative `limit` → invalid SQL; non-numeric year (e.g. "FY95") → bare `ValueError` | open |
| D2 | Low | eval | `percent: true` rescaling multiplies every numeric column (years too) → false failures | open |
| E4 | Low | discover | `draft-model` builds SQL from unquoted identifiers; `--out` treats Windows absolute paths as relative | open |

What is solid (verified): multi-statement SQL, other databases/schemas, `ACCOUNT_USAGE`, `INFORMATION_SCHEMA` tables,
stages, `SYSTEM$` and `RESULT_SCAN` are all rejected; role-playing nations stay apart; the fan-out guard works for
metrics in the SELECT list; explanations come from the SQL AST; the scripted end-to-end tests pass.

## Findings in detail

### A1 · High · HAVING / ORDER BY bypass the fan-out guard (`datamind/plan.py`, `compile_plan`)
Only `plan.metrics` contribute to `required` tables and the grain check. A metric used only in `having` or
`order_by` is inlined as raw SQL without either.
Probe: metrics `[revenue]`, dimension `cust_nation.n_name`, having `total_order_value > 1` →
`... FROM LINEITEM ... GROUP BY cust_nation.n_name HAVING SUM(orders.o_totalprice) > 1` — order totals summed once
per **line**, i.e. multiplied by the number of lines. Same for `order_by: avg_order_value` → `ORDER BY AVG(orders.o_totalprice)`
at line grain (line-weighted average).
**Fix:** add having/order metrics to `required` and to the grain check; test both.

### A2 · High · Comparison is too tolerant (`datamind/compare.py`)
`REL_TOL = 1e-4` applies to every number. Probes: `results_match([(150000,)], [(149990,)])` → **True**;
1.5e9 vs 1.5e9 + 100,000 → **True**. Used by the eval harness (inflates accuracy) and by candidate reconciliation
(two different answers count as agreement → "high confidence").
**Fix:** integers (and integral Decimals) compare exactly; other numbers relative 1e-9 plus the existing
cent-rounding tolerance for amounts ≥ 1. Tests for counts and large sums.

### A3 · High · Question numbers verify the answer (`datamind/numbers.py`, `pipeline._narrate`)
Every number in the question is "context". Probe: question "Was revenue in 1995 300 million?", narration
"Revenue in 1995 was 300 million." with a real result of 1,234,567,890.12 → `300 million: context` → accepted.
A judge asking a leading question gets the false number confirmed.
**Fix:** a number from the question counts only if it also appears in the executed SQL (filters, LIMIT, date
parts). Test with the leading-question case.

### B1 · High · Raw literals in compiled SQL (`datamind/plan.py`, `_literal` / `_condition`)
`exp.Literal.number(v)` renders `v` verbatim. Probes:
having value `"0 OR 1=1) UNION SELECT 1,2 --"` → `HAVING SUM(...) > 0 OR 1=1) UNION SELECT 1,2 -- LIMIT 1000`;
numeric filter value `{"x": "1) OR (1=1"}` → `WHERE l_quantity > {'x': '1) OR (1=1'}`.
The validator and the read-only role still contain this, but it breaks the "compiled from verified parts only"
invariant and is exactly the kind of thing a code-reading judge tests.
**Fix:** coerce numbers strictly (`float()` of a scalar, finite) and reject anything else as a plan error. Tests.

### B2 · High · Validator lets table functions and Cortex through (`datamind/sqlcheck.py`)
`if not name: continue` skips `exp.Table` nodes without a plain name, i.e. `TABLE(...)` functions. Probes that pass:
`SELECT * FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())`, `TABLE(GENERATOR(ROWCOUNT => 1000000000))`,
`TABLE(INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(...))`, and `SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3-8b','hi')`.
The last one matters for the rules (no non-Gemma model may do the central task); in Snowflake the
`CORTEX_USER` database role is granted to PUBLIC by default, so the agent role could call it.
**Fix:** reject any table that isn't a model table or CTE (incl. table functions; `LATERAL FLATTEN` isn't needed for
this data); reject namespaced function calls and `CORTEX`/`AI_*` functions. Optionally revoke `CORTEX_USER` from
the agent roles in `01_setup.sql`. Tests.

### C1 · High · Snowflake password sign-in (_verify live_)
`.env.example` and `01_setup.sql` §7 rely on a password for `DATAMIND_APP` (no `TYPE`). Snowflake has been
phasing out single-factor password sign-in: human (`PERSON`/unset) users need MFA, and service users are expected
to use key-pair or programmatic access tokens. A password-only app user on a trial created in Oct 2026 will likely fail
to connect from Python. **Fix:** make key-pair auth with `TYPE = SERVICE` the primary documented path (free, works on
trials): a helper to generate the key, the `ALTER USER ... SET RSA_PUBLIC_KEY`, `.env` fields. Confirm in Phase 1.

### A4 · Medium · Number-checker gaps
Probe: "…grew 2.5x" → only `2` is extracted (as context); `1994-1996` → `1996` never extracted. The derived pool
includes every ordered pair's difference, ratio, percent change and percent (up to ~14,000 values for 60 cells), so a
rounded made-up number often matches something. **Fix:** extract `Nx` and hyphen-joined numbers; limit derived values
to pairs in the same column plus totals, averages and shares. Tests.

### A5 · Medium · Period filters
Probe: filter `o_orderdate = "1995-03"` with grain month → `DATE_TRUNC('MONTH', o_orderdate) = '1995-03'` (cast error
in Snowflake). **Fix:** normalise to the first day of the period (`DATE '1995-03-01'`); accept `1995-Q1`. Tests.

### A7 · Medium · Empty agreement
`results_match([], [])` is True, so two candidates that both found nothing give "high confidence". A wrong filter
value (e.g. a misspelled name via ILIKE) is the common cause. **Fix:** empty results are at most "medium", and the
message lists the filters that matched nothing.

### B3 · Medium · Cost guard
`SELECT COUNT(*) FROM LINEITEM a, LINEITEM b` (3.6e13 rows) and `FETCH FIRST 5000000 ROWS ONLY` pass. The warehouse
timeout (120 s) and the daily resource monitor bound the cost, but a judge-visible stall is bad.
**Fix:** reject joins between model tables without a join condition (cross joins to a CTE/subquery stay allowed);
treat `FETCH` like `LIMIT`. Tests.

### B4 · Medium · Write-intent heuristic
False positives refuse legitimate questions ("Update me on revenue for 1995", "Drop the decimals and show revenue");
false negatives reach the router ("Remove all customers from Brazil", "Set every discount to zero").
The read-only role makes this a UX issue, not a safety one. **Fix:** require a data object after the verb, add
remove/set/change/modify verbs; table-driven tests with both lists.

### C2 · Medium · Session expiry
`SnowflakeExecutor.connect` caches one connection with no `client_session_keep_alive` and no reconnect. An app left
open for hours during judging will fail every query once the session token expires. **Fix:** keep-alive, and one
transparent reconnect when the connection is closed/expired. Test with a fake connection.

### C3 · Medium · Gemini client robustness
No HTTP timeout (a hung request hangs the UI); 429s retry after 2/4/8/16 s regardless of the server's suggested delay;
`max_output_tokens=4096` may be consumed by thinking, giving empty/truncated replies. **Fix:** `HttpOptions(timeout)`,
honour `retryDelay`, larger output budget for plan/SQL. Verify live.

### C4 · Medium · System instructions on Gemma (_verify live_)
Gemma models on the Gemini API previously returned "Developer instruction is not enabled". If Gemma 4 behaves the
same, every call fails. **Fix:** on that error, retry once with the system text prepended to the prompt and remember
the choice. Test with a fake client.

### C5 · Medium · Rate limits (_verify live_)
Router, plan and SQL prompts each embed the full semantic model (`render()` = 10.9k characters ≈ 3k tokens); a
question costs 3–6 calls. Measure real per-minute limits in Phase 1; if needed, a compact schema for the router and
pacing in the eval runner.

### C6 · Medium · Shared executor in the app
`st.cache_resource` shares one `DataMind` (and one Snowflake connection) across browser sessions; `set_role` changes
it for everyone. Two viewers on different roles could see each other's masking. **Fix:** pass the role per query
(execute `USE ROLE` under a lock, or one executor per role).

### D1 · Medium · Few-shot leakage in dev numbers
The dev set is also the example library. Leave-one-out excludes the item being scored, but closely related items
(same template, different year) remain. Dev accuracy will be optimistic. **Fix:** report the hold-out number as the
headline; optionally exclude same-"family" items during eval. Documented, not hidden.

### D3 · Medium · Masked aggregates
Under `DATAMIND_RESTRICTED`, `MASK_BALANCE` returns NULL, so `AVG(c_acctbal)` is NULL. `_masked_columns` only checks
result column names, so the answer reads as "no data" rather than "masked". **Fix:** detect sensitive columns in the
executed SQL's AST.

### E1 / E2 / A6 / D2 / E4
See the table; fixes are small and listed in the plan.

## Rubric coverage (from `CLAUDE.md`; re-check against the guide)

| Criterion | Weight | Evidence today | Gap |
|---|---|---|---|
| Correctness on unseen questions | 20 | 51-item dev set, gold SQL, harness | never run on Gemma; no hold-out; A1–A3 |
| NL interaction / follow-ups | 10 | router rewrite, history | no measured follow-up/misspelling tests (Phase 3) |
| Evidence / traceability | 15 | SQL, query id, QUERY_TAG, AST explanation, number check | A3/A4 weaken the number claim |
| Snowflake depth | 15 | roles, masking, tags, monitor, Time Travel demo | C1/C2 untested live |
| Gemma depth | 12 | router, planner, SQL, repair, narrator | C3–C5 untested live |
| Ambiguity / errors / unsafe | 12 | router categories, write guard, validator | B2–B4; no adversarial tests yet |
| Reusability (2nd dataset) | 8 | `draft-model`, ADDING_A_DATASET.md | no second dataset (Phase 4) |
| UX | 8 | Streamlit with evidence tabs | not reviewed with a non-technical user (Phase 5) |

## Fix plan

1. **Deterministic fixes with tests (offline, now):** A1, B1, A5, A6 (compiler) → A2, D2 (compare/eval) → A3, A4
   (numbers) → B2, B3, B4 (validator/guard) → A7, D3 (pipeline). One commit per area; `pytest` before each.
2. **Live-robustness code with fakes (offline, now):** C2, C3, C4, C6.
3. **Phase 1 with you:** C1 (key-pair service user), then C3–C5 verified on the real API; E2 docs.
4. **Phase 2:** D1 reporting; first real eval.
