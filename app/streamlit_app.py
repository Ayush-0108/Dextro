"""Nexora (package: datamind) — Streamlit UI.  Run:  streamlit run app/streamlit_app.py

Every status shown here is computed: system health comes from live checks, and every answer's evidence (receipt,
verification tower, SQL receipt, cross-check) comes from what actually ran for that answer.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datamind.config import build, load_dotenv  # noqa: E402
from datamind.pipeline import Answer  # noqa: E402

load_dotenv()
st.set_page_config(page_title="Nexora", page_icon="✅", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  :root { --nx-bg:#F8FAFC; --nx-card:#FFFFFF; --nx-line:#E2E8F0; --nx-ink:#0F172A; --nx-muted:#475569;
          --nx-faint:#94A3B8; --nx-ok:#059669; --nx-ok-soft:#ECFDF5; --nx-warn:#D97706; --nx-warn-soft:#FFFBEB;
          --nx-bad:#DC2626; --nx-bad-soft:#FEF2F2; --nx-info:#2563EB; --nx-info-soft:#EFF6FF; }
  html, body, [class*="css"], .stMarkdown, .stCaption, button, input, textarea {
      font-family: 'Inter', -apple-system, 'SF Pro Text', system-ui, sans-serif; }
  code, pre, .nx-mono { font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace !important; }
  .block-container { padding-top: 1.4rem; max-width: 1180px; }
  /* only the answer receipt cards (containers keyed nx-receipt-*) get the card look */
  [class*="st-key-nx-receipt"] { background: var(--nx-card); border: 1px solid var(--nx-line); border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,.06); padding: 14px 16px; }
  .nx-chip { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.76rem; font-weight:600;
             margin:0 6px 6px 0; border:1px solid var(--nx-line); color:var(--nx-muted); background:#fff; }
  .nx-ok { background:var(--nx-ok-soft); color:var(--nx-ok); border-color:#A7F3D0; }
  .nx-warn { background:var(--nx-warn-soft); color:var(--nx-warn); border-color:#FDE68A; }
  .nx-bad { background:var(--nx-bad-soft); color:var(--nx-bad); border-color:#FECACA; }
  .nx-info { background:var(--nx-info-soft); color:var(--nx-info); border-color:#BFDBFE; }
  .nx-legend { font-size:.76rem; color:var(--nx-muted); }
  .nx-status { display:flex; align-items:center; gap:8px; font-size:.82rem; color:var(--nx-ink); margin:4px 0; }
  .nx-dot { width:8px; height:8px; border-radius:50%; display:inline-block; flex:none; }
  .nx-dot.ok { background:var(--nx-ok); } .nx-dot.warn { background:var(--nx-warn); } .nx-dot.bad { background:var(--nx-bad); }
  .nx-sub { color:var(--nx-muted); font-size:.74rem; margin-left:16px; margin-top:-2px; }
  /* the dashed wire between verification blocks */
  .nx-wire { width:2px; height:20px; margin:0 0 0 26px;
             background: repeating-linear-gradient(to bottom, var(--nx-faint) 0 4px, transparent 4px 8px);
             background-size: 2px 8px; animation: nx-flow .9s linear infinite; }
  @keyframes nx-flow { from { background-position: 0 0; } to { background-position: 0 8px; } }
  @media (prefers-reduced-motion: reduce) { .nx-wire { animation: none; } }
</style>
""", unsafe_allow_html=True)

DATASETS = {   # label -> semantic model; only datasets whose YAML exists are offered
    "TPC-H · wholesale supplier (8 tables, 8.7M rows)": "config/datasets/tpch.yaml",
    "Chinook · digital music store (11 tables)": "config/datasets/chinook.yaml",
}
DATASETS = {k: v for k, v in DATASETS.items() if (ROOT / v).exists()}
for _p in sorted((ROOT / "config" / "datasets").glob("*.yaml")):   # any new dataset YAML appears automatically
    _rel = str(_p.relative_to(ROOT))
    if _rel not in DATASETS.values():
        try:
            import yaml
            DATASETS[(yaml.safe_load(_p.read_text(encoding="utf-8")) or {}).get("title") or _p.stem] = _rel
        except Exception:  # noqa: BLE001 - a broken draft shouldn't take the app down
            pass
