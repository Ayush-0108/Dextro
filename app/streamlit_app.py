"""Nexora (package: datamind) — Streamlit UI.  Run:  streamlit run app/streamlit_app.py"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datamind.config import build, load_dotenv  # noqa: E402
from datamind.pipeline import Answer  # noqa: E402

load_dotenv()
st.set_page_config(page_title="Nexora", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; max-width: 1180px;}
  .dm-chip {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:600;
            margin-right:6px; border:1px solid rgba(128,128,128,.35);}
  .dm-high {background:#e6f4ea; color:#137333; border-color:#a8dab5;}
  .dm-medium {background:#fef7e0; color:#8a5a00; border-color:#f6d77a;}
  .dm-low {background:#fce8e6; color:#a50e0e; border-color:#f4b4ae;}
  .dm-neutral {background:rgba(128,128,128,.08);}
  .dm-legend {font-size:0.78rem; opacity:.8;}
</style>
""", unsafe_allow_html=True)

ROLES = {"Analyst (full access)": "DATAMIND_AGENT", "Restricted (PII masked)": "DATAMIND_RESTRICTED"}
STATUS_LABEL = {"answered": "Answered", "empty": "No matching rows", "clarify": "Needs clarification",
                "not_in_data": "Not in this data", "refused": "Declined", "chitchat": "About Nexora",
                "error": "Could not answer"}


@st.cache_resource(show_spinner="Connecting to Snowflake and Gemma...")
def get_agent():
    return build()


def esc(text: str) -> str:
    """Escape characters Streamlit markdown would interpret ($ = LaTeX, etc.)."""
    return text.replace("\\", "\\\\").replace("$", "\\$").replace("[", "\\[").replace("]", "\\]")


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


def chip(label: str, kind: str) -> str:
    return f'<span class="dm-chip dm-{kind}">{label}</span>'


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
                s.loc[r, c] = "background-color: rgba(52,168,83,.25); font-weight:600"
        return s
    return df, df.style.apply(style, axis=None)


def maybe_chart(df: pd.DataFrame) -> None:
    if not 2 <= len(df) <= 60 or df.shape[1] < 2:
        return
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    lab = [c for c in df.columns if c not in num]
    if len(lab) == 1 and num:
        series = df.set_index(lab[0])[num[:1]]
        if re.search(r"date|year|month|quarter|week", lab[0]):
            st.line_chart(series, height=240)
        else:
            st.bar_chart(series, height=240)
    elif not lab and len(num) >= 2 and re.search(r"year|month|quarter", num[0]):
        st.line_chart(df.set_index(num[0])[num[1:2]], height=240)


def render_answer(a: Answer, idx: int, show_candidates: bool) -> None:
    chips = [chip(STATUS_LABEL.get(a.status, a.status), "neutral")]
    if a.confidence:
        chips.append(chip(f"{a.confidence} confidence", a.confidence))
    if a.narration == "fallback" and a.status == "answered":
        chips.append(chip("templated answer", "neutral"))
    st.markdown(" ".join(chips), unsafe_allow_html=True)
    st.markdown(highlighted(a) if a.number_checks else esc(a.message))
    if a.standalone_question and a.standalone_question.strip().lower() != a.question.strip().lower():
        st.caption(f"Interpreted as: {esc(a.standalone_question)}")
    if a.coverage:
        # the question -> query check: what was asked, and where the executed SQL does it (computed by code)
        parts = [f"{'✅' if i['found'] else '❌'} {esc(i['asked'])}" + (f" *({esc(i['where'])})*" if i["where"] else "")
                 for i in a.coverage]
        st.markdown("**Your question → the query:** " + " · ".join(parts))
        st.caption("Checked by code against the SQL that ran in Snowflake, not by the AI."
                   + ("" if all(i["found"] for i in a.coverage) else " ❌ = the query doesn't do this part of the question,"
                      " so the answer is not marked high confidence."))
    if a.assumptions:
        st.caption("Assumptions: " + " · ".join(esc(x) for x in a.assumptions))
    if a.status == "clarify" and a.interpretations:
        cols = st.columns(min(3, len(a.interpretations)))
        for i, interp in enumerate(a.interpretations):
            if cols[i % len(cols)].button(interp, key=f"interp-{idx}-{i}"):
                st.session_state.pending = f"{a.question} (I mean: {interp})"
                st.rerun()
    if a.number_checks:
        st.markdown('<span class="dm-legend">Numbers: '
                    '<b style="color:#137333">green</b> = found in the result rows · '
                    '<b style="color:#1a73e8">blue</b> = simple calculation from result rows · '
                    '<b style="color:#b06000">orange</b> = not verified</span>', unsafe_allow_html=True)
    if not a.chosen or not a.result:
        if a.alternatives and a.status == "error":
            with st.expander("What went wrong"):
                for alt in a.alternatives:
                    st.write(alt.get("note") or alt)
        return
    res = a.result
    tabs = st.tabs(["Result", "How it was computed", "SQL & evidence", "Cross-check"])
    with tabs[0]:
        df, shown = result_frame(a)
        st.dataframe(shown, width="stretch", hide_index=True)
        if res.truncated:
            st.caption(f"Showing the first {res.row_count} rows; the full result is larger.")
        maybe_chart(df)
    with tabs[1]:
        for step in a.explanation:
            st.markdown(f"- {esc(step)}")
        st.caption("Generated from the executed SQL by code, not written by the AI, so it always matches what ran.")
        if a.number_checks:
            st.markdown("**Where each number in the answer comes from**")
            st.dataframe(pd.DataFrame([{"number": n.text, "check": n.status, "source": n.source}
                                       for n in a.number_checks]), width="stretch", hide_index=True)
    with tabs[2]:
        st.code(a.chosen.sql, language="sql")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Engine", res.engine)
        c2.metric("Role", res.role or "-")
        c3.metric("Rows", res.row_count)
        c4.metric("Time", f"{res.elapsed_ms} ms")
        st.markdown(f"Snowflake query id: `{res.query_id}` · answer id: `{a.answer_id}`")
        st.caption("Look it up in Snowsight → Monitoring → Query History, or run snowflake/03_evidence_queries.sql.")
        st.download_button("Download evidence (JSON)", json.dumps(a.to_json(), indent=2, default=str),
                           file_name=f"datamind_answer_{a.answer_id}.json", mime="application/json",
                           key=f"dl-{idx}")
    with tabs[3]:
        st.write(a.agreement)
        rows = []
        for c in a.candidates:
            r = c.result
            rows.append({"candidate": {"plan": "semantic plan → compiled SQL", "sql": "direct SQL",
                                       "sql_alt": "independent re-derivation"}.get(c.name, c.name),
                         "status": "ran" if c.ok else ("failed" if c.sql else "not built"),
                         "rows": r.row_count if r and r.ok else None,
                         "query id": r.query_id if r else None,
                         "chosen": "✓" if c is a.chosen else "",
                         "note": (c.error or "")[:140]})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        for alt in a.alternatives:
            st.warning(f"A different reading ({alt.get('candidate')}) gave: {alt.get('summary')}")
        if show_candidates:
            for c in a.candidates:
                if c.sql:
                    with st.expander(f"{c.name} SQL"):
                        st.code(c.sql, language="sql")
                        if c.plan:
                            st.json(c.plan)
    st.caption(f"{a.model_name} · " + " · ".join(f"{k} {v}s" for k, v in a.timings.items()))


