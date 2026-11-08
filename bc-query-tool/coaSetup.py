import io
import json
import logging

import pandas as pd
import streamlit as st

import importlib

import coaCore as coa

# Streamlit re-runs this page on every refresh but keeps imported modules from
# when it started, so a fix to coaCore.py would otherwise need the console
# window closed and reopened. Reloading is cheap: it holds no state.
coa = importlib.reload(coa)

# RUN IN TERMINAL: streamlit run coaSetup.py

logging.basicConfig(
    filename="./logging/query_tool.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s",
)

st.set_page_config(page_title="Chart of Accounts", layout="wide")
st.title("📒 Chart of Accounts — add G/L accounts to every entity")
st.write(
    "Enter a G/L account once, with every card field and its default dimensions, "
    "and create it identically in each selected entity. Nothing is written until "
    "you have reviewed a dry run and approved it, and every account is read back "
    "afterwards to confirm it matches. **An account that already exists in an "
    "entity is never changed.**"
)

if coa.IS_PRODUCTION:
    st.error(f"Business Central environment: **{coa.ENVIRONMENT}** — changes made here are LIVE.",
             icon=":material/warning:")
else:
    st.success(f"Business Central environment: **{coa.ENVIRONMENT}** (sandbox). "
               "Nothing done here affects Production.", icon=":material/science:")

BLANK_LABEL = "(blank)"


def show(v):
    return BLANK_LABEL if v in ("", coa.BLANK, None) else v


def unshow(v):
    return "" if v == BLANK_LABEL else v


# -----------------------------
# READ BUSINESS CENTRAL
# -----------------------------

@st.cache_data(ttl=900, show_spinner=False)
def load_companies():
    return coa.BC().companies()


@st.cache_data(ttl=900, show_spinner=False)
def load_entity(company):
    return coa.read_entity(coa.BC(), company)


top_l, top_r = st.columns([4, 1])
with top_r:
    if st.button("🔄 Refresh from Business Central"):
        st.cache_data.clear()
        st.session_state.pop("plan", None)
        st.rerun()

try:
    companies = load_companies()
except Exception as e:
    st.error(f"Could not reach Business Central: {e}")
    st.stop()

if coa.MASTER_COMPANY not in companies:
    st.error(f"The master entity '{coa.MASTER_COMPANY}' was not found in Business Central.")
    st.stop()

with st.spinner("Reading the chart of accounts of every entity (cached for 15 minutes)..."):
    bar = st.progress(0.0)
    entities = {}
    for i, company in enumerate(companies, start=1):
        try:
            entities[company] = load_entity(company)
        except Exception as e:
            st.warning(f"{company}: could not be read and is left out ({e})")
        bar.progress(i / len(companies))
    bar.empty()

master = entities[coa.MASTER_COMPANY]

# -----------------------------
# 1) ENTITIES
# -----------------------------
st.subheader("1) Entities")

overview = pd.DataFrame([{
    "Entity": c,
    "Accounts": len(e["chart"]),
    "Shares master's chart": f"{coa.same_chart_share(e, master):.0%}",
    "Subcategories set up": len(e["subcats"]),
} for c, e in entities.items()])
default_targets = [c for c, e in entities.items()
                   if coa.same_chart_share(e, master) >= coa.SAME_CHART_THRESHOLD]
different = [c for c in entities if c not in default_targets]

targets = st.multiselect("Create the account(s) in", options=list(entities), default=default_targets)
if different:
    st.caption(f"Unticked by default because they run a different chart "
               f"(less than {coa.SAME_CHART_THRESHOLD:.0%} of the master's account numbers): "
               + ", ".join(different))
with st.expander("Entity overview"):
    st.dataframe(overview, hide_index=True, width="stretch")

# -----------------------------
# 2) ACCOUNTS
# -----------------------------
st.subheader("2) Account(s)")

codes_used = {f: sorted(master["codes_used"].get(f, set())) for f in coa.FIELD_NAMES}
master_dim_codes = sorted(master["dim_values"])
master_options = ["(start blank)"] + [f"{no} — {a['Name']}" for no, a in sorted(master["chart"].items())]