ROLES = {"Analyst (full access)": "DATAMIND_AGENT",
         "Restricted (PII masked by Snowflake masking policies)": "DATAMIND_RESTRICTED"}
STATUS_LABEL = {"answered": "Answered", "empty": "No matching rows", "clarify": "Needs clarification",
                "not_in_data": "Not in this data", "refused": "Declined", "chitchat": "About Nexora",
                "error": "Could not answer"}
CANDIDATE_LABEL = {"plan": "Semantic plan → compiled SQL", "sql": "Gemma-written SQL",
                   "sql_alt": "Independent re-derivation"}


@st.cache_resource(show_spinner="Connecting to Snowflake and Gemma...")
def get_agent(dataset: str):
    return build(dataset=dataset)


@st.cache_data(ttl=300, show_spinner=False)
def system_status(dataset: str) -> dict[str, tuple[str, str, str]]:
    """Live checks, cached for 5 minutes: (state ok|warn|bad, headline, detail) per component."""
    agent = get_agent(dataset)
    out: dict[str, tuple[str, str, str]] = {}
    ex = agent.executor
    if getattr(ex, "engine", "") == "snowflake":
        # context functions only: answered by Snowflake's services layer, no warehouse time
        r = ex.run("SELECT CURRENT_REGION(), CURRENT_VERSION()", tag={"purpose": "health"})
        wh = ex.describe().get("warehouse", "")
        out["Snowflake"] = (("ok", "Connected", f"{wh} · {r.rows[0][0]} · v{r.rows[0][1]}") if r.ok and r.rows
                            else ("bad", "Not reachable", (r.error or "")[:80]))
    else:
        out["Snowflake"] = ("warn", "Offline engine", "DuckDB, development only — not used for judging")
    llm = getattr(agent.llm, "inner", agent.llm)
    host, model = getattr(llm, "host", None), getattr(llm, "model", "")
    if host:   # Ollama: is the model pulled? (no generation, so this costs nothing)
        try:
            import httpx
            tags = [m.get("name", "") for m in httpx.get(f"{host}/api/tags", timeout=2).json().get("models", [])]
            ok = any(t == model or t.split(":")[0] == model for t in tags)
            out["Gemma"] = ("ok", "Ready", f"Ollama · {model}") if ok else ("bad", "Model not pulled",
                                                                          f"ollama pull {model}")
        except Exception as e:  # noqa: BLE001 - shown to the user
            out["Gemma"] = ("bad", "Ollama not reachable", str(e)[:80])
    else:
        out["Gemma"] = ("ok", "Configured", agent.llm.name)
    return out


def esc(text: str) -> str:
    """Escape characters Streamlit markdown would interpret ($ = LaTeX, etc.)."""
    return str(text).replace("\\", "\\\\").replace("$", "\\$").replace("[", "\\[").replace("]", "\\]")


def chip(label: str, kind: str = "") -> str:
    return f'<span class="nx-chip {f"nx-{kind}" if kind else ""}">{html.escape(label)}</span>'


def highlighted(a: Answer) -> str:
    """Answer text with every number coloured by its verification status."""
    text, out, pos = a.message, [], 0
    color = {"verified": "green", "derived": "blue", "unverified": "orange"}
    for n in sorted(a.number_checks, key=lambda n: n.start):
        if n.start < pos or n.end > len(text) or text[n.start:n.end].strip() != n.text:
            continue
        out.append(esc(text[pos:n.start]))
        span = esc(text[n.start:n.end])
        out.append(f":{color[n.status]}-background[{span}]" if n.status in color else span)
        pos = n.end
    out.append(esc(text[pos:]))
    return "".join(out)


def result_frame(a: Answer) -> tuple[pd.DataFrame, object]:
    res = a.result
    df = pd.DataFrame([list(r) for r in res.rows], columns=res.columns)
    for c in df.columns:
        if df[c].map(lambda v: type(v).__name__ == "Decimal").any():
            df[c] = df[c].astype(float)
    cells = {(n.cell[0], n.cell[1]) for n in a.number_checks if n.cell and n.status == "verified"}
    if not cells or len(df) > 500:
        return df, df

    def style(data: pd.DataFrame) -> pd.DataFrame:
        s = pd.DataFrame("", index=data.index, columns=data.columns)
        for r, c in cells:
            if r in s.index and c in s.columns:
                s.loc[r, c] = "background-color: #D1FAE5; color: #065F46; font-weight: 600"
        return s
    return df, df.style.apply(style, axis=None)


