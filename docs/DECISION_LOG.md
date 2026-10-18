# Decision log

## 2026-10-18 — PS1 (DataMind) over PS2 (Private Legal Triage)

A second assistant (GLM) first recommended PS2. We reviewed its analysis against the participant guide and
current sources and chose PS1. The reasoning, kept here so later decisions stay consistent:

**Errors in the case for PS2**
- *Cap misread.* PS1's trust cap fires only if correctness is in the **Poor** band (<25% of its points), not at the
  Acceptable/Good boundary. A team with an evaluation harness won't land there.
- *Caps never converted to final scores.* With a perfect common score, PS1 capped = 0.7×50+30 = **65**;
  PS2 capped = 0.7×40+30 = **58**. PS2's cap is harsher and has three triggers (grounding, uncertainty, privacy) vs one.
- *Wrong model assumption.* PS1 allows any Gemma variant, so Gemma 4 31B (Gemini API, free tier) is available.
  PS2 is limited to edge models (E2B/E4B, ~2–4B), which must handle legal explanation, refusals and
  prompt injection on unscripted documents.
- *Wrong benchmark.* BIRD (95 messy databases, external knowledge) is not a single curated schema; its labels are
  also noisy (a 2026 study found errors in 61% of a train subset). SOTA had moved to ~80–82% by mid/late 2026.
  The "evidence hints" BIRD systems rely on are exactly what our semantic model supplies.
- *"PS2's risks are deterministic" — only half true.* Privacy is; quote grounding partly is; refusal/uncertainty
  under adversarial judging is small-model behaviour.
- *Snowflake risks overstated.* The ~10 credits/day limit applies to Cortex AI functions, which we don't use.
  X-Small warehouse ≈ 1 credit/hour while running; $400 covers 100+ hours. Trial expiry is handled by a
  fresh judging-window account built purely from the setup script.

**What was right in the PS2 case:** correctness on unseen questions is PS1's central risk; SQL evidence makes
traceability comparatively easy; trial timing needs a plan.

**Strategy that follows:** build around *measured* correctness, not a chat UI —
semantic model with verified joins/metrics, compiled plans, two independent query paths compared on results,
deterministic explanations, number-level grounding, and an evaluation harness with an honest hold-out set.

## 2026-10-18 — implementation choices
- Gemma 4 31B via Gemini API by default; Ollama `gemma4:12b` as the local alternative (26B is too tight on
  the team's 16 GB M5 MacBook; changed 2026-10-18).
- No Cortex (keeps the central AI task on Gemma).
- TPC-H SF1 copied from `SNOWFLAKE_SAMPLE_DATA` into `DATAMIND_DB.TPCH` (needed for masking policies and the
  data-change demo; shared data is read-only).
- Independent ground truth from locally generated TPC-H (tpchgen-cli); verified against published TPC-H answers.
- Python backend (sqlglot, Snowflake connector, pydantic) + Streamlit UI, chosen for speed of build and tooling.

## 2026-10-18 — Snowflake sign-in: password on trials, key pair as an option
Snowflake's MFA rollout (phases through Oct 2026) does not apply to trial accounts, which keep single-factor
password sign-in ([docs](https://docs.snowflake.com/en/user-guide/security-mfa-rollout)). So the quick start uses
the judge's own trial login + password (no key generation), while the app still queries only as `DATAMIND_AGENT`
with secondary roles off. Key-pair sign-in for the `TYPE = SERVICE` user `DATAMIND_APP` stays supported for
non-trial accounts and long-lived deployments.

## 2026-10-18 — Chinook as second dataset (reusability criterion, 8 points)
Chose Chinook (digital media store database, MIT licence, pinned commit `7f67772`) to demonstrate zero-code
reusability via semantic model configuration alone: handles role-playing tables (`employee` as `support_rep` vs
`manager`), many-to-many relationship (`playlist_track` non-fanout handling), Snowflake setup and staging DDL,
and a 22-item evaluation set with 100% verified gold SQL.

## 2026-10-18 — Gemma backend: no Google AI Studio; Ollama locally, 31B via Hugging Face
The jury ruled that Gemma may not be used through Google AI Studio / the Gemini API, and that a 31B model must come
from Hugging Face. Gemma 4 31B (`google/gemma-4-31B-it`, ungated) is live on Hugging Face Inference Providers
(Novita $0.14/M input, $0.40/M output; DeepInfra $0.20/$0.40; free HF accounts get no included credits). Running 31B
locally needs ~19 GB+ and doesn't fit the team's 16 GB laptops. So: default backend `ollama` with `gemma4:12b` (free,
reproducible; measured 218 s/question), and a new `hf` backend for 31B through the OpenAI-compatible router. The
Gemini API client remains in the code but is not used or documented for this event.