def apply_template():
    """Prefill the form from the chosen master account."""
    choice = st.session_state["template"]
    if choice == "(start blank)":
        acc, dims = coa.clean_account({}), []
        acc.update(Income_Balance="Income Statement", Debit_Credit="Both",
                   Account_Type="Posting", Direct_Posting=True,
                   Consol_Translation_Method="Average Rate (Manual)",
                   Exchange_Rate_Adjustment="No Adjustment", Review_Policy="None")
    else:
        src_no = choice.split(" — ")[0]
        acc, dims = coa.master_template(master, src_no)
        acc["No"] = ""   # a new number is needed; type the same one to roll out an existing account
        acc[coa.POSTING_FROM] = src_no
        st.session_state.pop("posting_note", None)
        # An account only some entities have (e.g. created in the UK first)
        # cannot give the others their posting groups, so a matching account
        # that every entity has is used instead.
        same_chart = {c: entities[c] for c in default_targets}
        lacking = [c for c, e in same_chart.items() if src_no not in e["chart"]]
        if lacking:
            sugg = coa.suggest_posting_reference(master, same_chart, src_no)
            if sugg:
                acc[coa.POSTING_FROM] = sugg
                st.session_state["posting_note"] = (
                    f"{src_no} exists in only {len(same_chart) - len(lacking)} of {len(same_chart)} entities, "
                    f"so the posting groups are taken from **{sugg} {master['chart'][sugg]['Name']}**, which "
                    f"every entity has and which has the same posting setup as {src_no} in Contoso UK. Change it "
                    "in the Posting section if a different account fits better.")
            else:
                st.session_state["posting_note"] = (
                    f"{src_no} exists in only {len(same_chart) - len(lacking)} of {len(same_chart)} entities and "
                    "no account with the same posting setup exists in all of them. Enter a reference account "
                    "in the Posting section, or clear it to use the posting groups below in every entity.")
    for f in coa.FIELD_NAMES:
        kind = coa.FIELD_KIND[f]
        v = acc.get(f)
        st.session_state[f"f_{f}"] = (bool(v) if kind == "bool" else int(v or 0) if kind == "int"
                                      else show(v) if kind in ("choice", "code", "vatprod", "subcategory")
                                      else (v or ""))
    st.session_state["posting_from"] = acc.get(coa.POSTING_FROM, "")
    st.session_state["dims_df"] = pd.DataFrame(
        [{"Dimension_Code": d["Dimension_Code"], "Dimension_Value_Code": d.get("Dimension_Value_Code", ""),
          "Value_Posting": show(d.get("Value_Posting"))} for d in dims],
        columns=coa.DIM_FIELDS)
    # The editor keeps its own edits keyed to the old rows; start it afresh.
    st.session_state.pop("dims_editor", None)


if "template" not in st.session_state:
    st.session_state["template"] = "(start blank)"
    apply_template()

tab_one, tab_many = st.tabs(["One account", "Several accounts (Excel)"])

