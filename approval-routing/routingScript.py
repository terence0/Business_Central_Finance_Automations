import getpass
import os
import sys
import pandas as pd
import test
import logging
import traceback
from datetime import datetime

from notifier import send_notification_email, build_diff_table_html

RUN_BY = getpass.getuser()

# Setup logging - mirror everything to the console as well as the log file,
# so a run kicked off via the .bat file shows live status instead of a blank window.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("./logging/routingScript.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)

try:
    logging.info("Reading input CSV and Excel files...")

    # Read the CSV file into a DataFrame
    df = pd.read_csv('./Archieves/Yooz CC Import_v4.csv', sep=";")
    df = df.fillna("")

    logging.info("Filtering dataframes for each gateway...")

    review_df = df[df['Gateway'] == 'Review.Review']
    review2_df = df[df['Gateway'] == 'Review.Review 2']
    budgetHolderConstants_df = df[(df['Gateway'] == 'Approve.Budget Holder Approval') & (df['Rank']<=3)]
    limitApporverConstants_df = df[(df['Gateway'] == 'Approve.Limit Approver ') & (df['Rank'] <= 44)]
    headOffice_df = df[df['Gateway'] == 'Approve.Head Office Approval']
    approvePayment_df = df[df['Gateway'] == 'Approve payment.Approve Payment']

    #Creation of import file
    entityCodes = ["ARG","BRU","CAN","CAP","CHI","CLM","DUB","HK1","HLD","JPN","MEL","MEX","MUM","NOR","SAO","SG1","UKL","USA","ZUR"]
    entityNames = ["Contoso Argentina", "Contoso Belgium","Contoso Canada","Contoso South Africa","Contoso China","Contoso Colombia","Contoso Dubai","Contoso Hong Kong","Contoso Holdings","Contoso Japan","Contoso Australia","Contoso Mexico","Contoso India","Contoso Norway", "Contoso Servicos Brasil LTDA","Contoso Singapore", "Contoso UK","Contoso USA","Contoso Switzerland"]
    gateway = ["Review.Review","Review.Review 2","Approve.Budget Holder Approval","Approve.Limit Approver ","Approve.Head Office Approval", "Approve payment.Approve Payment"]

    logging.info("Reading Excel sheets for vendor and cost centre routing...")

    #Read an Excel file into a DataFrame
    sheet2 = pd.read_excel('Vendor & Cost Centre Routing.xlsx', sheet_name='Vendor')
    sheet1 = pd.read_excel('Vendor & Cost Centre Routing.xlsx', sheet_name='Cost center')
    overridesSheet = pd.read_excel(
        'Vendor & Cost Centre Routing.xlsx',
        sheet_name='Cost Centre Overrides',
        usecols=["Cost Centre", "Entity", "Budget Holder Approval", "Limit Approver"],
    )

    sheet1 = sheet1.fillna("")
    sheet2 = sheet2.fillna("")
    overridesSheet = overridesSheet.fillna("")

    cost_centres = sheet1["Cost Centre"].tolist()
    budget_holder = sheet1["Budget Holder Approval"].tolist()
    limit_holder = sheet1["Limit Approver"].tolist()
    vendors = sheet2["Vendor"].tolist()
    vendors_Names = sheet2["Vendor Name"].tolist()
    budget_holder_vendors = sheet2["Budget Holder Approval"].tolist()
    limit_holder_vendors = sheet2["Limit Approver"].tolist()

    # Entity-specific cost centre overrides: same Cost Centre, different approvers per Entity.
    # Only rows with both a Cost Centre and a recognised Entity code are used; everything else
    # keeps falling back to the default approver from the "Cost center" sheet above.
    logging.info("Building entity-specific cost centre override lookup...")
    cc_overrides = {}
    for _, row in overridesSheet.iterrows():
        cc = str(row["Cost Centre"]).strip()
        entity = str(row["Entity"]).strip()
        if not cc or not entity:
            continue
        if entity not in entityCodes:
            logging.warning(f"Cost Centre Overrides: unrecognised Entity code '{entity}' for Cost Centre '{cc}' - row ignored.")
            continue
        key = (cc, entity)
        if key in cc_overrides:
            logging.warning(f"Cost Centre Overrides: duplicate entry for Cost Centre '{cc}' / Entity '{entity}' - using the last one.")
        cc_overrides[key] = (
            str(row["Budget Holder Approval"]).strip(),
            str(row["Limit Approver"]).strip(),
        )
    logging.info(f"Loaded {len(cc_overrides)} entity-specific cost centre override(s).")

    #Budget Holder Approval dataFrame
    columns = ["Gateway","Rank","Default","Route","Condition 1","Criteria 1","Value 1","Condition 2","Criteria 2","Value 2","Condition 3","Criteria 3","Value 3","Condition 4","Criteria 4","Value 4","Condition 5","Criteria 5","Value 5","Next process object","PotentialOwners","Backward route process","Ignoring manual recipients"]
    dataBH = []
    countBH = 1

    logging.info("Building Budget Holder Approval dataframe...")

    for a in range(len(vendors)):
        if budget_holder_vendors[a] == "":
            break
        vendor_data = []
        vendor_data.append(gateway[2])
        vendor_data.append(countBH)
        countBH+=1
        vendor_data.append("")
        vendor_data.append(str(vendors_Names[a]) + " Invoices")
        vendor_data.append("YZ_COMMONS.YZ_THIRD.YZ_REFERENTIAL_DATA_COMMONS.YZ_CODE")
        vendor_data.append("EQUALS")
        vendor_data.append(vendors[a])
        for b in range(12):
            vendor_data.append("")
        vendor_data.append("USER_TASK.Budget Holder Approval")
        vendor_data.append("USER:"+str(budget_holder_vendors[a]).strip())
        vendor_data.append("")
        vendor_data.append("")
        dataBH.append(vendor_data)

    for i in range(len(entityCodes)):
        for j in range(len(cost_centres)):
            inner_data=[]
            inner_data.append(gateway[2])
            inner_data.append(countBH)
            countBH+=1
            inner_data.append("")
            inner_data.append(cost_centres[j] + "-" + entityCodes[i])
            inner_data.append("YZ_COMMONS.YZ_ORGANIZATIONAL_UNIT")
            inner_data.append("EQUALS")
            if entityCodes[i] == "SAO":
                inner_data.append(entityNames[i])
                inner_data.append("YZ_DIMENSION." + entityNames[i] + ".COST CENTRE.YZ_DIMENSION_DATA_COMMONS.YZ_CODE")
            else:
                inner_data.append(entityNames[i] + " (" + entityCodes[i]+ ")")
                inner_data.append("YZ_DIMENSION." + entityNames[i] + " (" + entityCodes[i]+ ").COST CENTRE.YZ_DIMENSION_DATA_COMMONS.YZ_CODE")
            inner_data.append("EQUALS")
            inner_data.append(cost_centres[j])
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("USER_TASK.Budget Holder Approval")
            override = cc_overrides.get((str(cost_centres[j]).strip(), entityCodes[i]))
            bh_value = override[0] if override else str(budget_holder[j]).strip()
            if "," in bh_value:
                inner_data.append("USER:" + bh_value.split(",")[0].strip() + "," + "USER:" + bh_value.split(",")[1].strip())
            else:
                inner_data.append("USER:"+bh_value.strip())
            inner_data.append("")
            inner_data.append("")
            dataBH.append(inner_data)
    dataBH.append(["Approve.Budget Holder Approval",len(entityCodes)*len(cost_centres)+4,"1","(Default)","","","","","","","","","","","","","","","","EXCLUSIVE_GATEWAY.Review","GROUP:AC","-12000",""])
    dfNewBH = pd.DataFrame(dataBH, columns=columns)

    logging.info("Budget Holder Approval dataframe complete.")

    # Limit holder approval
    dataLH = []
    countLH = 45

    logging.info("Building Limit Holder Approval dataframe...")

    for a in range(len(vendors)):
        if limit_holder_vendors[a] == "":
            break
        vendor_data = []
        vendor_data.append(gateway[3])
        vendor_data.append(countLH)
        countLH+=1
        vendor_data.append("")
        vendor_data.append(str(vendors_Names[a]) + " Invoices")
        vendor_data.append("YZ_COMMONS.YZ_THIRD.YZ_REFERENTIAL_DATA_COMMONS.YZ_CODE")
        vendor_data.append("EQUALS")
        vendor_data.append(vendors[a])
        for b in range(12):
            vendor_data.append("")
        vendor_data.append("USER_TASK.Limit Approver ")
        vendor_data.append("USER:"+ str(limit_holder_vendors[a]).strip())
        vendor_data.append("")
        vendor_data.append("")
        dataLH.append(vendor_data)

    for i in range(len(entityCodes)):
        for j in range(len(cost_centres)):
            inner_data=[]
            inner_data.append(gateway[3])
            inner_data.append(countLH)
            countLH+=1
            inner_data.append("")
            inner_data.append(cost_centres[j] + "-" + entityCodes[i])
            inner_data.append("YZ_COMMONS.YZ_ORGANIZATIONAL_UNIT")
            inner_data.append("EQUALS")
            if entityCodes[i] == "SAO":
                inner_data.append(entityNames[i])
                inner_data.append("YZ_DIMENSION." + entityNames[i] + ".COST CENTRE.YZ_DIMENSION_DATA_COMMONS.YZ_CODE")
            else:
                inner_data.append(entityNames[i] + " (" + entityCodes[i]+ ")")
                inner_data.append("YZ_DIMENSION." + entityNames[i] + " (" + entityCodes[i]+ ").COST CENTRE.YZ_DIMENSION_DATA_COMMONS.YZ_CODE")
            inner_data.append("EQUALS")
            inner_data.append(cost_centres[j])
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("")
            inner_data.append("USER_TASK.Limit Approver ")
            override = cc_overrides.get((str(cost_centres[j]).strip(), entityCodes[i]))
            lh_value = override[1] if override else str(limit_holder[j]).strip()
            if "," in lh_value:
                inner_data.append("USER:" + lh_value.split(",")[0].strip() + "," + "USER:" + lh_value.split(",")[1].strip())
            else:
                inner_data.append("USER:"+lh_value)
            inner_data.append("")
            inner_data.append("")
            dataLH.append(inner_data)
    dataLH.append(["Approve.Limit Approver ",countLH,"1","(Default)","","","","","","","","","","","","","","","","USER_TASK.Limit Approver ","GROUP:AC","-12000",""])
    dfNewLH = pd.DataFrame(dataLH, columns=columns)

    logging.info("Limit Holder Approval dataframe complete.")

    logging.info("Concatenating all dataframes...")

    result = pd.concat([review_df, review2_df, dfNewBH, limitApporverConstants_df, dfNewLH, headOffice_df,approvePayment_df], axis=0, ignore_index=True)

    logging.info("Exporting to CSV: ./Generated Import/Generated_Import.csv")

    result.to_csv('./Generated Import/Generated_Import.csv', sep=";", index=False)

    logging.info("Comparing generated CSV against baseline - this step is slow and can take several minutes, please keep this window open...")
    similarity_result, removed_rows, added_rows = test.compare('./Generated Import/Generated_Import.csv')
    logging.info(f"Comparing generated CSV with test expectations: {similarity_result}")

    logging.info("Script completed successfully. Sending notification email...")

    diff_columns = [c for c in removed_rows.columns if c != "Source"]
    diff_table_html = build_diff_table_html(diff_columns, removed_rows, added_rows)

    html_body = f"""
    <html><body style="font-family:Segoe UI, Arial, sans-serif;font-size:13px;">
    <p>routingScript.py completed successfully at {datetime.now():%Y-%m-%d %H:%M:%S}.</p>
    <p><b>Run by:</b> {RUN_BY}</p>
    <p><b>{similarity_result}</b></p>
    <p>Changes vs baseline (red = removed, green = added/changed):</p>
    {diff_table_html}
    <p>Full generated import file and differences.csv are attached.</p>
    </body></html>
    """

    send_notification_email(
        subject="Yooz Routing Automation - Success",
        html_body=html_body,
        attachments=[
            os.path.abspath('./Generated Import/Generated_Import.csv'),
            os.path.abspath('./Differences/differences.csv'),
        ],
    )
    logging.info("Notification email sent. All done.")

except Exception as e:
    logging.error("Script failed: %s", e, exc_info=True)
    logging.info("Sending failure notification email...")
    send_notification_email(
        subject="Yooz Routing Automation - FAILURE",
        body=(
            f"routingScript.py failed at {datetime.now():%Y-%m-%d %H:%M:%S}.\n\n"
            f"Run by: {RUN_BY}\n\n"
            f"Error: {e}\n\n"
            f"{traceback.format_exc()}"
        ),
    )
    raise
