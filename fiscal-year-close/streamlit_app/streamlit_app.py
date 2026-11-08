import streamlit as st

from fyc import data
from fyc.config import is_production, settings

st.set_page_config(page_title="Fiscal year close", page_icon=":material/event_available:", layout="wide")

cfg = settings()
st.session_state.setdefault("environment", cfg.environment_name)

missing = cfg.missing()
if missing:
    st.error(
        "The app cannot sign in to Business Central. Add these values to the .env file next to "
        f"streamlit_app.py: {', '.join(missing)}."
    )
    st.stop()

with st.sidebar:
    st.text_input(
        "Business Central environment",
        key="environment",
        on_change=data.clear_caches,
        help="The extension is installed once per environment and is then available in every company in it.",
    )
    env = st.session_state.environment
    if is_production(env):
        if not cfg.allow_production_updates:
            st.info(
                "Production is read-only. Set ALLOW_PRODUCTION_UPDATES=true in .env to allow changes.",
                icon=":material/lock:",
            )
        elif data.writes_allowed():
            st.warning(f"**{env}** is unlocked for this session. Changes and runs are live.", icon=":material/warning:")
            if st.button("Lock production again", icon=":material/lock:", width="stretch"):
                st.session_state.pop("production_unlocked_for", None)
                st.rerun()
        else:
            st.info(f"**{env}** is locked. You can look, but not change or run anything.", icon=":material/lock:")
            typed = st.text_input(
                "Type the environment name to unlock it for this session",
                key=f"unlock_{env}",
                placeholder=env,
            )
            if typed.strip() == env:
                st.session_state.production_unlocked_for = env
                st.rerun()
            elif typed:
                st.caption("That does not match the environment name.")
    else:
        st.success("Sandbox environment.", icon=":material/science:")
    st.caption(f"Tenant {cfg.tenant_id}")
    if st.button("Refresh from Business Central", icon=":material/refresh:", width="stretch"):
        data.clear_caches()
        st.rerun()

try:
    data.load_companies(st.session_state.environment)
except Exception as exc:  # noqa: BLE001 - show any connection problem to the user
    st.error(f"Could not list the companies in **{st.session_state.environment}**. {exc}")
    st.stop()

page = st.navigation(
    [
        st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:", default=True),
        st.Page("app_pages/setup.py", title="Setup", icon=":material/tune:"),
        st.Page("app_pages/run.py", title="Run", icon=":material/play_circle:"),
        st.Page("app_pages/posting_dates.py", title="Posting dates", icon=":material/date_range:"),
        st.Page("app_pages/log.py", title="Log", icon=":material/history:"),
    ],
    position="top",
)
page.run()
