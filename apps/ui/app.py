"""DeskFleet support operations console (Streamlit).

A focused console for support agents: paste a ticket, resolve it through the
multi-agent API, and inspect the decision, drafted reply, tool-call audit trail,
and observability links. Talks to the API over HTTP (``API_URL``).
"""

from __future__ import annotations

import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
REQUEST_TIMEOUT = 60

DECISION_STYLES = {
    "RESOLVED": {"color": "#1a7f37", "emoji": "✅", "label": "Resolved"},
    "ESCALATE": {"color": "#9a6700", "emoji": "⚠️", "label": "Escalated"},
    "REFUSE": {"color": "#cf222e", "emoji": "⛔", "label": "Refused"},
}

st.set_page_config(
    page_title="DeskFleet · Support Console",
    page_icon="\U0001f39f️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _api_get(path: str, **params):
    try:
        resp = requests.get(f"{API_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json(), None
    except requests.RequestException as exc:
        return None, str(exc)


def _api_post(path: str, payload: dict):
    try:
        resp = requests.post(f"{API_URL}{path}", json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 422:
            return None, "Validation error: ticket text is required."
        resp.raise_for_status()
        return resp.json(), None
    except requests.RequestException as exc:
        return None, str(exc)


def render_decision_badge(decision: str) -> None:
    style = DECISION_STYLES.get(decision, {"color": "#57606a", "emoji": "❓", "label": decision})
    st.markdown(
        f"""
        <div role="status" aria-label="Decision: {style['label']}"
             style="display:inline-block;padding:6px 16px;border-radius:999px;
                    background:{style['color']};color:#fff;font-weight:700;
                    font-size:1rem;letter-spacing:.02em;">
            {style['emoji']} {style['label']}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_result(result: dict) -> None:
    top = st.columns([2, 1, 1, 1])
    with top[0]:
        render_decision_badge(result.get("decision", "?"))
    top[1].metric("Category", (result.get("category") or "n/a").title())
    top[2].metric("Review loops", result.get("iterations", 0))
    top[3].metric("Latency", f"{result.get('latency_ms', 0):.0f} ms")

    st.caption(
        f"Ticket ID `{result.get('ticket_id', '?')}` · "
        f"estimated cost ${result.get('cost_usd', 0):.6f}"
    )

    decision = result.get("decision")
    if decision == "RESOLVED":
        st.subheader("Drafted reply")
        st.success(result.get("reply") or "(empty)")
    elif decision == "ESCALATE":
        st.subheader("Escalated to a human")
        st.warning(result.get("escalation_reason") or "No reason provided.")
        if result.get("reply"):
            with st.expander("Draft prepared before escalation"):
                st.write(result["reply"])
    elif decision == "REFUSE":
        st.subheader("Request refused")
        st.error(result.get("escalation_reason") or "Refused by guardrails.")

    tool_calls = result.get("tool_calls") or []
    st.subheader(f"Tool-call audit trail ({len(tool_calls)})")
    if tool_calls:
        rows = [
            {
                "Tool": c.get("tool_name"),
                "Status": c.get("status"),
                "Args": c.get("args"),
                "Result": c.get("result"),
            }
            for c in tool_calls
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if any(c.get("status") == "blocked" for c in tool_calls):
            st.info("\U0001f6e1️ One or more off-allowlist tool calls were blocked and audited.")
    else:
        st.caption("No tools were called for this ticket.")

    trace = result.get("langsmith_trace_url")
    if trace:
        st.link_button("\U0001f517 Open LangSmith trace", trace)


def sidebar() -> None:
    with st.sidebar:
        st.header("\U0001f39f️ DeskFleet")
        st.caption("Multi-agent support ticket resolver")

        health, err = _api_get("/health")
        if err:
            st.error(f"API unreachable at {API_URL}")
        else:
            llm = "live LLM" if health.get("llm_configured") else "no key (demo)"
            st.success(f"API online · {llm}")

        st.divider()
        st.subheader("Recent tickets")
        tickets, terr = _api_get("/tickets", limit=8)
        if terr or not tickets:
            st.caption("No recent tickets yet.")
        else:
            for t in tickets:
                style = DECISION_STYLES.get(t.get("decision", ""), {"emoji": "❓"})
                with st.expander(f"{style['emoji']} {t.get('body', '')[:48]}"):
                    st.write(f"**Decision:** {t.get('decision')}")
                    st.write(f"**Category:** {t.get('category')}")
                    if t.get("reply"):
                        st.write(f"**Reply:** {t.get('reply')}")
                    if t.get("escalation_reason"):
                        st.write(f"**Reason:** {t.get('escalation_reason')}")


def main() -> None:
    sidebar()
    st.title("Support ticket resolver")
    st.caption(
        "Paste a customer ticket. The Classifier → Researcher → Responder → Reviewer "
        "agents resolve, escalate, or refuse it — with injection and PII guardrails."
    )

    with st.form("resolve_form"):
        ticket = st.text_area(
            "Ticket text",
            height=160,
            placeholder="e.g. Where is my order 3? It's been two weeks.",
            help="The customer's message. PII is automatically redacted.",
        )
        order_id = st.text_input("Order ID (optional)", placeholder="e.g. 3")
        submitted = st.form_submit_button("Resolve ticket", type="primary")

    if submitted:
        if not ticket.strip():
            st.warning("Please enter ticket text.")
            return
        payload = {"ticket": ticket}
        if order_id.strip():
            payload["order_id"] = order_id.strip()
        with st.spinner("Running the agent graph..."):
            result, err = _api_post("/resolve", payload)
        if err:
            st.error(err)
        elif result:
            render_result(result)


if __name__ == "__main__":
    main()
