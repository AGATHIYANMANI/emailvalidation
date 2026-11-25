from io import BytesIO
from datetime import datetime
from email import policy
from email.parser import BytesParser
from xml.sax.saxutils import escape
import re
import os

import joblib
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from openpyxl import load_workbook

# File-type text extractors
import pypdf
from docx import Document as DocxDocument
from pptx import Presentation as PptxPresentation

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

from excel_database import save_record


# --------------------------------------------------
# FLASK APP CONFIGURATION
# --------------------------------------------------

app = Flask(__name__)

# Maximum uploaded file size: 2 MB
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

ALLOWED_EXTENSIONS = {"txt", "eml", "pdf", "docx", "doc", "pptx", "ppt"}

# Use /tmp for writable storage on serverless platforms (Vercel, etc.)
# Falls back to current directory when running locally.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TMP_DIR = "/tmp" if os.path.isdir("/tmp") else _BASE_DIR

EXCEL_FILE = os.path.join(_TMP_DIR, "spam_detection_records.xlsx")
EXCEL_SHEET = "Email Records"


# --------------------------------------------------
# LOAD TRAINED MACHINE-LEARNING FILES
# --------------------------------------------------

model = joblib.load(os.path.join(_BASE_DIR, "spam_model.pkl"))
vectorizer = joblib.load(os.path.join(_BASE_DIR, "vectorizer.pkl"))
accuracy = joblib.load(os.path.join(_BASE_DIR, "model_accuracy.pkl"))


# --------------------------------------------------
# HELPER: READ TXT AND EML FILES
# --------------------------------------------------

def read_email_file(uploaded_file):
    """
    Read an uploaded file and return (content, filename).
    Supported formats: TXT, EML, PDF, DOCX, DOC, PPTX, PPT.
    """

    filename = secure_filename(uploaded_file.filename or "")

    if not filename or "." not in filename:
        raise ValueError(
            "Please upload a valid file (TXT, EML, PDF, DOCX, DOC, PPTX, PPT)."
        )

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. Allowed: TXT, EML, PDF, DOCX, DOC, PPTX, PPT."
        )

    file_bytes = uploaded_file.read()

    # ---- Plain text ----
    if extension == "txt":
        content = file_bytes.decode("utf-8-sig")

    # ---- Email (EML) ----
    elif extension == "eml":
        message = BytesParser(policy=policy.default).parsebytes(file_bytes)

        body_part = message.get_body(preferencelist=("plain",))
        if body_part is not None:
            content = body_part.get_content()
        else:
            content = ""
            if message.is_multipart():
                for part in message.walk():
                    if (
                        part.get_content_type() == "text/plain"
                        and part.get_content_disposition() != "attachment"
                    ):
                        part_content = part.get_content()
                        if isinstance(part_content, str):
                            content = part_content
                            break
            else:
                part_content = message.get_content()
                if isinstance(part_content, str):
                    content = part_content

    # ---- PDF ----
    elif extension == "pdf":
        reader = pypdf.PdfReader(BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)
        content = "\n".join(pages)

    # ---- Word (DOCX / DOC) ----
    elif extension in {"docx", "doc"}:
        doc = DocxDocument(BytesIO(file_bytes))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        content = "\n".join(paragraphs)

    # ---- PowerPoint (PPTX / PPT) ----
    elif extension in {"pptx", "ppt"}:
        prs = PptxPresentation(BytesIO(file_bytes))
        slide_texts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_texts.append(shape.text)
        content = "\n".join(slide_texts)

    else:
        content = ""

    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "The uploaded file is empty or its text could not be extracted."
        )

    return content.strip(), filename


# --------------------------------------------------
# HELPER: FIND SPAM-ASSOCIATED WORDS
# --------------------------------------------------

def find_suspicious_words(email_text):
    """
    Return up to 10 words in the email that the trained
    Multinomial Naive Bayes model associates more strongly with spam.
    """

    # This method expects a MultinomialNB model with classes 0 and 1.
    if not hasattr(model, "feature_log_prob_"):
        return []

    classes = list(model.classes_)

    if 0 not in classes or 1 not in classes:
        return []

    words = set(re.findall(r"\b[a-zA-Z]+\b", email_text.lower()))
    feature_names = vectorizer.get_feature_names_out()

    spam_index = classes.index(1)
    ham_index = classes.index(0)

    spam_scores = (
        model.feature_log_prob_[spam_index]
        - model.feature_log_prob_[ham_index]
    )

    score_map = dict(zip(feature_names, spam_scores))

    suspicious = [
        word
        for word in words
        if word in score_map and score_map[word] > 0
    ]

    suspicious.sort(
        key=lambda word: score_map[word],
        reverse=True
    )

    return suspicious[:10]


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# PREDICT SPAM OR NOT SPAM
# --------------------------------------------------