with tab_one:
    st.selectbox("Start from an existing account in the master (Contoso UK)", master_options,
                 key="template", on_change=apply_template,
                 help="Copies every field and default dimension of that account into the form. "
                      "Then give it a new No. and Name. To roll an existing UK account out to the "
                      "entities that do not have it yet, type that same No.")
    if st.session_state.get("posting_note"):
        st.info(st.session_state["posting_note"], icon=":material/info:")

    groups = []
    for f in coa.FIELDS:
        if f[2] not in groups:
            groups.append(f[2])
    for group in groups:
        with st.expander(group, expanded=group in ("General", "Posting")):
            if group == "Posting":
                st.text_input(
                    "Take the posting groups from each entity's own copy of account",
                    key="posting_from",
                    help="Recommended. Posting groups differ by entity (Gen. Bus. Posting Group is "
                         "UKL in the UK, CLM in Colombia, CHI in China; VAT Prod. Posting Group "
                         "follows the country). With an account No. here, each entity copies "
                         + ", ".join(coa.LABELS[f] for f in coa.POSTING_FIELDS)
                         + " from its own copy of that account. Clear it to use the values below "
                           "in every entity.")
                if st.session_state.get("posting_from"):
                    st.caption("The posting groups below are the master's, shown for reference only. "
                               "Each entity uses its own copy of account "
                               f"{st.session_state['posting_from']}; the dry run lists what each will get.")
            cols = st.columns(3)
            for i, (f, label, _, kind, choices) in enumerate([x for x in coa.FIELDS if x[2] == group]):
                with cols[i % 3]:
                    key = f"f_{f}"
                    locked = f in coa.POSTING_FIELDS and bool(st.session_state.get("posting_from"))
                    if kind == "bool":
                        st.checkbox(label, key=key)
                    elif kind == "int":
                        st.number_input(label, key=key, step=1, min_value=0)
                    elif kind == "choice":
                        opts = [show(c) for c in choices]
                        if st.session_state.get(key) not in opts:
                            st.session_state[key] = opts[0]
                        st.selectbox(label, opts, key=key, disabled=locked)
                    elif kind in ("code", "vatprod", "subcategory"):
                        pool = (sorted(master["vat_prod"]) if kind == "vatprod"
                                else sorted(master["subcats"]) if kind == "subcategory"
                                else codes_used[f])
                        opts = [BLANK_LABEL] + pool
                        if st.session_state.get(key) not in opts:
                            opts.append(st.session_state.get(key))
                        st.selectbox(label, opts, key=key, disabled=locked)
                    else:
                        st.text_input(label, key=key)

    st.markdown("**Default dimensions**")
    dims_df = st.data_editor(
        st.session_state["dims_df"], num_rows="dynamic", width="stretch", key="dims_editor",
        column_config={
            "Dimension_Code": st.column_config.SelectboxColumn("Dimension", options=master_dim_codes, required=True),
            "Dimension_Value_Code": st.column_config.TextColumn("Dimension value (blank = any)"),
            "Value_Posting": st.column_config.SelectboxColumn(
                "Value posting", options=[show(v) for v in coa.VALUE_POSTING]),
        })

    single = {f: unshow(st.session_state.get(f"f_{f}")) if coa.FIELD_KIND[f] not in ("bool", "int")
              else st.session_state.get(f"f_{f}") for f in coa.FIELD_NAMES}
    single[coa.POSTING_FROM] = (st.session_state.get("posting_from") or "").strip()
    single = coa.clean_account(single)
    single_dims = [{"Dimension_Code": r["Dimension_Code"],
                    "Dimension_Value_Code": "" if pd.isna(r["Dimension_Value_Code"]) else str(r["Dimension_Value_Code"]).strip(),
                    "Value_Posting": unshow(r["Value_Posting"]) if not pd.isna(r["Value_Posting"]) else ""}
                   for _, r in dims_df.iterrows() if not pd.isna(r["Dimension_Code"]) and r["Dimension_Code"]]

