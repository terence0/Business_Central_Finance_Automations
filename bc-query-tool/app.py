import streamlit as st
from datetime import datetime
import pandas as pd
import io

# RUN IN TERMINAL: streamlit run app.py

# Import your existing code
# If your script file is called something like query_tool.py, import from there:
# from query_tool import Query, COMPANY_LIST
#
# If everything is currently in one .py file, rename it to query_tool.py (recommended)
# and then import from it.

from query import Query, COMPANY_LIST  # <-- update this filename if needed

ACCOUNT_OPTIONS = [
    "100070","100080","100090","100100","100101","100102","100103","100104","100105","100106",
    "100107","100108","100109","100110","100111","100112","100113","100114","100115","100116",
    "100117","100118","100121","100122","100123","100124","100125","100126","100190","100200",
    "100201","100202","100203","100204","100205","100206","100210","100211","100212","100213",
    "100215","100220","100221","100290","100300","100301","100302","100303","100310","100320",
    "100321","100390","100400","100410","100415","100420","100430","100440","100450","100460",
    "100490","100500","100501","100502","100510","100520","100521","100590","100800","100810",
    "100820","100830","100840","100890","100895","100900","100910","100920","100930","100990",
    "100995","200001","200100","200101","200102","200103","200104","200105","200106","200107",
    "200108","200109","200110","200190","300001","300010","300050","300055","300060","300100",
    "300101","300102","300103","300104","300105","300106","300107","300108","300109","300110",
    "300111","300112","300113","300114","300115","300116","300117","300118","300119","300120",
    "300190","300200","300210","300220","300230","300240","300290","300300","300301","300302",
    "300303","300304","300305","300306","300307","300308","300309","300310","300311","300312",
    "300313","300314","300315","300316","300317","300318","300319","300340","300350","300351",
    "300352","300353","300354","300355","300356","300357","300358","300390","300400","300401",
    "300490","300500","300501","300502","300503","300504","300505","300506","300507","300508",
    "300509","300510","300511","300512","300513","300514","300515","300516","300590","400100",
    "400110","400120","400190","400200","400210","400220","400230","400240","400290","400400",
    "400401","400402","400403","400404","400405","400406","400407","400408","400409","400410",
    "400411","400412","400413","400414","400415","400416","400417","400490","400500","400501",
    "400502","400503","400504","400505","400506","400507","400508","400509","400510","400511",
    "400512","400513","400514","400515","400516","400517","400518","400519","400590","400600",
    "400601","400602","400603","400604","400605","400606","400690","400700","400710","400720",
    "400730","400790","400800","400810","400890","400990","500100","500110","500120","500130",
    "500140","500150","500160","500170","500190","500790","500800","500810","500820","500830",
    "500890","500990","600001","600010","600020","600100","600101","600102","600110","600111",
    "600120","600121","600130","600131","600190","600200","600201","600202","600210","600211",
    "600220","600221","600290","600300","600301","600302","600390","600400","600410","600420",
    "600490","600990","700010","700100","700101","700102","700103","700109","700110","700111",
    "700112","700113","700114","700115","700119","700120","700121","700122","700129","700130",
    "700131","700132","700133","700134","700135","700136","700137","700138","700139","700150",
    "700151","700152","700153","700154","700155","700156","700157","700158","700159","700200",
    "700201","700290","700295","700400","700401","700402","700403","700404","700405","700406",
    "700407","700408","700409","700410","700411","700412","700413","700414","700415","700501",
    "700502","700503","700504","700505","700506","700507","700508","700509","700510","700516",
    "700517","700518","700519","700520","700521","700522","700523","700524","700525","700564",
    "700601","700602","700603","700604","700605","700606","700607","700608","700609","700610",
    "700611","700612","700613","700614","700615","700616","700617","700618","700619","700620",
    "700621","700622","700623","700624","700625","700626","700627","700628","700629","700630",
    "700631","700632","700633","700634","700635","700636","700637","700638","700639","700640",
    "700641","700642","700643","700650","700651","700652","700653","700654","700701","700711",
    "700712","700713","700801","700802","700803","700804","700805","700806","700807","700808",
    "700809","700810","700811","700812","700901","700902","700980","700990","700995","800010",
    "800020","800030","800100","800101","800102","800109","800110","800111","800112","800113",
    "800114","800115","800116","800117","800119","800120","800121","800122","800123","800125",
    "800126","800127","800128","800129","800130","800132","800133","800134","800135","800136",
    "800137","800138","800139","800140","800141","800142","800149","800150","800151","800161",
    "800162","800171","800172","800173","800174","800175","800176","800177","800179","800190",
    "800200","800201","800202","800203","800204","800205","800206","800207","800208","800209",
    "800210","800211","800212","800213","800214","800215","800216","800217","800218","800219",
    "800220","800221","800222","800223","800224","800225","800226","800227","800228","800229",
    "800230","800290","800300","800310","800320","800410","800490","800500","800501","800590",
    "800595","800600","800610","800620","800710","800790","800990","800995","900010","900100",
    "900101","900190","900200","900201","900202","900290","900300","900301","900390","900400",
    "900401","900490","900500","900510","900520","900530","900531","900540","900590","900600",
    "900610","900620","900690","900990","900995","900998","999999"
]