def chart(df: pd.DataFrame) -> None:
    """A bar chart for categories, a line chart for time; nothing when the shape doesn't suit a chart."""
    if not 2 <= len(df) <= 60 or df.shape[1] < 2:
        return
    import plotly.express as px
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    lab = [c for c in df.columns if c not in num]
    timeish = re.compile(r"date|year|month|quarter|week|period", re.I)
    if len(lab) == 1 and num:
        x, y = lab[0], num[0]
    elif not lab and len(num) >= 2 and timeish.search(num[0]):
        x, y = num[0], num[1]
    else:
        return
    is_time = bool(timeish.search(str(x))) or pd.api.types.is_datetime64_any_dtype(df[x])
    if is_time:
        df = df.sort_values(x)          # a time axis is drawn in time order whatever order the rows came in
        plot = px.line(df, x=x, y=y, markers=True)
        plot.update_traces(line_color="#059669", marker_color="#059669")
    else:
        plot = px.bar(df, x=x, y=y)
        plot.update_traces(marker_color="#059669")
    plot.update_layout(template="plotly_white", height=320, margin=dict(l=8, r=8, t=24, b=8),
                       font=dict(family="Inter, system-ui, sans-serif", size=12, color="#0F172A"),
                       xaxis_title=None, yaxis_title=y)
    st.plotly_chart(plot, use_container_width=True, config={"displayModeBar": False})


def receipt(a: Answer, idx: int) -> None:
    """The answer card: status, answer text with checked numbers, and the question -> query check."""
    res = a.result
    chips = [chip(STATUS_LABEL.get(a.status, a.status), "info")]
    if a.confidence:
        chips.append(chip(f"{a.confidence} confidence",
                          {"high": "ok", "medium": "warn", "low": "bad"}.get(a.confidence, "")))
    if a.chosen and res:
        chips.append(chip("✓ read-only SQL, validated", "ok"))
        chips.append(chip(f"⏱ {a.timings.get('total_s', 0):.1f} s · Snowflake {res.elapsed_ms} ms"))
        if res.query_id:
            chips.append(chip(f"❄ query {res.query_id[:18]}…" if len(res.query_id) > 18 else f"❄ query {res.query_id}"))
    if a.narration == "fallback" and a.status == "answered":
        chips.append(chip("templated answer (narration failed its number check)", "warn"))
    with st.container(key=f"nx-receipt-{idx}-{a.answer_id}"):
        st.markdown("".join(chips), unsafe_allow_html=True)
        st.markdown(highlighted(a) if a.number_checks else esc(a.message))
        if a.standalone_question and a.standalone_question.strip().lower() != a.question.strip().lower():
            st.caption(f"Interpreted as: {esc(a.standalone_question)}")
        if a.coverage:
            # what the question asked for, and where the executed SQL does it (computed by code, not the model)
            parts = [f"{'✅' if i['found'] else '❌'} {esc(i['asked'])}" + (f" *({esc(i['where'])})*" if i["where"] else "")
                     for i in a.coverage]
            st.markdown("**Your question → the query:** " + " · ".join(parts))
            st.caption("Checked by code against the SQL that ran in Snowflake, not by the AI."
                       + ("" if all(i["found"] for i in a.coverage) else
                          " ❌ = the query doesn't do this part of the question, so the answer is not high confidence."))
        if a.assumptions:
            st.caption("Assumptions: " + " · ".join(esc(x) for x in a.assumptions))
        if a.number_checks:
            st.markdown('<span class="nx-legend">Numbers: <b style="color:#059669">green</b> = found in the result rows · '
                        '<b style="color:#2563EB">blue</b> = simple calculation from result rows · '
                        '<b style="color:#D97706">orange</b> = not verified</span>', unsafe_allow_html=True)
        if a.status == "clarify" and a.interpretations:
            cols = st.columns(min(3, len(a.interpretations)))
            for i, interp in enumerate(a.interpretations):
                if cols[i % len(cols)].button(interp, key=f"interp-{idx}-{i}"):
                    st.session_state.pending = f"{a.question} (I mean: {interp})"
                    st.rerun()


