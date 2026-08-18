"""Browse-all-schemes directory page. Lists every gold + silver scheme with its Verified/AI-
Checked/Unverified seal, a search box, and category filter pills (deterministic keyword heuristic
-- see schemelogic/discovery/categories.py for why there's no real category data to filter on
instead, and confirmation this is wired to REAL filtering, not decoration). Routes through the
SAME chat_engine.select_scheme() funnel the chat shortlist and quick-start cards use, then hands
off to app.py via st.switch_page() -- there is deliberately no second selection pathway.

One intentional departure from the Figma reference: cards here still show the Verified/AI-
Checked/Unverified seal next to the title (the reference's card mockup doesn't include one). That
seal is this project's core trust signal, built and hardened across the whole preceding session --
dropping it from the directory would undercut a just-shipped feature for the sake of pixel-parity
on a presentation-only pass, so it stays, clearly flagged as a deliberate deviation.
"""

from __future__ import annotations

import streamlit as st

from schemelogic.conversational import chat_engine, i18n, shared
from schemelogic.discovery.categories import CATEGORIES, categories_for
from schemelogic.discovery.indexer import GOLD_SCHEME_NAMES

st.set_page_config(page_title="SchemeLogic — Browse all schemes", layout="wide")
chat_engine.init_state(st.session_state)
shared.inject_css()
shared.render_nav_bar(active="browse")
shared.render_floating_chat_button()

st.markdown(f'<h1 class="sl-serif">{i18n.t("browse_title")}</h1>', unsafe_allow_html=True)
st.caption(i18n.t("browse_subtitle"))

gold_rows = [
    {"id": scheme_id, "name": name, "source_type": "gold", "description": None, "categories": categories_for(name)}
    for scheme_id, name in sorted(GOLD_SCHEME_NAMES.items(), key=lambda kv: kv[1])
]
silver_rows = [
    {
        "id": r["slug"], "name": r.get("scheme_name") or r["slug"], "source_type": "silver",
        "description": r.get("description"), "categories": categories_for(r.get("scheme_name") or "", r.get("description")),
    }
    for r in shared.get_silver_records()
    if r.get("scheme_name")
]
all_rows = gold_rows + silver_rows

st.session_state.setdefault("browse_category", "all")

search_col, pill_area = st.columns([2, 5])
with search_col:
    query = st.text_input("search", placeholder=i18n.t("search_placeholder"), label_visibility="collapsed")

with pill_area:
    with st.container(key="sl_category_pills"):
        pill_defs = [("all", "category_all")] + [(c, f"category_{c}") for c in CATEGORIES]
        cols = st.columns(len(pill_defs))
        for col, (cat_id, label_key) in zip(cols, pill_defs):
            with col:
                active = st.session_state["browse_category"] == cat_id
                if st.button(i18n.t(label_key), key=f"pill_{cat_id}", type="primary" if active else "secondary"):
                    st.session_state["browse_category"] = cat_id
                    st.rerun()

query_norm = query.strip().lower()
active_category = st.session_state["browse_category"]
rows = all_rows
if query_norm:
    rows = [r for r in rows if query_norm in r["name"].lower()]
if active_category != "all":
    rows = [r for r in rows if active_category in r["categories"]]

MAX_SHOWN = 60  # a 3-col card grid is heavier to render per-row than the old single-column list
st.caption(f"{len(rows)} {i18n.t('schemes_shown_suffix')}")
if len(rows) > MAX_SHOWN:
    st.info(f"Showing the first {MAX_SHOWN} matches — narrow your search or pick a category to see more precisely.")
    rows = rows[:MAX_SHOWN]

CARDS_PER_ROW = 3
for row_start in range(0, len(rows), CARDS_PER_ROW):
    grid_row = rows[row_start : row_start + CARDS_PER_ROW]
    cols = st.columns(CARDS_PER_ROW)
    for col, row in zip(cols, grid_row):
        with col:
            with st.container(border=True, key=f"card_{row['source_type']}_{row['id']}"):
                st.markdown(
                    f'<div class="sl-card-title">{shared.esc(row["name"])}</div>{shared.render_seal(row["source_type"])}',
                    unsafe_allow_html=True,
                )
                if row["description"]:
                    snippet = shared.esc(row["description"][:140])
                    snippet += "..." if len(row["description"]) > 140 else ""
                    st.markdown(f'<div class="sl-card-snippet">{snippet}</div>', unsafe_allow_html=True)
                if st.button(f'{i18n.t("view_details")} →', key=f"browse_select_{row['source_type']}_{row['id']}"):
                    deps = shared.build_deps()
                    with st.spinner("..."):
                        chat_engine.select_scheme(st.session_state, row["id"], row["source_type"], deps)
                    st.switch_page("app.py")