st.set_page_config(page_title="GL Query Tool", layout="wide")
st.title("📊 General Ledger Query Tool")
from config import bc_env as _bc_env
_bc_env.banner(st)

st.write("Use the inputs below to extract GL entries from Business Central.")

# -----------------------------
# UI INPUTS
# -----------------------------

all_company_keys = list(COMPANY_LIST.keys())

st.subheader("1) Select Company / Companies")
company_selection = st.multiselect(
    "Choose one or more companies",
    options=all_company_keys,
)

select_all = st.checkbox("Select ALL companies")

if select_all:
    company_selection = all_company_keys

st.subheader("2) Select Date Range")
date_from = st.date_input("Start date")
date_to = st.date_input("End date")

st.subheader("3) Select Accounts")

select_all_accounts = st.checkbox("Select ALL accounts")

# Quick filter input
filter_text = st.text_input(
    "Quick filter (type to match accounts)",
    placeholder="e.g. 300 or 7006"
).strip()

# Determine filtered options
if filter_text:
    filtered_account_options = [acc for acc in ACCOUNT_OPTIONS if acc.startswith(filter_text)]
else:
    filtered_account_options = ACCOUNT_OPTIONS

if select_all_accounts:
    selected_accounts = ACCOUNT_OPTIONS
    st.info(f"✅ All accounts selected ({len(selected_accounts)})")
else:
    selected_accounts = st.multiselect(
        "Search and select one or more accounts",
        options=filtered_account_options
    )
    st.caption(f"Showing {len(filtered_account_options)} accounts based on filter.")




# -----------------------------
# VALIDATION HELPERS
# -----------------------------

def validate_accounts_from_dropdown(accounts_list):
    if not accounts_list:
        return None, "Please select at least one account."
    # Optional: numeric validation (in case the list includes non-numeric)
    if not all(str(acc).isdigit() for acc in accounts_list):
        return None, "Account list contains non-numeric values."
    return [str(acc) for acc in accounts_list], None

def validate_inputs(companies, d_from, d_to, accounts_list):
    if not companies:
        return False, "Please select at least one company (or choose ALL)."

    if d_from > d_to:
        return False, "Start date cannot be after end date."

    accounts, err = validate_accounts_from_dropdown(accounts_list)
    if err:
        return False, err

    return True, accounts

def convert_df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Converts a dataframe to Excel bytes in-memory.
    """
    output = io.BytesIO()
    # xlsxwriter is the preferred engine, openpyxl is the fallback. Both are in
    # requirements.txt; the fallback exists so a stripped-down environment still
    # produces a file instead of a ModuleNotFoundError at the download step.
    try:
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
    except (ImportError, ValueError):
        writer = pd.ExcelWriter(output, engine="openpyxl")
    with writer:
        df.to_excel(writer, index=False, sheet_name="GL Results")
    return output.getvalue()


# -----------------------------
# RUN EXTRACTION
# -----------------------------
st.divider()
run_button = st.button("▶ Run Extraction")

if run_button:
    valid, result = validate_inputs(company_selection, date_from, date_to, selected_accounts)

    if not valid:
        st.error(result)
    else:
        accounts_list = result

        st.info("Running extraction... please wait.")

        # Cost centres default to ALL (empty list)
        cost_centres = []

        # Convert dates to strings in expected format
        date_from_str = date_from.strftime("%Y-%m-%d")
        date_to_str = date_to.strftime("%Y-%m-%d")

        query = Query(
            accountNo=accounts_list,
            costCentre=cost_centres,
            dateFrom=date_from_str,
            dateTo=date_to_str
        )

        df_results = query.getGeneralGenDimAndAcclist(selected_company_keys=company_selection)

        st.success(f"✅ Extraction complete. Rows returned: {len(df_results)}")

        if df_results.empty:
            st.warning("No data returned for the selected parameters.")
        else:
            st.subheader("Preview of Results")
            st.dataframe(df_results.head(200))

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Determine output label for filename
        all_keys = list(COMPANY_LIST.keys())
        if set(company_selection) == set(all_keys):
            output_label = "ALL"
        elif len(company_selection) > 1:
            output_label = "MULTI"
        else:
            output_label = company_selection[0]

        file_name = f"{output_label} - {timestamp}.xlsx"

        # Convert to Excel bytes
        excel_bytes = convert_df_to_excel_bytes(df_results)

        st.download_button(
            label="⬇ Download Excel (All Rows)",
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