def tower(a: Answer) -> None:
    """The verification tower: each check this answer went through, with its evidence, from what actually ran."""
    res = a.result
    ok = [c for c in a.candidates if c.ok]
    numbers = a.number_checks
    traced = sum(1 for n in numbers if n.status in ("verified", "derived", "context"))
    covered = sum(1 for i in a.coverage if i["found"])
    repairs = sum(1 for c in a.candidates for t in c.attempts if t.get("stage") == "validate")

    def show_router():
        st.markdown(f"- Write-intent guard: **passed** (the question asks to read, not change, data)")
        st.markdown(f"- Router: answerable · interpreted as *{esc(a.standalone_question)}*")
        for s in a.assumptions:
            st.markdown(f"- Assumption: {esc(s)}")

    def show_candidates():
        st.dataframe(pd.DataFrame([{
            "candidate": CANDIDATE_LABEL.get(c.name, c.name),
            "status": "ran" if c.ok else ("failed" if c.sql else "not built"),
            "rows": c.result.row_count if c.result and c.result.ok else None,
            "note": (c.error or "")[:160]} for c in a.candidates]), width="stretch", hide_index=True)
        plan = next((c.plan for c in a.candidates if c.name == "plan" and c.plan), None)
        if plan:
            st.caption("Gemma's structured plan (compiled to SQL by code using the semantic model):")
            st.json(plan, expanded=False)

    def show_validator():
        st.markdown("Every query must be a single read-only SELECT over the dataset's tables: no writes, no other "
                    "databases, no table functions or Cortex/AI calls, no cartesian joins, known columns only, and "
                    "a row cap. Plans are compiled only along verified many-to-one joins (no double counting).")
        for c in a.candidates:
            for t in c.attempts:
                if t.get("stage") == "validate":
                    st.markdown(f"- {CANDIDATE_LABEL.get(c.name, c.name)}: rejected and repaired — {esc(t['error'][:200])}")
        st.code(a.chosen.sql, language="sql")

    def show_snowflake():
        st.dataframe(pd.DataFrame([{
            "candidate": CANDIDATE_LABEL.get(c.name, c.name), "query id": c.result.query_id,
            "ms": c.result.elapsed_ms, "rows": c.result.row_count, "role": c.result.role} for c in ok]),
            width="stretch", hide_index=True)
        st.caption("Every query carries a QUERY_TAG with this answer's id; look it up in Snowsight → Query History "
                   "or run snowflake/03_evidence_queries.sql.")

    def show_coverage():
        if a.coverage:
            st.dataframe(pd.DataFrame([{"the question asks for": i["asked"], "in the query": "yes" if i["found"] else "NO",
                                        "where": i["where"]} for i in a.coverage]), width="stretch", hide_index=True)
        else:
            st.markdown("The question states no years, values, thresholds or 'top N' for code to check; the "
                        "cross-check and the explanation below still apply.")
        for c in a.candidates:
            if c.issues:
                st.markdown(f"- {CANDIDATE_LABEL.get(c.name, c.name)} failed this check: {esc('; '.join(c.issues))}")

    def show_numbers():
        if numbers:
            st.dataframe(pd.DataFrame([{"number": n.text, "check": n.status, "source": n.source} for n in numbers]),
                         width="stretch", hide_index=True)
        else:
            st.markdown("The answer text contains no numbers to check.")
        if a.narration == "fallback":
            st.markdown("Gemma's sentence used a number not found in the rows, so a templated answer built only from "
                        "the rows is shown instead.")

    blocks: list[tuple[str, bool, str, Callable[[], None]]] = [
        ("🛡️ Read-only guard & question router", True, "question allowed; intent and assumptions stated", show_router),
        ("🧠 Two independent candidates (Gemma)", len(ok) >= 2,
         f"{len(ok)} of {len(a.candidates)} candidate queries ran", show_candidates),
        ("🔍 SQL validator & join rules", True,
         "passed" + (f" after {repairs} repair{'s' if repairs != 1 else ''}" if repairs else ""), show_validator),
        ("❄️ Snowflake execution" if res.engine == "snowflake" else f"🗄️ Query execution ({res.engine}, offline)", True,
         f"{res.row_count} rows in {res.elapsed_ms} ms as {res.role}", show_snowflake),
        ("🧭 Question → query coverage", covered == len(a.coverage),
         f"{covered} of {len(a.coverage)} stated conditions used" if a.coverage else "no explicit conditions to check",
         show_coverage),
        ("🔢 Number grounding", traced == len(numbers) and a.narration != "fallback",
         f"{traced} of {len(numbers)} numbers traced to the rows" if numbers else "no numbers in the answer",
         show_numbers),
    ]
    for i, (title, passed, summary, body) in enumerate(blocks, 1):
        if i > 1:
            st.markdown('<div class="nx-wire"></div>', unsafe_allow_html=True)
        with st.expander(f"{'✅' if passed else '⚠️'} {i}. {title} — {summary}"):
            body()
    st.caption("Built from this answer's own run: nothing here is a fixed claim.")


