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
- Gemma 4 31B via Gemini API by default; Ollama `gemma4:26b` as a local alternative.
- No Cortex (keeps the central AI task on Gemma).
- TPC-H SF1 copied from `SNOWFLAKE_SAMPLE_DATA` into `DATAMIND_DB.TPCH` (needed for masking policies and the
  data-change demo; shared data is read-only).
- Independent ground truth from locally generated TPC-H (tpchgen-cli); verified against published TPC-H answers.
- Python backend (sqlglot, Snowflake connector, pydantic) + Streamlit UI, chosen for speed of build and tooling.