@app.route("/predict", methods=["POST"])
def predict():
    try:
        person_name = request.form.get("person_name", "").strip()
        email_address = request.form.get("email_address", "").strip()

        if not person_name or not email_address:
            return jsonify({
                "error": "Please enter your name and email address."
            }), 400

        uploaded_file = request.files.get("email_file")
        file_name = None

        if uploaded_file and uploaded_file.filename:
            email_text, file_name = read_email_file(uploaded_file)
        else:
            email_text = request.form.get("email_text", "").strip()

        if not email_text:
            return jsonify({
                "error": "Please enter email text or upload a file."
            }), 400

        if len(email_text) > 100000:
            return jsonify({
                "error": "Email content is too large. Maximum is 100,000 characters."
            }), 400

        # Convert the email text into numerical features.
        email_vector = vectorizer.transform([email_text])

        # Predict: this project uses 1 = Spam and 0 = Not Spam.
        result = model.predict(email_vector)[0]
        prediction = "Spam" if result == 1 else "Not Spam"

        # Find words associated with spam in the trained model.
        suspicious_words = find_suspicious_words(email_text)

        # Save the record in the Excel workbook.
        record_id = save_record(
            person_name,
            email_address,
            email_text,
            file_name,
            prediction,
            ", ".join(suspicious_words),
            round(float(accuracy) * 100, 2),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        return jsonify({
            "id": record_id,
            "prediction": prediction,
            "suspicious_words": suspicious_words,
            "accuracy": round(float(accuracy) * 100, 2),
            "file_name": file_name
        })

    except (ValueError, UnicodeDecodeError) as error:
        return jsonify({"error": str(error)}), 400

    except Exception:
        app.logger.exception("Prediction failed")
        return jsonify({
            "error": "Something went wrong while analyzing the email. "
                     "Please try again or contact support."
        }), 500


# --------------------------------------------------
# DOWNLOAD PDF REPORT
# --------------------------------------------------

@app.route("/download/<int:record_id>")
def download_report(record_id):
    try:
        # Read the saved record from the Excel workbook.
        workbook = load_workbook(EXCEL_FILE, read_only=True, data_only=True)

        if EXCEL_SHEET not in workbook.sheetnames:
            workbook.close()
            return "Excel worksheet not found.", 404

        worksheet = workbook[EXCEL_SHEET]
        record = None

        for row in worksheet.iter_rows(min_row=2, values_only=True):
            if row and row[0] == record_id:
                record = row
                break

        workbook.close()

        if record is None:
            return "Report not found.", 404

        # Excel columns:
        # 0 ID, 1 Person Name, 2 Email Address, 3 Email Content,
        # 4 File Name, 5 Prediction, 6 Suspicious Words,
        # 7 Model Accuracy, 8 Date and Time.

        person_name = str(record[1] or "")
        email_address = str(record[2] or "")
        email_content = str(record[3] or "")
        file_name = str(record[4] or "Pasted email text")
        prediction = str(record[5] or "")
        suspicious_words = str(record[6] or "No matching words found")
        model_accuracy = record[7]
        created_at = str(record[8] or "")

        try:
            accuracy_text = f"{float(model_accuracy):.2f}%"
        except (TypeError, ValueError):
            accuracy_text = "Not available"

        # Create PDF in memory.
        buffer = BytesIO()

        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=17,
            leading=22,
            spaceAfter=12
        )

        section_style = styles["Heading2"]

        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=13,
            wordWrap="CJK"
        )

        elements = []

        elements.append(Paragraph(
            "SPAM EMAIL DETECTION REPORT",
            title_style
        ))

        elements.append(Spacer(1, 12))

        # Use Paragraph objects so long values wrap inside the table.
        details = [
            [
                Paragraph("<b>Person Name</b>", body_style),
                Paragraph(escape(person_name), body_style)
            ],
            [
                Paragraph("<b>Email Address</b>", body_style),
                Paragraph(escape(email_address), body_style)
            ],
            [
                Paragraph("<b>File Name</b>", body_style),
                Paragraph(escape(file_name), body_style)
            ],
            [
                Paragraph("<b>Prediction</b>", body_style),
                Paragraph(escape(prediction), body_style)
            ],
            [
                Paragraph("<b>Model Test Accuracy</b>", body_style),
                Paragraph(escape(accuracy_text), body_style)
            ],
            [
                Paragraph("<b>Date and Time</b>", body_style),
                Paragraph(escape(created_at), body_style)
            ],
        ]

        details_table = Table(
            details,
            colWidths=[135, 380],
            repeatRows=0
        )

        details_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.lightblue),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        elements.append(details_table)
        elements.append(Spacer(1, 18))

        elements.append(Paragraph(
            "SPAM-ASSOCIATED WORDS",
            section_style
        ))
        elements.append(Paragraph(
            escape(suspicious_words).replace("\n", "<br/>"),
            body_style
        ))

        elements.append(Spacer(1, 18))

        elements.append(Paragraph(
            "ORIGINAL EMAIL CONTENT",
            section_style
        ))

        # Escape HTML characters so email content is displayed as text.
        safe_content = escape(email_content)
        safe_content = safe_content.replace("\r\n", "\n")
        safe_content = safe_content.replace("\r", "\n")
        safe_content = safe_content.replace("\n", "<br/>")

        elements.append(Paragraph(safe_content, body_style))

        elements.append(Spacer(1, 18))

        elements.append(Paragraph(
            "<i>Note: Model test accuracy measures performance on a "
            "separate evaluation dataset. It is not the confidence of "
            "this individual prediction. Spam-associated words are "
            "indicators learned by the model, not proof of malicious "
            "activity.</i>",
            body_style
        ))

        pdf.build(elements)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"email_report_{record_id}.pdf",
            mimetype="application/pdf"
        )

    except FileNotFoundError:
        return "Excel database file was not found. Analyze an email first.", 404

    except Exception:
        app.logger.exception("PDF report generation failed")
        return "Could not generate the PDF report. Please try again.", 500


# --------------------------------------------------
# HANDLE FILES THAT ARE TOO LARGE
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "The uploaded file is too large. Maximum file size is 2 MB."
    }), 413


# --------------------------------------------------
# RUN THE FLASK APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