def render_answer(a: Answer, idx: int) -> None:
    receipt(a, idx)
    if not a.chosen or not a.result:
        if a.alternatives and a.status == "error":
            with st.expander("What went wrong"):
                for alt in a.alternatives:
                    st.write(alt.get("note") or alt)
        return
    res = a.result
    tabs = st.tabs(["📊 Data & chart", "🏛️ Verification tower", "🔍 SQL & Snowflake receipt", "⚖️ Cross-check"])
    with tabs[0]:
        df, shown = result_frame(a)
        chart(df)
        st.dataframe(shown, width="stretch", hide_index=True)
        if res.truncated:
            st.caption(f"Showing the first {res.row_count} rows; the full result is larger.")
        st.caption("Highlighted cells are the ones the answer's numbers come from.")
    with tabs[1]:
        tower(a)
    with tabs[2]:
        st.code(a.chosen.sql, language="sql")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Engine", res.engine)
        c2.metric("Role", res.role or "-")
        c3.metric("Rows", res.row_count)
        c4.metric("Snowflake time", f"{res.elapsed_ms} ms")
        wh = st.session_state.get("warehouse", "")
        st.markdown(f'<span class="nx-mono">query id {html.escape(str(res.query_id))} · answer id {a.answer_id}'
                    f'{" · warehouse " + html.escape(wh) if wh else ""}</span>', unsafe_allow_html=True)
        st.markdown("**How it was computed**")
        for step in a.explanation:
            st.markdown(f"- {esc(step)}")
        st.caption("Generated from the executed SQL by code, not written by the AI, so it always matches what ran.")
        st.download_button("Download evidence (JSON)", json.dumps(a.to_json(), indent=2, default=str),
                           file_name=f"nexora_answer_{a.answer_id}.json", mime="application/json", key=f"dl-{idx}")
    with tabs[3]:
        st.markdown(esc(a.agreement))
        st.dataframe(pd.DataFrame([{
            "candidate": CANDIDATE_LABEL.get(c.name, c.name),
            "status": "ran" if c.ok else ("failed" if c.sql else "not built"),
            "rows": c.result.row_count if c.result and c.result.ok else None,
            "query id": c.result.query_id if c.result else None,
            "chosen": "✓" if c is a.chosen else "",
            "checks": "; ".join(c.issues) if c.issues else ("ok" if c.ok else ""),
            "note": (c.error or "")[:140]} for c in a.candidates]), width="stretch", hide_index=True)
        for alt in a.alternatives:
            if alt.get("summary"):
                st.warning(f"A different reading ({CANDIDATE_LABEL.get(alt.get('candidate'), alt.get('candidate'))}) "
                           f"gave: {alt.get('summary')}")
        for c in a.candidates:
            if c.sql:
                with st.expander(f"{CANDIDATE_LABEL.get(c.name, c.name)} — SQL"):
                    st.code(c.sql, language="sql")
    st.caption(f"{a.model_name} · " + " · ".join(f"{k} {v}s" for k, v in a.timings.items()))


