import requests
import json
import config.token_2 as token_2
from datetime import date, datetime
import calendar
import logging
import pandas as pd
import time
import re

## Configuration
# Production or sandbox comes from BC_ENVIRONMENT_NAME, set by the run files
# (see config/bc_env.py); with it unset, config.json is used as it is.
from config import bc_env
config = bc_env.load_config()

logging.basicConfig(
    filename='./logging/query_tool.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)
logging.info("======================================================================================================")
logging.info("==================================Beginning of Query Tool=============================================")
logging.info(f"Business Central environment: {config['api']['environment_name']}")
logging.info("======================================================================================================")

## Useful links:
BUSINESS_CENTRAL_BASE_URL = f"{config['api']['base_api']}"
headers = {
    'Authorization': f'Bearer {token_2.get_access_token()}',
    'Prefer': 'odata.continue-on-error',
    'Isolation': 'snapshot'
}
COMPANY_LIST = config["company"]

"""
    Some tools:
        isEmpty(jsonFile) returns true if the COMPANY_LIST is not empty, false otherwise
"""
### HELPER FUNCTIONS
def isNotEmpty(jsonFile):
    return len(jsonFile) != 0

def convert_to_odata_filter(account_list):
    """
    Converts a list of account numbers into an OData filter string.

    Args:
        account_list (list): List of account numbers as strings.

    Returns:
        str: OData filter string.
    """
    return " or ".join([f"G_L_Account_No_ eq '{account}'" for account in account_list])

def convert_to_odata_filter_tb(account_list):
    """
    Converts a list of account numbers into an OData filter string for Trial Balance.
    Uses 'No' field instead of 'G_L_Account_No_'.

    Args:
        account_list (list): List of account numbers as strings.

    Returns:
        str: OData filter string.
    """
    return " or ".join([f"No eq '{account}'" for account in account_list])

def search_accounts_in_response(api_response, account_numbers):
    """
    Searches for all occurrences of specific account numbers in the 'G_L_Account_No' field
    within the API response and appends matching objects to a result list.

    Args:
        api_response (dict or list): Parsed JSON data from the API response.
        account_numbers (list of str): The account numbers to search for.

    Returns:
        list: A list of JSON-serializable objects containing matches.
    """
    matches = []

    def recursive_search(data):
        if isinstance(data, dict):
            # Check for the 'G_L_Account_No' field
            if "G_L_Account_No" in data and data["G_L_Account_No"] in account_numbers:
                matches.append(data)
            # Recursively search other fields
            for key, value in data.items():
                recursive_search(value)
        elif isinstance(data, list):
            for item in data:
                recursive_search(item)

    recursive_search(api_response)
    return matches



def prompt_for_companies(company_list_dict):
    """
    Prompts user to select companies by number(s) or ALL.
    Returns a list of company keys (the dict keys from COMPANY_LIST).
    """
    keys = list(company_list_dict.keys())

    while True:
        print("\nAvailable Companies:")
        for idx, key in enumerate(keys, start=1):
            print(f"{idx}. {key}")

        user_input = input("\nSelect company numbers (e.g. 1,2,4) or type ALL: ").strip().upper()

        if user_input == "ALL":
            return keys

        # Validate comma-separated numbers
        selections = [x.strip() for x in user_input.split(",") if x.strip().isdigit()]
        if not selections:
            print("❌ Invalid input. Please enter numbers like 1,2,3 or ALL.")
            continue

        selections = [int(x) for x in selections]
        if any(x < 1 or x > len(keys) for x in selections):
            print("❌ Invalid selection. One or more numbers are out of range.")
            continue

        selected_keys = [keys[i - 1] for i in selections]
        return selected_keys


def prompt_for_date_range():
    """
    Prompts user for a date range in format: YYYY-MM-DD to YYYY-MM-DD
    Returns (date_from, date_to) as strings.
    """
    while True:
        user_input = input("\nEnter date range (YYYY-MM-DD to YYYY-MM-DD): ").strip()

        pattern = r"^\d{4}-\d{2}-\d{2}\s+to\s+\d{4}-\d{2}-\d{2}$"
        if not re.match(pattern, user_input):
            print("❌ Invalid format. Please use: YYYY-MM-DD to YYYY-MM-DD")
            continue

        start_str, end_str = [x.strip() for x in user_input.split("to")]
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_str, "%Y-%m-%d")
        except ValueError:
            print("❌ Invalid dates. Please ensure dates are real and formatted correctly.")
            continue

        if start_date > end_date:
            print("❌ Start date must be before or equal to end date.")
            continue

        return start_str, end_str


def prompt_for_accounts():
    """
    Prompts user to enter comma-separated account numbers.
    Returns a list of account strings.
    """
    while True:
        user_input = input("\nEnter account numbers (comma-separated, numeric only): ").strip()
        if not user_input:
            print("❌ Accounts cannot be empty.")
            continue

        accounts = [x.strip() for x in user_input.split(",") if x.strip()]
        if not accounts:
            print("❌ Accounts cannot be empty.")
            continue

        # Validate numeric-only
        if not all(acc.isdigit() for acc in accounts):
            print("❌ Invalid accounts. Only numeric strings are allowed (e.g. 300301,300302).")
            continue

        return accounts



