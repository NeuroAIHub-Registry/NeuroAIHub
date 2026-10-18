import base64
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # server: render charts to images only
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data_utils import load_data, site_records, COLUMNS, DATABASE_UPDATED, refresh_package  # also puts ../package on the path
refresh_package()  # pick up updated agent/data code after a push (Streamlit only reloads files inside web_app/)
from ui_utils import display_paginated_dataframe
from neuroaihub.agent import NeuroAIAgent
from neuroaihub.agent_tools import DatasetTools
import usage_log

SITE_DIR = Path(__file__).resolve().parent / "site"
REPO = "https://github.com/NeuroAIHub-Registry/NeuroAIHub"
# Public link of the "Submit a dataset" Google Form (see dataset_submissions/SETUP.md); '' hides the submit buttons.
SUBMIT_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfCCAqT9-tx4he0kocomjPqSv4TsO96qrbroEiisgmyQOod_g/viewform"
PAPER = "https://www.ajnr.org/content/early/2026/04/24/ajnr.A9363"

st.set_page_config(page_title="NeuroAIHub — Neuroradiology Dataset Discovery", page_icon=(SITE_DIR / "logo.svg").read_text(encoding="utf-8"),
                   layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------- page styling (matches site/index.html)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{ --frost:#CDEFFF; --sparkle:#7AD9FF; --ocean:#1AA3D9; --deep:#123B4A; --bg:#F3FBFF; --bg-soft:#E9F7FF;
  --grad:linear-gradient(100deg,#7AD9FF,#1AA3D9); --shadow:0 20px 48px -20px rgba(26,163,217,.32); }
html, body, .stApp, [data-testid="stAppViewContainer"]{ background:var(--bg) !important; overflow-x:hidden; }
.stApp, .stApp p, .stApp li, .stApp input, .stApp textarea, .stApp button{ font-family:'Inter',system-ui,sans-serif; }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer{ display:none !important; }
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"]{ display:none; }
.block-container, [data-testid="stAppViewBlockContainer"]{ max-width:1200px; padding:0 24px 0 !important; }
/* the website iframe runs edge to edge */
iframe[title="st.iframe"]{ display:block; width:100vw !important; max-width:none; position:relative; left:50%; margin-left:-50vw; border:0; }
/* chat section */
.nai-head{ max-width:720px; margin:70px 0 26px; scroll-margin-top:20px; }
.nai-eyebrow{ display:inline-flex; align-items:center; gap:8px; font-size:.75rem; font-weight:600; letter-spacing:.16em;
  text-transform:uppercase; color:var(--ocean); padding:7px 14px; border-radius:999px; border:1px solid var(--frost);
  background:#fff; margin-bottom:20px; box-shadow:0 4px 14px -6px rgba(26,163,217,.18); }
.nai-eyebrow i{ width:6px; height:6px; border-radius:50%; background:var(--sparkle); box-shadow:0 0 0 4px rgba(122,217,255,.35); }
.nai-title{ font-family:'Space Grotesk','Inter',sans-serif !important; font-size:clamp(1.9rem,4vw,2.9rem) !important; font-weight:700 !important;
  color:var(--deep) !important; letter-spacing:-.02em; line-height:1.15 !important; padding:0 !important; margin:0 !important; }
.nai-title .accent{ background:var(--grad); -webkit-background-clip:text; background-clip:text; color:transparent; }
.nai-lede{ color:rgba(18,59,74,.72); font-size:1.05rem; margin-top:18px; }
/* about us: compact, one row on desktop */
.nai-team{ display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:12px; margin-bottom:10px; }
.nai-member{ background:#fff; border:1px solid var(--frost); border-radius:14px; padding:14px 10px 12px; text-align:center;
  box-shadow:0 4px 14px -8px rgba(26,163,217,.18); display:flex; flex-direction:column; align-items:center; }
.nai-member img{ width:68px; height:68px; border-radius:50%; object-fit:cover; border:2px solid var(--frost); margin-bottom:8px; }
.nai-member .name{ font-family:'Space Grotesk','Inter',sans-serif; font-weight:700; font-size:.88rem; line-height:1.25; color:var(--deep); }
.nai-member .role{ font-size:.58rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--ocean); margin:4px 0 5px; }
.nai-member .blurb{ font-size:.72rem; color:rgba(18,59,74,.68); line-height:1.4; margin:0 0 8px; }
.nai-member .links{ display:flex; flex-wrap:wrap; justify-content:center; gap:4px; margin-top:auto; }
.nai-member .links a{ font-size:.64rem; font-weight:600; color:var(--ocean) !important; text-decoration:none !important;
  border:1px solid var(--frost); background:var(--bg-soft); border-radius:999px; padding:2px 8px; }
.nai-member .links a:hover{ border-color:var(--ocean); }
.nai-member.lead{ border-color:var(--sparkle); }
@media (max-width:1000px){ .nai-team{ grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width:560px){ .nai-team{ grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; } }
[data-testid="stExpander"] details{ background:#fff; border:1px solid var(--frost); border-radius:14px; }
[data-testid="stExpander"] summary p{ font-weight:600; color:var(--deep); }
[data-testid="stChatMessage"]{ background:#fff; border:1px solid var(--frost); border-radius:16px; padding:14px 16px; }
[data-testid="stChatInput"]{ border-radius:14px; }
[data-testid="stTextInput"] input{ background:var(--bg-soft); }
/* footer */
.nai-footer{ width:100vw; position:relative; left:50%; margin-left:-50vw; margin-top:80px; background:#fff;
  border-top:1px solid var(--frost); padding:52px 0 30px; }
.nai-footer .in{ max-width:1200px; margin:0 auto; padding:0 24px; display:grid; grid-template-columns:1.6fr 1fr 1fr; gap:40px; }
.nai-footer .brand{ font-family:'Space Grotesk','Inter',sans-serif; font-weight:700; font-size:1.12rem; color:var(--deep); }
.nai-footer .brand b{ color:var(--ocean); }
.nai-footer p{ font-size:.86rem; color:rgba(18,59,74,.55); margin-top:12px; max-width:320px; }
.nai-footer h5{ font-family:'Space Grotesk','Inter',sans-serif; font-size:.78rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--ocean); margin:0 0 14px; font-weight:700; padding:0; }
.nai-footer a{ display:block; font-size:.87rem; color:rgba(18,59,74,.6) !important; padding:4px 0; text-decoration:none !important; }
.nai-footer a:hover{ color:var(--ocean) !important; }
.nai-footer .bottom{ max-width:1200px; margin:40px auto 0; padding:22px 24px 0; border-top:1px solid var(--frost);
  font-size:.8rem; color:rgba(18,59,74,.5); display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; }
@media (max-width:720px){
  .block-container, [data-testid="stAppViewBlockContainer"]{ padding:0 16px !important; }
  .nai-footer .in{ grid-template-columns:1fr; gap:26px; padding:0 16px; }
  .nai-footer .bottom{ padding:22px 16px 0; }
}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- data + website
dataframes, combined_df, sheet_names = load_data()


@st.cache_data(show_spinner=False)
def build_site(_df: pd.DataFrame, categories: tuple, template_mtime: float, logo_mtime: float, log_url: str, form_url: str) -> str:
    payload = {"rows": site_records(_df), "categories": list(categories), "columns": COLUMNS, "updated": DATABASE_UPDATED}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    logo = "data:image/svg+xml;base64," + base64.b64encode((SITE_DIR / "logo.svg").read_bytes()).decode()
    html = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("__LOGO__", logo).replace("__DATA__", data).replace("__LOG_URL__", json.dumps(log_url)) \
        .replace("__FORM_URL__", json.dumps(form_url))


# Initial height only; the page resizes its own frame to fit the content.
site_html = build_site(combined_df, tuple(sheet_names), (SITE_DIR / "index.html").stat().st_mtime,
                       (SITE_DIR / "logo.svg").stat().st_mtime, usage_log.endpoint(),
                       SUBMIT_FORM_URL)
components.html(site_html, height=4200, scrolling=False)

# ---------------------------------------------------------------- chat with NeuroAI
st.markdown("""
<div class="nai-head" id="chat">
  <span class="nai-eyebrow"><i></i> NeuroAI Chat Agent</span>
  <h2 class="nai-title">Chat with <span class="accent">NeuroAI</span></h2>
  <p class="nai-lede">Ask for dataset recommendations, comparisons, custom counts and plots in plain language.
  Connect any OpenAI-compatible model to start.</p>
</div>""", unsafe_allow_html=True)

for key in ("api_key", "base_url", "model"):
    st.session_state.setdefault(key, "")
# Keep the values when their widgets are not drawn in a run (explicit assignment works on all Streamlit versions).
for key in ("api_key", "base_url", "model"):
    st.session_state[key] = st.session_state[key]
st.session_state.setdefault("show_connection", False)

user_api_key = st.session_state.api_key.strip()
user_model = st.session_state.model.strip()
connected = bool(user_api_key and user_model)

if not (connected or st.session_state.show_connection):
    # Clean first view: one button instead of empty input boxes.
    if st.button("🔑 Connect your API key and model to start chatting", type="primary"):
        st.session_state.show_connection = True
        st.rerun()
else:
    with st.expander("🔑 Model connection" + (f" — {user_model}" if connected else ""), expanded=not connected):
        c1, c2, c3 = st.columns(3)
        c1.text_input("API key", type="password", placeholder="sk-...", key="api_key")
        c2.text_input("Base URL (optional)", placeholder="https://api.openai.com/v1", key="base_url",
                      help="Leave empty for OpenAI. Any OpenAI-compatible endpoint works, e.g. https://openrouter.ai/api/v1")
        c3.text_input("Model name", placeholder="e.g. gpt-5", key="model",
                      help="The model must support tool (function) calling.")
        st.caption("Your key is used only for this session and is not stored. Free option: get a key at "
                   "[OpenRouter](https://openrouter.ai/keys), use the base URL `https://openrouter.ai/api/v1` and a free "
                   "model such as [nvidia/nemotron-3-super-120b-a12b:free]"
                   "(https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free) "
                   "(free models are rate-limited and can be slow).")

# Per-session tool state (it remembers the last search for follow-up questions).
if "agent_tools" not in st.session_state:
    st.session_state.agent_tools = DatasetTools(combined_df, sheet_names)
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help you explore the neuroradiology datasets today? "
                                  "Ask me to find, compare, count or plot datasets, or to recommend some for your project."}]


def render_message(i, msg):
    with st.chat_message(msg["role"]):
        if msg.get("content"):
            st.markdown(msg["content"])
        for img in msg.get("images", []):
            st.image(base64.b64decode(img), width=720)
        for t, (title, table) in enumerate(msg.get("tables", [])):
            if table is not None and not table.empty:
                st.caption(title)
                display_paginated_dataframe(table, state_key=f"page_agent_{i}_{t}")
        if msg.get("steps"):
            with st.expander(f"How this answer was found ({len(msg['steps'])} database lookup{'s' if len(msg['steps']) != 1 else ''})"):
                for name, args in msg["steps"]:
                    st.code(f"{name}({json.dumps(args, ensure_ascii=False)})", language="python")


if connected:
    for i, msg in enumerate(st.session_state.messages):
        render_message(i, msg)
    if st.session_state.get("chat_error"):
        st.error(st.session_state.pop("chat_error"))

    # Inside a container the chat box stays under the conversation instead of floating over the page.
    with st.container():
        user_query = st.chat_input("Let's talk about neuroradiology datasets!")
    if user_query:
        history = [{"role": m["role"], "content": m.get("content", "")} for m in st.session_state.messages[1:]]
        base_url = st.session_state.base_url.strip() or None
        with st.spinner("🧠 Searching the database..."):
            started = time.time()
            agent = NeuroAIAgent(st.session_state.agent_tools, user_api_key, user_model, base_url)
            result = agent.ask(user_query, history)
        turn = sum(1 for m in st.session_state.messages if m["role"] == "user") + 1
        usage_log.log_chat(user_query, result, user_model, base_url, turn, time.time() - started)
        if result.error:
            st.session_state.chat_error = f"{result.error}\n\nYour question was: _{user_query}_"
        else:
            st.session_state.messages.append({"role": "user", "content": user_query})
            st.session_state.messages.append({"role": "assistant", "content": result.text, "tables": result.tables[-1:],
                                              "images": result.images, "steps": result.steps})
        st.rerun()

    if usage_log.endpoint():
        st.caption("Questions and filter choices are logged anonymously (no API keys, IP addresses or personal data) to "
                   "improve NeuroAIHub. Please don't include personal information in your questions.")

# ---------------------------------------------------------------- about us
TEAM = [
    ("benyamin-gheiji", "Benyamin Gheiji", "Project Lead", "MD Candidate · ML Engineer · Medical Imaging AI Researcher",
     [("Portfolio", "https://benyamin-gheiji.github.io/"),
      ("LinkedIn", "https://www.linkedin.com/in/benyamin-gheiji-4a0668260"),
      ("Scholar", "https://scholar.google.com/citations?user=0Fdy24gAAAAJ&hl=en"),
      ("GitHub", "https://github.com/benyamin-gheiji"), ("Email", "mailto:benyamingheiji@gmail.com")]),
    ("mohammad-hossein-kazemi", "Mohammad Hossein Kazemi", "Project Contributor",
     "Computer Engineering-DBA Candidate | Creating Organically",
     [("Portfolio", "https://thisiskazzi.github.io/"), ("GitHub", "https://github.com/thisiskazzi")]),
    ("sana-shokrani", "Sana Shokrani", "Project Contributor",
     "MD Candidate at Tehran University of Medical Sciences · Neurosurgery Researcher",
     [("LinkedIn", "https://www.linkedin.com/in/sana-shokrani-6392512a4"), ("Email", "mailto:sanashokrani061@gmail.com")]),
    ("danial-elyassirad", "Danial Elyassirad", "Project Contributor", "Medical Doctor · Medical Imaging AI Researcher",
     [("Website", "https://danialelyassirad.github.io/"),
      ("Scholar", "https://scholar.google.com/citations?user=RzDOvMwAAAAJ&hl=en"),
      ("LinkedIn", "https://www.linkedin.com/in/danial-elyassirad")]),
    ("mahsa-vatanparast", "Mahsa Vatanparast", "Project Contributor", "Medical Doctor · Medical Imaging AI Researcher",
     [("Scholar", "https://scholar.google.com/citations?user=rEmIJDIAAAAJ&hl=en"),
      ("LinkedIn", "https://www.linkedin.com/in/mahsa-vatanparast-24314b2a7")]),
    ("shahriar-faghani", "Shahriar Faghani", "Supervisor & Mentor",
     "Radiology Resident at the University of Pennsylvania · Adjunct Assistant Professor of Radiology at Mayo Clinic",
     [("Scholar", "https://scholar.google.com/citations?user=6HV5eJAAAAAJ&hl=en"),
      ("LinkedIn", "https://www.linkedin.com/in/shahriar-faghani-7b468082")]),
]


@st.cache_data(show_spinner=False)
def team_html(photos_mtime: float) -> str:
    cards = []
    for slug, name, role, blurb, links in TEAM:
        photo = base64.b64encode((SITE_DIR / "team" / f"{slug}.webp").read_bytes()).decode()
        anchors = "".join(f'<a href="{url}" target="_blank" rel="noopener">{label}</a>' for label, url in links)
        cards.append(f'<div class="nai-member{" lead" if role == "Project Lead" else ""}">'
                     f'<img src="data:image/webp;base64,{photo}" alt="{name}" />'
                     f'<div class="name">{name}</div><div class="role">{role}</div>'
                     f'<p class="blurb">{blurb}</p><div class="links">{anchors}</div></div>')
    return ("""<div class="nai-head" id="about">
  <span class="nai-eyebrow"><i></i> About us</span>
  <h2 class="nai-title">The <span class="accent">NeuroAIHub</span> team</h2>
  <p class="nai-lede">The people who build NeuroAIHub and keep its database up to date.</p>
</div>""" + f'<div class="nai-team">{"".join(cards)}</div>')


st.markdown(team_html(max(p.stat().st_mtime for p in (SITE_DIR / "team").glob("*.webp"))), unsafe_allow_html=True)

# ---------------------------------------------------------------- footer
st.markdown(f"""
<div class="nai-footer">
  <div class="in">
    <div>
      <div class="brand">Neuro<b>AI</b>Hub</div>
      <p>An AI-driven framework for neuroradiology dataset discovery — easier, smarter, and always up to date.
      Database last updated {DATABASE_UPDATED}.</p>
    </div>
    <div>
      <h5>Project</h5>
      <a href="{REPO}" target="_blank" rel="noopener">GitHub repository</a>
      <a href="{REPO}#-offline-installation" target="_blank" rel="noopener">Offline installation guide</a>
      <a href="{PAPER}" target="_blank" rel="noopener">Research paper (AJNR)</a>
    </div>
    <div>
      <h5>Community</h5>
      <a href="{SUBMIT_FORM_URL or REPO + '#-community-contributions'}" target="_blank" rel="noopener">Submit a dataset</a>
      <a href="{REPO}/issues" target="_blank" rel="noopener">Report an issue</a>
      <a href="https://drive.google.com/file/d/1nG2cF6pN9CP4lofSQuYMhFwRZCHMdxeM/view?usp=drive_link" target="_blank" rel="noopener">Demo video</a>
    </div>
  </div>
  <div class="bottom">
    <span>© 2026 NeuroAIHub · Licensed under CC BY-NC-ND 4.0.</span>
    <span>{len(combined_df)} datasets · {len(sheet_names)} categories</span>
  </div>
</div>""", unsafe_allow_html=True)