with tab_many:
    examples, example_dims = [], []
    for no in ("300055", "700121"):
        a, d = coa.master_template(master, no)
        if a:
            a["No"], a["Name"] = "", f"(example, copied from {no}) " + a["Name"]
            a[coa.POSTING_FROM] = no
            examples.append(a)
            example_dims += [{"No": "", **x} for x in d]
    st.download_button("⬇ Download the Excel template", data=coa.template_workbook(examples, example_dims),
                       file_name="G-L Account upload template.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    upload = st.file_uploader("Upload the completed template", type=["xlsx"])
    many, many_dims = [], {}
    if upload is not None:
        many, many_dims, problems = coa.read_workbook(upload)
        for p in problems:
            st.warning(p)
        if many:
            st.success(f"{len(many)} account(s) read from {upload.name}.")
            st.dataframe(pd.DataFrame(many)[["No", "Name", "Income_Balance", "Account_Category",
                                             "Account_Type", "Gen_Posting_Type", "VAT_Prod_Posting_Group"]],
                         hide_index=True, width="stretch")

source = st.radio("Use", ["The account in the form", "The accounts in the uploaded file"],
                  horizontal=True, disabled=not many,
                  index=1 if many else 0)
if source.startswith("The accounts") and many:
    accounts, dims_by_no = many, many_dims
else:
    accounts, dims_by_no = [single], {single["No"]: single_dims}

# The plan is only valid for exactly these inputs. Any change after the dry
# run hides the approve button until the dry run is repeated.
signature = json.dumps([accounts, dims_by_no, sorted(targets)], sort_keys=True, default=str)

# -----------------------------
# 3) DRY RUN
# -----------------------------
st.divider()
st.subheader("3) Dry run")
st.caption("Reads every selected entity and shows what would happen. Writes nothing.")

if st.button("🔍 Run dry run") or st.session_state.pop("auto_dry_run", False):
    missing_no = [a.get("Name") or "(unnamed)" for a in accounts if not a.get("No")]
    if not targets:
        st.error("Pick at least one entity.")
    elif missing_no:
        st.error("Type the account **No.** first. It is left blank on purpose when you start from an "
                 "existing account: type a new number to create a new account, or the same number to "
                 "roll that account out to the entities that do not have it yet. Missing for: "
                 + ", ".join(missing_no))
        st.session_state.pop("plan", None)
    else:
        plan = coa.plan_accounts(accounts, dims_by_no, {c: entities[c] for c in targets})
        st.session_state["plan"] = plan
        st.session_state["plan_signature"] = signature

plan = st.session_state.get("plan")
plan_current = plan is not None and st.session_state.get("plan_signature") == signature

if plan is not None and not plan_current:
    st.info("The account, dimensions or entities changed since the dry run. Run it again.")

if plan_current:
    # The commonest mistake: the posting reference only exists in some entities.
    bad_refs = sorted({r["account"].get(coa.POSTING_FROM) for r in plan
                       if any("for the posting setup" in e for e in r["errors"])})
    for ref in bad_refs:
        sugg = coa.suggest_posting_reference(master, {c: entities[c] for c in targets}, ref)
        msg = (f"The posting groups are set to come from account **{ref}**, which some of these entities "
               "do not have, so they cannot be created there.")
        if sugg and source.startswith("The account in the form"):
            st.warning(msg + f" **{sugg} {master['chart'][sugg]['Name']}** has the same posting setup in "
                       "Contoso UK and exists in every selected entity.", icon=":material/lightbulb:")
            def _use(ref_no=sugg):
                # Runs before the form is drawn on the next pass, which is the
                # only point a widget's value may be changed.
                st.session_state["posting_from"] = ref_no
                st.session_state["auto_dry_run"] = True

            st.button(f"Use {sugg} for the posting groups and run the dry run again", on_click=_use)
        else:
            st.warning(msg + (f" Try {sugg} (same posting setup, in every entity)." if sugg else
                              " Pick a reference account that exists in every selected entity."),
                       icon=":material/lightbulb:")
    s = coa.summarise(plan)
    m1, m2, m3 = st.columns(3)
    m1.metric("Will be created", s["create"])
    m2.metric("Already exist (left alone)", s["exists"])
    m3.metric("Cannot be created", s["error"])
    table = pd.DataFrame([{
        "Entity": r["company"], "No.": r["No"], "Name": r["Name"],
        "Action": {"create": "✅ create", "exists": "⏭ exists, left alone", "error": "⛔ cannot create"}[r["action"]],
        "Posting setup (type / gen bus / gen prod / VAT bus / VAT prod)": r["posting"],
        "Problems": " | ".join(r["errors"]),
        "Warnings": " | ".join(r["warnings"]),
        "Differs from request (existing only)": " | ".join(r["diffs"]),
    } for r in plan])
    st.dataframe(table, hide_index=True, width="stretch")
    buf = io.BytesIO()
    table.to_excel(buf, index=False)
    st.download_button("⬇ Download the dry run", buf.getvalue(), "G-L account dry run.xlsx")

    # -----------------------------
    # 4) APPROVE AND CREATE
    # -----------------------------
    st.divider()
    st.subheader("4) Approve and create")
    if s["create"] == 0:
        st.info("Nothing to create.")
    else:
        if s["error"]:
            st.warning(f"{s['error']} row(s) marked 'cannot create' will be skipped. Fix them and run "
                       "the dry run again to include them.")
        ok = st.checkbox(f"I have reviewed the dry run. Create {s['create']} account(s) in "
                         f"Business Central environment {coa.ENVIRONMENT}.")
        if st.button("✅ Create accounts", disabled=not ok, type="primary"):
            bar = st.progress(0.0)
            log_box = st.empty()
            lines = []

            def progress(i, n, msg):
                bar.progress(i / n)
                lines.append(f"({i}/{n}) {msg}")
                log_box.code("\n".join(lines[-15:]), language=None)

            results = coa.apply_plan(coa.BC(), plan, progress=progress)
            st.session_state.pop("plan", None)
            st.cache_data.clear()   # the charts have changed
            res = pd.DataFrame(results)
            good = ((res["account"] == "created") & (res["verified"] == "OK")).sum()
            if good == len(res):
                st.success(f"All {good} account(s) created and verified.")
            else:
                st.error(f"{good} of {len(res)} created and verified. Check the rows below.")
            st.dataframe(res, hide_index=True, width="stretch")
            buf = io.BytesIO()
            res.to_excel(buf, index=False)
            st.download_button("⬇ Download the results", buf.getvalue(), "G-L account results.xlsx")
            st.caption(f"Every write is also logged to {coa.AUDIT_FILE}.")