### QUERY FUNCTIONALITY
class Query:
    def __init__(self, accountNo =[], costCentre =[], dateFrom = '0001-01-01', dateTo = date.today()):
        self.accountList= accountNo
        self.costCentreList = costCentre
        self.dateFrom = dateFrom
        self.dateTo = dateTo
        self.base_url = BUSINESS_CENTRAL_BASE_URL
        logging.info(f"Initialized Query with accounts: {self.accountList}, cost centres: {self.costCentreList}, dateFrom: {self.dateFrom}, dateTo: {self.dateTo}")
        """
            The base url is the url of the business central API, it is used to make requests to the API.
            The COMPANY_LIST is a configuration of the url routing, it is used to make requests to the API.
            The headers are used to authenticate the requests to the API.
        """
    """
        you can use a query class and group types of queries together. I would suggest that you use one field and get a list of that specific field (i.e. list of account numbers), then have an intermediate code filter for the cost centres and dates you need.
        this query class has 4 inputs:
            AccountList = list of account(s), you may query for one account, it will just have to be in a list. Valid input: ['100211'] or ['100211','800102',.......]
            CostCentreList = list of cost centre(s), you may query for multiple cost centres, similar to account list. Valid input: ['OFFTEN'] or ['OFFTEN','NAMOPS',.......]
            DateFrom = start date of the query, default is '01-01-0001'.
            DateTo = end date of the query, default is today's date
        you may customize it such that you add an entity filter, but remember the entity filter affects {COMPANY_LIST[key]}, which is a configuration of the url routing. However, the solution is designed such that the output is already grouped in different entities.
    """
    def getGeneralGenV1(self):
        for key in COMPANY_LIST:
            filtered_data = []
            filter_param = convert_to_odata_filter(self.accountList)
            url = self.base_url + f"{COMPANY_LIST[key]}/General_Ledger_Entries_Excel?$filter=G_L_Account_No eq '{filter_param}'"

            try:
                response = requests.get(url, headers=headers)
                logging.info(f"Requested URL: {url} | Status: {response.status_code}")

                # Define the date range
                start_date = datetime.strptime(self.dateFrom, "%Y-%m-%d")
                end_date = datetime.strptime(str(self.dateTo),"%Y-%m-%d")
                #Filter the data
                if isNotEmpty(response.json()['value']):
                    logging.info(f"Found {len(response.json()['value'])} entries in {key}")
                    for item in response.json()['value']:
                        if "Posting_Date" in item and start_date <= datetime.strptime(item["Posting_Date"], "%Y-%m-%d") <= end_date:
                            filtered_data.append(item)

                with open(f'./GL Query/JSON/{key}.json', 'w') as output_doc:
                    json.dump(filtered_data, output_doc, indent=4)
            except requests.exceptions.RequestException as e:
                logging.error(f"Error occurred: {e}")
                return f"Error occurred: {e}"
            logging.info(f"Written filtered data to ./GL Query/JSON/{key}.json")

    def getGeneralGenV2(self):
        for key in COMPANY_LIST:
            url = self.base_url + f"{COMPANY_LIST[key]}/General_Ledger_Entries_Excel"
            try:
                response = requests.get(url, headers=headers)
                logging.info(f"Requested URL: {url} | Status: {response.status_code}")

                # Check if the response is successful
                if response.status_code != 200:
                    logging.error(f"Error: {response.status_code} - {response.text}")
                    return f"Error: {response.status_code} - {response.text}"

                # Define the date range
                start_date = datetime.strptime(self.dateFrom, "%Y-%m-%d")
                end_date = datetime.strptime(str(self.dateTo),"%Y-%m-%d")
                modified_response = search_accounts_in_response(response.json(), self.accountList)
                #Filter the data
                filtered_data = []
                if isNotEmpty(modified_response):
                    logging.info(f"Found {len(modified_response)} matching entries in {key}")
                    for item in modified_response:
                        if "Posting_Date" in item and start_date <= datetime.strptime(item["Posting_Date"], "%Y-%m-%d") <= end_date:
                            filtered_data.append(item)

                with open(f'./GL Query/JSON/{key}.json', 'w') as output_doc:
                    json.dump(filtered_data, output_doc, indent=4)
                logging.info(f"Written filtered data to ./GL Query/JSON/{key}.json")

            except requests.exceptions.RequestException as e:
                logging.error(f"Error occurred: {e}")
                return f"Error occurred: {e}"

    def getGeneralGenV3(self):
        for key in COMPANY_LIST:
            url = self.base_url + f"{COMPANY_LIST[key]}/General_Ledger_Entries_Excel$select="
            try:
                response = requests.get(url, headers=headers, verify=False)
                logging.info(f"Requested URL: {url} | Status: {response.status_code}")
                if response.status_code != 200:
                    logging.error(f"Error: {response.status_code} - {response.text}")
                    return f"Error: {response.status_code} - {response.text}"

                # Define the date range
                start_date = datetime.strptime(self.dateFrom, "%Y-%m-%d")
                end_date = datetime.strptime(str(self.dateTo),"%Y-%m-%d")
                modified_response = search_accounts_in_response(response.json(), self.accountList)
                #Filter the data
                filtered_data = []
                if isNotEmpty(modified_response):
                    logging.info(f"Found {len(modified_response)} matching entries in {key}")
                    for item in modified_response:
                        if "Posting_Date" in item and start_date <= datetime.strptime(item["Posting_Date"], "%Y-%m-%d") <= end_date:
                            filtered_data.append(item)

                with open(f'./GL Query/JSON/{key}.json', 'w') as output_doc:
                    json.dump(filtered_data, output_doc, indent=4)
                logging.info(f"Written filtered data to ./GL Query/JSON/{key}.json")
            except requests.exceptions.RequestException as e:
                logging.error(f"Error occurred: {e}")
                return f"Error occurred: {e}"

    def getGeneralGenDim(self):
        for key in COMPANY_LIST:
            url = self.base_url + f"{COMPANY_LIST[key]}/General_Ledger_Entries_Excel"
            try:
                response = requests.get(url, headers=headers, verify=False)
                logging.info(f"Requested URL: {url} | Status: {response.status_code}")
                if response.status_code != 200:
                    logging.error(f"Error: {response.status_code} - {response.text}")
                    return f"Error: {response.status_code} - {response.text}"

                # Define the date range
                start_date = datetime.strptime(self.dateFrom, "%Y-%m-%d")
                end_date = datetime.strptime(str(self.dateTo),"%Y-%m-%d")
                #Filter the data
                filtered_data = [
                    item for item in response.json()["value"]
                    if "Posting_Date" in item and start_date <= datetime.strptime(item["Posting_Date"], "%Y-%m-%d") <= end_date
                ]
                with open(f'./GL Query/JSON/{key}_{date.today()}.json', 'w') as output_doc:
                    json.dump(json.dumps(filtered_data, indent=4), output_doc, indent=4)
                logging.info(f"Written filtered data to ./GL Query/JSON/{key}_{date.today()}.json")
            except requests.exceptions.RequestException as e:
                logging.error(f"Error occurred: {e}")
                return f"Error occurred: {e}"

    def getGeneralGenDimAndAcclist(self, selected_company_keys=None):

        if selected_company_keys is None:
            selected_company_keys = list(COMPANY_LIST.keys())

        combined_results = []

        for key in selected_company_keys:
            url = self.base_url + f"{COMPANY_LIST[key]}/General_Ledger_Entries_with_Dimensions?$filter={convert_to_odata_filter(self.accountList)}"

            try:
                response = requests.get(url, headers=headers, verify=False)
                logging.info(f"Requested URL: {url} | Status: {response.status_code}")

                if response.status_code != 200:
                    logging.error(f"Error: {response.status_code} - {response.text}")
                    continue  # move to next company

                # Define the date range
                start_date = datetime.strptime(self.dateFrom, "%Y-%m-%d")
                end_date = datetime.strptime(str(self.dateTo), "%Y-%m-%d")

                # Filter by date
                filtered_byDate = [
                    item for item in response.json()["value"]
                    if "Posting_Date" in item and start_date <= datetime.strptime(item["Posting_Date"], "%Y-%m-%d") <= end_date
                ]
                logging.info(f"Filtered {len(filtered_byDate)} entries by date for {key}")

                # Filter by cost centre (optional)
                if len(self.costCentreList) != 0:
                    filtered_data = [
                        item for item in filtered_byDate
                        if "Global_Dimension_1_Code" in item and item["Global_Dimension_1_Code"] in self.costCentreList
                    ]
                    logging.info(f"Filtered {len(filtered_data)} entries by cost centre for {key}")
                else:
                    filtered_data = filtered_byDate
                    logging.info(f"No cost centre filter applied for {key}, using all {len(filtered_data)} entries")

                # Add Company column to each record
                for row in filtered_data:
                    row["Company"] = key

                combined_results.extend(filtered_data)

            except requests.exceptions.RequestException as e:
                logging.error(f"RequestException in getGeneralGenDimAndAcclist() for {key}: {e}")
            except Exception as e:
                logging.error(f"Error in getGeneralGenDimAndAcclist() for {key}: {e}")

        # Return as DataFrame (even if empty)
        df = pd.DataFrame(combined_results)
        return df

    @staticmethod
    def _get_month_end_dates(date_from_str, date_to_str):
        """
        Generate a list of month-end dates for every month touched by the date range.
        A month is included if any part of it overlaps with [date_from, date_to].

        For example: '2025-01-15' to '2025-06-20' returns:
            ['2025-01-31', '2025-02-28', '2025-03-31', '2025-04-30', '2025-05-31', '2025-06-30']

        Args:
            date_from_str: Start date string 'YYYY-MM-DD'
            date_to_str:   End date string 'YYYY-MM-DD'

        Returns:
            List of month-end date strings in 'YYYY-MM-DD' format.
        """
        start = datetime.strptime(date_from_str, "%Y-%m-%d")
        end = datetime.strptime(date_to_str, "%Y-%m-%d")

        month_ends = []
        year, month = start.year, start.month
        end_year, end_month = end.year, end.month

        while (year < end_year) or (year == end_year and month <= end_month):
            last_day = calendar.monthrange(year, month)[1]
            month_end = datetime(year, month, last_day)
            month_ends.append(month_end.strftime("%Y-%m-%d"))
            # Move to next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

        return month_ends

    def getTrialBalance(self, selected_company_keys=None, progress_callback=None):
        """
        Queries the ExcelTemplateTrialBalance web service for each selected company,
        at each month-end date within self.dateFrom to self.dateTo.

        Each month-end snapshot is tagged with a 'Period' column (e.g. '2025-01-31').
        Account filtering is done client-side.
        Returns a combined DataFrame across all companies and all month-ends.

        Args:
            selected_company_keys: List of company keys to query. Defaults to all.
            progress_callback: Optional callable(current_step, total_steps, message)
                               for reporting progress (e.g. Streamlit progress bar).
        """
        if selected_company_keys is None:
            selected_company_keys = list(COMPANY_LIST.keys())

        # Generate month-end dates from the date range
        month_ends = self._get_month_end_dates(str(self.dateFrom), str(self.dateTo))
        if not month_ends:
            logging.warning("[TB] No complete months in the selected date range.")
            return pd.DataFrame()

        logging.info(f"[TB] Will query {len(month_ends)} month-end(s): {month_ends}")

        combined_results = []
        total_steps = len(month_ends) * len(selected_company_keys)
        current_step = 0

        for period_date in month_ends:
            for key in selected_company_keys:
                current_step += 1
                if progress_callback:
                    progress_callback(current_step, total_steps, f"{key} — {period_date}")

                url = self.base_url + f"{COMPANY_LIST[key]}/ExcelTemplateTrialBalance"
                params = {'$filter': f"dateFilter eq {period_date}"}

                try:
                    response = requests.get(url, headers=headers, params=params, verify=False)
                    logging.info(f"[TB] {period_date} | {key} | URL: {response.url} | Status: {response.status_code}")

                    if response.status_code != 200:
                        logging.error(f"[TB] Error: {response.status_code} - {response.text}")
                        continue

                    data = response.json().get("value", [])
                    logging.info(f"[TB] {period_date} | {key} | Retrieved {len(data)} records")

                    # Log first record's keys for debugging (shows available columns)
                    if data:
                        logging.info(f"[TB] {period_date} | {key} | Columns: {list(data[0].keys())}")
                    else:
                        logging.warning(f"[TB] {period_date} | {key} | API returned 0 records")

                    # Tag each row with Period and Company
                    for row in data:
                        row["Period"] = period_date
                        row["Company"] = key

                    combined_results.extend(data)

                except requests.exceptions.RequestException as e:
                    logging.error(f"[TB] RequestException for {key} at {period_date}: {e}")
                except Exception as e:
                    logging.error(f"[TB] Error for {key} at {period_date}: {e}")

        df = pd.DataFrame(combined_results)
        return df

    # Fields pulled for the VAT Return & Recon report. Kept identical, field
    # for field and in order, to VAT_SELECT_WANTED in the VAT Return Extract
    # that feeds the central VAT automation (the central extract's query.py),
    # so the Data sheet of a pack built here matches one built there.
    VAT_SELECT_FIELDS = [
        "Entry_No", "Posting_Date", "Document_Type", "Document_No",
        "G_L_Account_No", "G_L_Account_Name", "Description",
        "Gen_Posting_Type", "Gen_Bus_Posting_Group", "Gen_Prod_Posting_Group",
        "VAT_Bus_Posting_Group", "VAT_Prod_Posting_Group",
        "Amount", "VAT_Amount", "NonDeductibleVATAmount",
        "Bal_Account_Type", "Bal_Account_No",
        # Source_No_PLANFUL is what the pack's GL Account sheet is keyed on.
        "Source_No_PLANFUL",
        "CustomerName", "VendorName", "CurrencyCode", "VAT_Reporting_Date",
        "External_Document_No", "Global_Dimension_1_Code",
        "Global_Dimension_2_Code", "Source_Code", "User_ID",
    ]

    # The pack cannot be built without these, so they are never dropped from
    # $select. Anything else Business Central says it does not have is.
    VAT_REQUIRED_FIELDS = {"Entry_No", "Posting_Date", "G_L_Account_No",
                           "Gen_Posting_Type", "VAT_Prod_Posting_Group",
                           "Amount", "VAT_Amount"}

    def getVATLedgerEntries(self, selected_company_keys=None, progress_callback=None):
        """
        Extracts General_Ledger_Entries_Excel for each selected company, with
        Posting_Date filtered *server-side* via OData $filter.

        This is the important difference from getGeneralGenDim/getGeneralGenV2/
        getGeneralGenDimAndAcclist above (and from the Power BI model this
        replaces): those all pull the full, unfiltered history for a company
        and then discard out-of-range rows in Python/DAX afterwards. Confirmed
        via a live test against Business Central that Posting_Date does fold
        into a real server-side filter (fewer rows come back, less time spent),
        so filtering here first is what actually fixes the slow-refresh problem
        rather than working around it after the fact.

        Handles @odata.nextLink pagination. Returns a combined DataFrame
        across all selected companies, tagged with a 'Company' column.
        """
        if selected_company_keys is None:
            selected_company_keys = list(COMPANY_LIST.keys())

        wanted = list(self.VAT_SELECT_FIELDS)
        date_filter = f"Posting_Date ge {self.dateFrom} and Posting_Date le {self.dateTo}"

        combined_results = []
        total = len(selected_company_keys)

        for i, key in enumerate(selected_company_keys, start=1):
            if progress_callback:
                progress_callback(i, total, key)

            url = self.base_url + f"{COMPANY_LIST[key]}/General_Ledger_Entries_Excel"
            params = {"$filter": date_filter, "$select": ",".join(wanted)}
            page = 0
            company_rows = 0

            while url:
                try:
                    response = requests.get(url, headers=headers, params=params, verify=False)
                    logging.info(f"[VAT] {key} | page {page} | URL: {response.url} | Status: {response.status_code}")

                    # An optional field this service does not expose: drop it
                    # and ask again, as the the central VAT automation extract only selects
                    # what the service reports.
                    unknown = re.search(r"Could not find a property named '([^']+)'",
                                        response.text) if response.status_code == 400 else None
                    if (unknown and page == 0 and unknown.group(1) in wanted
                            and unknown.group(1) not in self.VAT_REQUIRED_FIELDS):
                        logging.warning(f"[VAT] {key} | service has no {unknown.group(1)}, "
                                        "dropped from $select")
                        wanted.remove(unknown.group(1))
                        params = {"$filter": date_filter, "$select": ",".join(wanted)}
                        continue

                    # Raised rather than skipped: carrying on would publish a
                    # short pack for this company that looks complete.
                    if response.status_code != 200:
                        logging.error(f"[VAT] Error for {key}: {response.status_code} - {response.text}")
                        raise RuntimeError(
                            f"Business Central refused {key} (HTTP {response.status_code}) "
                            f"on page {page}. Nothing was published. {response.text[:300]}")

                    body = response.json()
                    data = body.get("value", [])
                    for row in data:
                        row["Company"] = key
                    combined_results.extend(data)
                    company_rows += len(data)

                    # nextLink already carries the full query string, so no
                    # params on subsequent requests.
                    url = body.get("@odata.nextLink")
                    params = None
                    page += 1

                except requests.exceptions.RequestException as e:
                    logging.error(f"[VAT] RequestException for {key}: {e}")
                    raise RuntimeError(
                        f"Could not reach Business Central for {key} on page {page}: {e}. "
                        "Nothing was published.") from e

            logging.info(f"[VAT] {key} | total rows: {company_rows}")

        df = pd.DataFrame(combined_results)
        return df


    # =====================================================================
    #  CUSTOMER AGEING  (Notes 21 and 22, debtors ageing and ECL)
    # =====================================================================
    #
    #  Two things about this extract are not obvious. Both were decided on
    #  evidence from the FY25 pack, so please read before changing either.
    #
    #  1. BUCKETS ARE CALENDAR MONTHS ON POSTING DATE, NOT DAY BANDS.
    #     The note labels its columns "0 - 30 days" and so on, but the FY25
    #     figures came from Business Central's Aged Accounts Receivable report
    #     run with monthly periods: 01/08..31/08, 01/07..31/07, 01/06..30/06,
    #     01/05..31/05, Before 01/05. 33 of the 40 FY25 files were aged by
    #     posting date (one, USA 700151, by due date; six were not the report
    #     at all). FY26 reproduces the FY25 basis deliberately so the
    #     comparative holds. Due-date day bands are still computed, into
    #     Bucket_DueDate_Days, so the size of the difference is visible and the
    #     basis can be switched later without another extract.
    #
    #  2. THE BALANCE IS ROLLED BACK, NOT SUMMED FORWARD.
    #     BC's Remaining Amount is the balance TODAY. An invoice open at
    #     31 August but settled in September reads nil now, so a year-end
    #     ageing taken straight off Remaining Amount understates every bucket,
    #     and understates it more the later it is run. The audit re-runs this
    #     months afterwards.
    #
    #     Rather than rebuild each balance by summing all detailed entries from
    #     inception (hundreds of thousands of rows), it is rolled back:
    #
    #         balance at cut-off = Remaining Amount today
    #                            - detailed entries posted AFTER the cut-off
    #
    #     Algebraically identical, and the second term covers only the days
    #     since the year end instead of all history. A few hundred rows.
    #
    #  Service names are discovered at run time. BC web service names are set
    #  per tenant and were not documented anywhere, so each candidate is tried
    #  in order against one probe company and the first that answers 200 is
    #  used. The chosen names come back on the DataFrame's .attrs.

    CUST_LEDGER_SERVICES = [
        "Customer_Ledger_Entries_Excel",     # page 25, matches the *_Excel pattern
        "CustomerLedgerEntries",             # query object
        "Cust_Ledger_Entries_Excel",
        "Customer_Ledger_Entries",
        "customerLedgerEntries",
    ]

    DETAILED_CUST_SERVICES = [
        "Detailed_Cust__Ledg__Entries_Excel",   # page 29
        "DetailedCustLedgEntries",
        "Detailed_Cust_Ledg_Entries_Excel",
        "Detailed_Customer_Ledger_Entries_Excel",
    ]

    CUST_POSTING_GROUP_SERVICES = [
        "Customer_Posting_Groups",
        "CustomerPostingGroups",
        "Customer_Posting_Groups_Excel",
    ]

    # Canonical name -> the spellings BC might return it as. Page services use
    # Underscore_Case, query objects use camelCase.
    CLE_FIELDS = {
        "Entry_No":            ("Entry_No", "entryNo", "Entry_No_"),
        "Customer_No":         ("Customer_No", "customerNo", "Customer_No_"),
        "Customer_Name":       ("Customer_Name", "customerName", "Name", "Description"),
        "Customer_Posting_Group": ("Customer_Posting_Group", "customerPostingGroup"),
        "Posting_Date":        ("Posting_Date", "postingDate"),
        "Document_Date":       ("Document_Date", "documentDate"),
        "Due_Date":            ("Due_Date", "dueDate"),
        "Document_Type":       ("Document_Type", "documentType"),
        "Document_No":         ("Document_No", "documentNo", "Document_No_"),
        "Currency_Code":       ("Currency_Code", "currencyCode"),
        "Open":                ("Open", "open"),
        "Closed_at_Date":      ("Closed_at_Date", "closedAtDate"),
        "Remaining_Amount":    ("Remaining_Amount", "remainingAmount"),
        "Remaining_Amt_LCY":   ("Remaining_Amt_LCY", "Remaining_Amt__LCY_", "remainingAmountLCY"),
        "Amount":              ("Amount", "amount"),
        "Amount_LCY":          ("Amount_LCY", "Amount__LCY_", "amountLCY"),
        "Global_Dimension_1_Code": ("Global_Dimension_1_Code", "globalDimension1Code"),
        "Global_Dimension_2_Code": ("Global_Dimension_2_Code", "globalDimension2Code"),
    }

    DCLE_FIELDS = {
        "Cust_Ledger_Entry_No": ("Cust__Ledger_Entry_No_", "Cust_Ledger_Entry_No",
                                 "custLedgerEntryNo", "Cust_Ledger_Entry_No_"),
        "Posting_Date":         ("Posting_Date", "postingDate"),
        "Entry_Type":           ("Entry_Type", "entryType"),
        "Amount":               ("Amount", "amount"),
        "Amount_LCY":           ("Amount_LCY", "Amount__LCY_", "amountLCY"),
    }

    # Detailed entry types that do not change what the customer owes and do not
    # feed Remaining Amt. (LCY), so they must not be rolled back either.
    NON_BALANCE_ENTRY_TYPES = {"Unrealized Loss", "Unrealized Gain"}

    # $select, so the payload is the 17 fields the note needs and not the 100+
    # on the Cust. Ledger Entry table. The VAT extract does the same thing and
    # for the same reason: without it the pull is an order of magnitude larger
    # and slow enough to look broken.
    # Canonical names. The actual spelling sent to Business Central is resolved
    # at run time from the fields the service reports, through CLE_FIELDS and
    # DCLE_FIELDS, because the spellings differ per service and per tenant.
    CLE_SELECT_WANTED = ["Entry_No", "Customer_No", "Customer_Name",
                         "Customer_Posting_Group", "Posting_Date",
                         "Document_Date", "Due_Date", "Document_Type",
                         "Document_No", "Currency_Code", "Open",
                         "Closed_at_Date", "Remaining_Amount",
                         "Remaining_Amt_LCY", "Amount", "Amount_LCY",
                         "Global_Dimension_1_Code", "Global_Dimension_2_Code"]
    DCLE_SELECT_WANTED = ["Cust_Ledger_Entry_No", "Posting_Date", "Entry_Type",
                          "Amount", "Amount_LCY"]

    BUCKET_NAMES = ["0 - 30 days", "30 - 60 days", "60 - 90 days",
                    "90 - 120 days", "120+ days"]

    @staticmethod
    def _pick(row, aliases, default=None):
        """First alias present in the row, else default. BC field spellings
        differ between page services and query objects."""
        for a in aliases:
            if a in row:
                return row[a]
        return default

    # Companies tried first when learning a service's field names. A company
    # with no rows teaches nothing, and the alphabetically first ones
    # (Adjustments, Argentina) are usually empty.
    PROBE_ORDER = ["Contoso UK", "Contoso Switzerland", "Contoso USA", "Contoso Brazil",
                   "Contoso Singapore", "Contoso Japan"]

    def _discover_service(self, candidates, company_keys, tag):
        """Return (service_name, field_names).

        The service is the first candidate answering 200. The field names come
        from the first company that actually returns a row: an empty company
        teaches nothing, and without real field names the $select is guesswork,
        which is what produced
        "Could not find a property named 'Cust__Ledger_Entry_No_'".
        """
        order = ([k for k in self.PROBE_ORDER if k in company_keys]
                 + [k for k in company_keys if k not in self.PROBE_ORDER])
        service = None
        for candidate in candidates:
            for key in order[:1]:
                url = self.base_url + f"{COMPANY_LIST[key]}/{candidate}"
                try:
                    r = requests.get(url, headers=headers, params={"$top": "1"},
                                     verify=False, timeout=90)
                except requests.exceptions.RequestException as e:
                    logging.warning(f"[AGE] {tag} probe {candidate}: {e}")
                    continue
                if r.status_code == 200:
                    service = candidate
                    break
                logging.info(f"[AGE] {tag} probe {candidate}: HTTP {r.status_code}")
            if service:
                break
        if service is None:
            logging.error(f"[AGE] {tag}: none of {candidates} is published")
            return None, []

        for key in order[:8]:
            url = self.base_url + f"{COMPANY_LIST[key]}/{service}"
            try:
                r = requests.get(url, headers=headers, params={"$top": "1"},
                                 verify=False, timeout=90)
            except requests.exceptions.RequestException:
                continue
            if r.status_code != 200:
                continue
            try:
                sample = r.json().get("value", [])
            except ValueError:
                sample = []
            if sample:
                keys = list(sample[0].keys())
                logging.info(f"[AGE] {tag} resolved: {service} | "
                             f"{len(keys)} fields learned from {key}")
                return service, keys
        logging.warning(f"[AGE] {tag} resolved: {service}, but no company "
                        "returned a row, so $select will be omitted")
        return service, []

    @staticmethod
    def _select_for(field_map, wanted, available):
        """Build a $select from the field names the service actually exposes.

        Returns None when nothing was learned, in which case no $select is sent
        and the full row comes back. Slower, but it always works, which beats a
        guessed field name that fails the whole call.
        """
        if not available:
            return None
        have = set(available)
        picked = []
        for canon in wanted:
            for alias in field_map.get(canon, (canon,)):
                if alias in have:
                    picked.append(alias)
                    break
        return ",".join(picked) if picked else None

    def _fetch_all(self, company, service, params, tag, key):
        """GET with @odata.nextLink pagination.

        Returns (rows, ok, error_text). `ok` is False only when the request
        itself failed.
        An empty list with ok=True means the filter legitimately matched
        nothing, which is the normal answer for a company with no open items.
        Conflating the two is what made an earlier version fall back to pulling
        the entire ledger since inception.
        """
        url = self.base_url + f"{company}/{service}"
        rows, page = [], 0
        while url:
            try:
                response = requests.get(url, headers=headers, params=params,
                                        verify=False, timeout=300)
            except requests.exceptions.RequestException as e:
                logging.error(f"[AGE] {tag} {key} page {page}: {e}")
                return rows, False, f"{type(e).__name__}: {e}"
            if response.status_code != 200:
                text = response.text[:400]
                logging.error(f"[AGE] {tag} {key}: HTTP {response.status_code} - {text}")
                return rows, False, f"HTTP {response.status_code}: {text}"
            body = response.json()
            rows.extend(body.get("value", []))
            url = body.get("@odata.nextLink")   # already carries the query string
            params = None
            page += 1
        logging.info(f"[AGE] {tag} {key}: {len(rows)} rows over {page} page(s)")
        return rows, True, None

    def getCustomerPostingGroups(self, selected_company_keys=None):
        """Customer Posting Group -> receivables G/L account, per company.

        This is what turns a ledger entry into an account number, and it is why
        the report does not have to be run once per posting group the way the
        FY25 pack was. Twelve rows for Contoso UK.
        """
        if selected_company_keys is None:
            selected_company_keys = list(COMPANY_LIST.keys())

        service, _ = self._discover_service(
            self.CUST_POSTING_GROUP_SERVICES, selected_company_keys, "postinggroups")
        if service is None:
            return pd.DataFrame()

        out = []
        for key in selected_company_keys:
            rows, _ok, _err = self._fetch_all(COMPANY_LIST[key], service, None, "PG", key)
            for row in rows:
                out.append({
                    "Company": key,
                    "Customer_Posting_Group": self._pick(row, ("Code", "code")),
                    "Description": self._pick(row, ("Description", "description")),
                    "Receivables_Account": self._pick(
                        row, ("Receivables_Account", "receivablesAccount",
                              "Receivables_Account_No")),
                })
        df = pd.DataFrame(out)
        df.attrs["service"] = service
        return df

    # Output levels. "summary" is the default because the disclosure only ever
    # needs company x account x bucket: 5 buckets across ~13 companies and 7
    # accounts is a few hundred rows at most. Entry level exists for the day
    # TB Check shows a break and you need the invoices behind it.
    GRANULARITIES = ("summary", "customer", "detail")

    SUMMARY_KEYS = ["Company", "As_At", "Basis", "Customer_Posting_Group",
                    "Receivables_Account", "Bucket"]
    CUSTOMER_KEYS = SUMMARY_KEYS + ["Customer_No", "Customer_Name",
                                    "Currency_Code"]

    def _summarise(self, df, keys):
        """Aggregate the entry-level frame onto `keys`. Nothing is dropped:
        every balance still lands in exactly one bucket."""
        agg = (df.groupby(keys, dropna=False)
                 .agg(Balance_LCY=("Balance_LCY", "sum"),
                      Balance_Currency=("Balance_Currency", "sum"),
                      Entries=("Entry_No", "count"),
                      Oldest_Posting_Date=("Posting_Date", "min"),
                      Newest_Posting_Date=("Posting_Date", "max"))
                 .reset_index())
        return agg.sort_values(keys).reset_index(drop=True)

    def getCustomerAging(self, selected_company_keys=None, progress_callback=None,
                         granularity="summary"):
        """Customer ageing at self.dateTo.

        granularity:
          "summary"  one row per company, posting group, account and bucket.
                     The default. This is all the disclosure needs.
          "customer" the same, split by customer.
          "detail"   one row per ledger entry open at the cut-off.

        See the block comment above for the two design points."""
        if granularity not in self.GRANULARITIES:
            raise ValueError(f"granularity must be one of {self.GRANULARITIES}")
        if selected_company_keys is None:
            selected_company_keys = list(COMPANY_LIST.keys())

        as_at = str(self.dateTo)[:10]
        cut = pd.Timestamp(as_at)

        cle_service, cle_keys = self._discover_service(
            self.CUST_LEDGER_SERVICES, selected_company_keys, "custledger")
        if cle_service is None:
            raise RuntimeError(
                "No customer ledger web service is published in Business Central. "
                f"Tried: {', '.join(self.CUST_LEDGER_SERVICES)}. "
                "Ask whoever administers BC to publish page 25 (Customer Ledger "
                "Entries) as a web service, then run this again. Until then the "
                "summary route is the fallback: run report 120 Aged Accounts "
                "Receivable per company per posting group and paste into the "
                "Summary Input tab of the ageing workbook.")

        dcle_service, dcle_keys = self._discover_service(
            self.DETAILED_CUST_SERVICES, selected_company_keys, "detailed")
        rollback = dcle_service is not None
        basis = ("Calendar month on posting date; balance rolled back to cut-off"
                 if rollback else
                 "Calendar month on posting date; BALANCE NOT ROLLED BACK "
                 "(Remaining Amount as at today)")
        if not rollback:
            logging.warning("[AGE] Detailed service unavailable. Remaining Amount is "
                            f"the balance today, not at {as_at}.")

        cle_select = self._select_for(self.CLE_FIELDS, self.CLE_SELECT_WANTED,
                                      cle_keys)
        dcle_select = self._select_for(self.DCLE_FIELDS, self.DCLE_SELECT_WANTED,
                                       dcle_keys)
        logging.info(f"[AGE] $select CLE: {cle_select}")
        logging.info(f"[AGE] $select DCLE: {dcle_select}")

        combined = []
        total = len(selected_company_keys)

        for i, key in enumerate(selected_company_keys, start=1):
            if progress_callback:
                progress_callback(i, total, key)
            company = COMPANY_LIST[key]

            # --- ledger entry headers, open at the cut-off ----------------
            # Two narrow pulls, unioned. Business Central answers
            #   501 BadRequest_MethodNotImplemented
            #   "The 'OR' operator is not supported on distinct fields"
            # to `Open eq true or Closed_at_Date gt <date>`, so the OR is done
            # here. Both halves are still filtered server-side: there is
            # deliberately no "pull it all and sift in pandas" path, because at
            # a year end that is the whole ledger since inception.
            params_open = {"$filter": f"Posting_Date le {as_at} and Open eq true"}
            params_closed = {"$filter": f"Posting_Date le {as_at} and "
                                        f"Closed_at_Date gt {as_at}"}
            if cle_select:
                params_open["$select"] = cle_select
                params_closed["$select"] = cle_select

            a, ok_a, err_a = self._fetch_all(company, cle_service, params_open,
                                             "CLE-open", key)
            b, ok_b, err_b = self._fetch_all(company, cle_service, params_closed,
                                             "CLE-closedafter", key)
            if not (ok_a and ok_b):
                raise RuntimeError(
                    f"Business Central refused the open-entry read for {key} on "
                    f"service {cle_service}. Nothing was pulled; the tool will "
                    f"not fall back to reading the whole ledger.\n\n"
                    f"{err_a or err_b}")

            seen, cle_rows = set(), []
            for row in a + b:
                num = self._pick(row, self.CLE_FIELDS["Entry_No"])
                if num in seen:
                    continue
                seen.add(num)
                cle_rows.append(row)
            if not cle_rows:
                continue

            cle = pd.DataFrame([
                {canon: self._pick(row, aliases)
                 for canon, aliases in self.CLE_FIELDS.items()}
                for row in cle_rows])
            cle["Company"] = key

            # format="mixed" because BC returns ISO dates but writes the null
            # date as 0001-01-01, which trips pandas' format inference.
            for c in ("Posting_Date", "Due_Date", "Closed_at_Date", "Document_Date"):
                cle[c] = pd.to_datetime(cle[c], errors="coerce", format="mixed")

            cle = cle[cle["Posting_Date"] <= cut]
            open_at_cut = (cle["Open"].astype(str).str.lower().isin(["true", "1", "yes"])
                           | (cle["Closed_at_Date"] > cut))
            cle = cle[open_at_cut]
            if cle.empty:
                continue

            cle["Balance_Currency"] = pd.to_numeric(
                cle["Remaining_Amount"], errors="coerce").fillna(0)
            cle["Balance_LCY"] = pd.to_numeric(
                cle["Remaining_Amt_LCY"], errors="coerce").fillna(0)

            # --- roll the balance back to the cut-off ---------------------
            if rollback:
                dp = {"$filter": f"Posting_Date gt {as_at}"}
                if dcle_select:
                    dp["$select"] = dcle_select
                after, ok_d, err_d = self._fetch_all(
                    company, dcle_service, dp, "DCLE-after", key)
                if not ok_d and dcle_select:
                    # A $select naming a field this service does not expose
                    # fails the whole call. Drop it and take the full row.
                    logging.warning(f"[AGE] {key}: detailed $select refused, "
                                    "retrying without it")
                    dcle_select = None
                    after, ok_d, err_d = self._fetch_all(
                        company, dcle_service,
                        {"$filter": f"Posting_Date gt {as_at}"},
                        "DCLE-after-noselect", key)
                if not ok_d:
                    raise RuntimeError(
                        f"Could not read the post cut-off detailed entries for "
                        f"{key} on service {dcle_service}. Without them the "
                        "balance cannot be rolled back to the cut-off and every "
                        f"bucket would be understated.\n\n{err_d}")
                if after:
                    d = pd.DataFrame([
                        {canon: self._pick(r, aliases)
                         for canon, aliases in self.DCLE_FIELDS.items()}
                        for r in after])
                    d = d[~d["Entry_Type"].astype(str).isin(self.NON_BALANCE_ENTRY_TYPES)]
                    for c in ("Amount", "Amount_LCY"):
                        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
                    agg = (d.groupby("Cust_Ledger_Entry_No")[["Amount", "Amount_LCY"]]
                             .sum().reset_index())
                    agg.columns = ["Entry_No", "After_Currency", "After_LCY"]
                    cle = cle.merge(agg, on="Entry_No", how="left")
                    cle[["After_Currency", "After_LCY"]] = (
                        cle[["After_Currency", "After_LCY"]].fillna(0))
                else:
                    cle["After_Currency"] = 0.0
                    cle["After_LCY"] = 0.0
                cle["Balance_Currency"] = cle["Balance_Currency"] - cle["After_Currency"]
                cle["Balance_LCY"] = cle["Balance_LCY"] - cle["After_LCY"]
            else:
                cle["After_Currency"] = 0.0
                cle["After_LCY"] = 0.0

            cle = cle[(cle["Balance_LCY"] != 0) | (cle["Balance_Currency"] != 0)]
            if cle.empty:
                continue

            # --- ageing ---------------------------------------------------
            cle["Months_Back"] = ((cut.year - cle["Posting_Date"].dt.year) * 12
                                  + (cut.month - cle["Posting_Date"].dt.month))
            cle["Bucket"] = cle["Months_Back"].apply(self._bucket_calendar)
            cle["Days_Past_Due"] = (cut - cle["Due_Date"]).dt.days
            cle["Not_Yet_Due"] = cle["Days_Past_Due"] < 0
            cle["Bucket_DueDate_Days"] = cle["Days_Past_Due"].apply(self._bucket_days)
            cle["As_At"] = as_at
            cle["Basis"] = basis
            combined.append(cle)

        if not combined:
            df = pd.DataFrame()
            df.attrs["services"] = {"customer_ledger": cle_service,
                                    "detailed": dcle_service}
            df.attrs["basis"] = basis
            df.attrs["granularity"] = granularity
            df.attrs["detail_rows"] = 0
            return df

        df = pd.concat(combined, ignore_index=True)

        # --- receivables account per row ---------------------------------
        pg = self.getCustomerPostingGroups(selected_company_keys)
        if not pg.empty:
            df = df.merge(pg[["Company", "Customer_Posting_Group",
                              "Receivables_Account"]],
                          on=["Company", "Customer_Posting_Group"], how="left")
        else:
            df["Receivables_Account"] = None

        order = ["Company", "As_At", "Basis", "Entry_No", "Customer_No",
                 "Customer_Name", "Customer_Posting_Group", "Receivables_Account",
                 "Document_Type", "Document_No", "Posting_Date", "Document_Date",
                 "Due_Date", "Months_Back", "Bucket",
                 "Days_Past_Due", "Not_Yet_Due", "Bucket_DueDate_Days",
                 "Currency_Code", "Balance_Currency", "Balance_LCY",
                 "After_Currency", "After_LCY",
                 "Open", "Closed_at_Date",
                 "Global_Dimension_1_Code", "Global_Dimension_2_Code"]
        detail = df[[c for c in order if c in df.columns]]
        detail_rows = len(detail)

        # The due-date view, summarised, so changing basis later needs no
        # second extract even when only the summary is kept.
        due_keys = [k if k != "Bucket" else "Bucket_DueDate_Days"
                    for k in self.SUMMARY_KEYS]
        due_summary = self._summarise(detail, due_keys)

        if granularity == "detail":
            out = detail
        elif granularity == "customer":
            out = self._summarise(detail, self.CUSTOMER_KEYS)
        else:
            out = self._summarise(detail, self.SUMMARY_KEYS)

        out.attrs["services"] = {"customer_ledger": cle_service,
                                 "detailed": dcle_service}
        out.attrs["basis"] = basis
        out.attrs["granularity"] = granularity
        out.attrs["detail_rows"] = detail_rows
        out.attrs["due_summary"] = due_summary
        out.attrs["moved_rows"] = int(
            (detail["Bucket"] != detail["Bucket_DueDate_Days"]).sum())
        logging.info(f"[AGE] {detail_rows} entries -> {len(out)} rows "
                     f"at granularity '{granularity}' | basis: {basis}")
        return out

    @staticmethod
    def _bucket_calendar(months_back):
        """Calendar-month buckets, matching the FY25 Aged Accounts Receivable
        runs. months_back 0 is the cut-off month itself."""
        if pd.isna(months_back):
            return "0 - 30 days"
        m = int(months_back)
        if m <= 0:
            return "0 - 30 days"
        if m >= 4:
            return "120+ days"
        return Query.BUCKET_NAMES[m]

    @staticmethod
    def _bucket_days(days):
        """Due-date day bands. Diagnostic only: nothing in the note uses this
        yet. Kept so the basis can be changed without another extract."""
        if pd.isna(days):
            return "0 - 30 days"
        if days <= 30:
            return "0 - 30 days"
        if days <= 60:
            return "30 - 60 days"
        if days <= 90:
            return "60 - 90 days"
        if days <= 120:
            return "90 - 120 days"
        return "120+ days"


