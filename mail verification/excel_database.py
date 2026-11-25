
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import os

# Use /tmp on serverless platforms (Vercel); fall back to local directory.
_TMP_DIR = "/tmp" if os.path.isdir("/tmp") else os.path.dirname(os.path.abspath(__file__))
FILE_NAME = os.path.join(_TMP_DIR, "spam_detection_records.xlsx")

HEADERS = [
    "ID",
    "Person Name",
    "Email Address",
    "Email Content",
    "File Name",
    "Prediction",
    "Suspicious Words",
    "Model Accuracy",
    "Date and Time"
]


def create_excel():

    if not os.path.exists(FILE_NAME):

        wb = Workbook()
        ws = wb.active
        ws.title = "Email Records"

        ws.append(HEADERS)

        for cell in ws[1]:
            cell.font = Font(
                bold=True,
                color="FFFFFF"
            )
            cell.fill = PatternFill(
                start_color="1F4E78",
                end_color="1F4E78",
                fill_type="solid"
            )
            cell.alignment = Alignment(
                horizontal="center"
            )

        widths = [10, 20, 30, 50, 25, 18, 35, 18, 25]

        for i, width in enumerate(widths, 1):
            ws.column_dimensions[
                get_column_letter(i)
            ].width = width

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = "A1:I1"

        wb.save(FILE_NAME)


def save_record(
    person_name,
    email_address,
    email_content,
    file_name,
    prediction,
    suspicious_words,
    accuracy,
    date_time
):

    create_excel()

    wb = load_workbook(FILE_NAME)
    ws = wb.active

    record_id = ws.max_row

    ws.append([
        record_id,
        person_name,
        email_address,
        email_content,
        file_name or "Text Input",
        prediction,
        suspicious_words,
        accuracy,
        date_time
    ])

    wb.save(FILE_NAME)

    return record_id