# ---------------------------------------------------------------------------- page
st.session_state.setdefault("turns", [])
st.session_state.setdefault("pending", None)

with st.sidebar:
    st.markdown("## Nexora")
    st.caption("Verified AI data analyst · by Dextro")

    default = next((k for k, v in DATASETS.items() if (ROOT / v) == (ROOT / os.getenv("DATAMIND_DATASET", "x"))),
                   next(iter(DATASETS)))
    label = st.selectbox("Dataset", list(DATASETS), index=list(DATASETS).index(default),
                         help="Same code, different semantic model (config/datasets/*.yaml): reusability by configuration.")
    dataset = DATASETS[label]
    if st.session_state.get("dataset") not in (None, dataset):
        st.session_state.turns = []          # a conversation belongs to one dataset
    st.session_state.dataset = dataset

try:
    agent = get_agent(dataset)
except Exception as e:  # configuration problems are shown, not hidden
    st.error(f"Nexora could not start: {e}")
    st.info("Copy .env.example to .env (or run `python scripts/make_env.py`), run snowflake/01_setup.sql once, "
            "then reload. `python -m datamind check` diagnoses connectivity.")
    st.stop()
st.session_state.warehouse = agent.executor.describe().get("warehouse", "") if hasattr(agent.executor, "describe") else ""

with st.sidebar:
    st.caption(agent.model.data_coverage)
    st.markdown("**System status** · live")
    for name, (state, headline, detail) in system_status(dataset).items():
        st.markdown(f'<div class="nx-status"><span class="nx-dot {state}"></span><b>{name}</b>&nbsp;{html.escape(headline)}</div>'
                    f'<div class="nx-sub">{html.escape(detail)}</div>', unsafe_allow_html=True)
    st.markdown("[![tests](https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml/badge.svg)]"
                "(https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml)")

    role = None
    if getattr(agent.executor, "engine", "") == "snowflake":
        role = ROLES[st.radio("Answer as", list(ROLES), help="The restricted role sees personal data (phones, "
                              "balances, emails) masked by Snowflake dynamic masking policies.")]
    else:
        st.warning("Offline development mode (DuckDB). Not Snowflake — do not use for judging.")

    st.markdown("**Try asking**")
    for q in agent.model.sample_questions:
        if st.button(q, key=f"sample-{q}", width="stretch"):
            st.session_state.pending = q
    with st.expander("⚡ Live data-change demo"):
        st.markdown(
            "Answers are computed by SQL **at question time**, so they change when the data changes:\n"
            "1. Ask: *Which customer generated the most revenue from orders placed in July 1998?*\n"
            "2. In Snowsight run STEP 1–2 of `snowflake/02_demo_data_change.sql` (adds one large order).\n"
            "3. Ask again: a new answer, with a new Snowflake query id.\n"
            "4. STEP 4 shows before vs after with Time Travel; STEP 5 reverts.\n\n"
            "Nexora itself never writes: its role has SELECT only, so the change is made in Snowsight.")
    if st.button("New conversation", width="stretch"):
        st.session_state.turns = []
        st.rerun()
    st.caption(f"Model: {agent.llm.name}")

st.markdown("### Ask your data")
for i, ans in enumerate(st.session_state.turns):
    with st.chat_message("user"):
        st.markdown(esc(ans.question))
    with st.chat_message("assistant"):
        render_answer(ans, i)

placeholder = ("e.g. " + agent.model.sample_questions[0]) if agent.model.sample_questions else "Ask a question"
question = st.chat_input(placeholder)
question = question or st.session_state.pending
if question:
    st.session_state.pending = None
    with st.chat_message("user"):
        st.markdown(esc(question))
    with st.chat_message("assistant"):
        with st.status("Understanding your question", expanded=False) as progress:
            history = [t.history_entry() for t in st.session_state.turns if t.status in ("answered", "empty")]
            ans = agent.ask(question, history=history, role=role,
                            on_step=lambda step: (progress.update(label=step), progress.write(step)))
            progress.update(label=f"Done in {ans.timings.get('total_s', 0):.0f} s", state="complete")
        st.session_state.turns.append(ans)
        render_answer(ans, len(st.session_state.turns) - 1)