# ---------------------------------------------------------------------------- page
try:
    agent = get_agent()
except Exception as e:  # configuration problems are shown, not hidden
    st.error(f"Nexora could not start: {e}")
    st.info("Copy .env.example to .env, fill in your Snowflake account and GEMINI_API_KEY, "
            "run snowflake/01_setup.sql once, then reload. `python -m datamind check` diagnoses connectivity.")
    st.stop()

st.session_state.setdefault("turns", [])
st.session_state.setdefault("pending", None)

with st.sidebar:
    st.markdown("## Nexora")
    st.caption("Verified AI data analyst · by Dextro")
    st.caption("Ask questions in plain English. Every answer is computed by SQL in Snowflake, cross-checked, "
               "and shown with the query and rows behind it.")
    st.markdown(f"**Dataset:** {agent.model.title}")
    st.caption(agent.model.data_coverage)
    engine = getattr(agent.executor, "engine", "")
    role = None
    if engine == "snowflake":
        label = st.radio("Answer as", list(ROLES), help="The restricted role sees customer phone numbers and "
                         "balances masked by a Snowflake masking policy.")
        role = ROLES[label]
    else:
        st.warning("Offline development mode (DuckDB). Not Snowflake — do not use for judging.")
    show_candidates = st.toggle("Show every candidate query", value=False)
    st.markdown("**Try asking**")
    for q in agent.model.sample_questions:
        if st.button(q, key=f"sample-{q}", width="stretch"):
            st.session_state.pending = q
    if st.button("New conversation", width="stretch"):
        st.session_state.turns = []
        st.rerun()
    st.caption(f"Model: {agent.llm.name}")

st.markdown("### Ask your data")
for i, ans in enumerate(st.session_state.turns):
    with st.chat_message("user"):
        st.markdown(esc(ans.question))
    with st.chat_message("assistant"):
        render_answer(ans, i, show_candidates)

question = st.chat_input("e.g. Which 5 nations generated the most revenue from ASIA customers in 1994?")
question = question or st.session_state.pending
if question:
    st.session_state.pending = None
    with st.chat_message("user"):
        st.markdown(esc(question))
    with st.chat_message("assistant"):
        with st.status("Understanding your question", expanded=False) as progress:
            history = [t.history_entry() for t in st.session_state.turns if t.status in ("answered", "empty")]
            ans = agent.ask(question, history=history, role=role,
                            on_step=lambda label: (progress.update(label=label), progress.write(label)))
            progress.update(label=f"Done in {ans.timings.get('total_s', 0):.0f} s", state="complete")
        st.session_state.turns.append(ans)
        render_answer(ans, len(st.session_state.turns) - 1, show_candidates)
