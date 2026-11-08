import html
import time

import pywintypes
import win32com.client as win32

RECIPIENTS = ["finance.automation@example.com", "finance.team@example.com"]

MAX_DIFF_ROWS = 50

OUTLOOK_DISPATCH_RETRIES = 3
OUTLOOK_DISPATCH_RETRY_DELAY_SECONDS = 10


def _dispatch_outlook():
    """Dispatch Outlook.Application, retrying on transient COM errors.

    Outlook's COM server can briefly refuse connections while it is still
    starting up (e.g. right after login), raising com_error instead of
    just being slow. Retrying with a short delay avoids treating that as
    a script failure.
    """
    last_error = None
    for attempt in range(1, OUTLOOK_DISPATCH_RETRIES + 1):
        try:
            return win32.Dispatch("Outlook.Application")
        except pywintypes.com_error as e:
            last_error = e
            if attempt < OUTLOOK_DISPATCH_RETRIES:
                time.sleep(OUTLOOK_DISPATCH_RETRY_DELAY_SECONDS)
    raise last_error


def send_notification_email(subject, body=None, html_body=None, to_recipients=RECIPIENTS, attachments=None):
    outlook = _dispatch_outlook()
    mail = outlook.CreateItem(0)
    mail.To = ";".join(to_recipients)
    mail.Subject = subject
    if html_body is not None:
        mail.HTMLBody = html_body
    elif body is not None:
        mail.Body = body
    for path in attachments or []:
        mail.Attachments.Add(path)
    mail.Send()


def _row_cells(row, columns):
    return "".join(
        f"<td style='padding:4px 8px;border:1px solid #ccc;white-space:nowrap;'>{html.escape(str(row[col]))}</td>"
        for col in columns
    )


def build_diff_table_html(columns, removed_rows, added_rows, max_rows=MAX_DIFF_ROWS):
    """Build an HTML table highlighting rows removed from the baseline (red)
    and rows added/changed in the newly generated import (green)."""
    header = "".join(f"<th style='padding:4px 8px;border:1px solid #999;background:#f0f0f0;'>{html.escape(col)}</th>" for col in columns)
    header += "<th style='padding:4px 8px;border:1px solid #999;background:#f0f0f0;'>Change</th>"

    body_rows = ""
    for _, row in removed_rows.head(max_rows).iterrows():
        body_rows += f"<tr style='background-color:#fbdcdc;'>{_row_cells(row, columns)}<td style='padding:4px 8px;border:1px solid #ccc;'>Removed</td></tr>"
    for _, row in added_rows.head(max_rows).iterrows():
        body_rows += f"<tr style='background-color:#d9f2d9;'>{_row_cells(row, columns)}<td style='padding:4px 8px;border:1px solid #ccc;'>Added</td></tr>"

    truncated_note = ""
    total_shown = min(len(removed_rows), max_rows) + min(len(added_rows), max_rows)
    total_rows = len(removed_rows) + len(added_rows)
    if total_rows > total_shown:
        truncated_note = (
            f"<p style='color:#666;font-size:12px;'>Showing {total_shown} of {total_rows} changed rows. "
            "See the attached differences.csv for the full list.</p>"
        )

    table = (
        "<table style='border-collapse:collapse;font-family:Segoe UI, Arial, sans-serif;font-size:12px;'>"
        f"<tr>{header}</tr>{body_rows}</table>"
    )
    return table + truncated_note