def generate_output_label(selected_companies, all_companies):

        if set(selected_companies) == set(all_companies):
            return "ALL"
        elif len(selected_companies) > 1:
            return "MULTI"
        else:
            return selected_companies[0]



if __name__ == "__main__":
    start_time = time.time()

    # Prompt user inputs
    selected_companies = prompt_for_companies(COMPANY_LIST)
    date_from, date_to = prompt_for_date_range()
    list_of_accounts = prompt_for_accounts()

    # Default cost centres to ALL (no filtering)
    cost_centres = []

    # Create query object and run for selected companies
    query1 = Query(
        accountNo=list_of_accounts,
        costCentre=cost_centres,
        dateFrom=date_from,
        dateTo=date_to
    )

    df_results = query1.getGeneralGenDimAndAcclist(selected_company_keys=selected_companies)

    print(f"\n✅ Extraction complete. Rows returned: {len(df_results)}")

        # Create timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determine output label
    output_label = generate_output_label(selected_companies, list(COMPANY_LIST.keys()))

    # Output paths
    excel_output_path = f"./GL Query/Excel/{output_label} - {timestamp}.xlsx"
    json_output_path = f"./GL Query/JSON/{output_label} - {timestamp}.json"

    # Save combined outputs
    if not df_results.empty:
        df_results.to_excel(excel_output_path, index=False)
        logging.info(f"Combined Excel written to {excel_output_path}")
        print(f"✅ Excel saved to: {excel_output_path}")

        # Also save JSON if you want combined JSON output
        df_results.to_json(json_output_path, orient="records", indent=4)
        logging.info(f"Combined JSON written to {json_output_path}")
        print(f"✅ JSON saved to: {json_output_path}")
    else:
        logging.info("No results returned — nothing written to Excel/JSON.")
        print("⚠️ No results returned — no output files created.")


    end_time = time.time()
    elapsed = end_time - start_time
    logging.info(f"Query execution time: {elapsed:.2f} seconds")
    logging.info("======================================================================================================")
    logging.info("====================================End of Query Tool=================================================")
    logging.info("======================================================================================================")
