# streamlit_real_pdf_extraction.py
import re
import streamlit as st
import pandas as pd
import pdfplumber
from collections import OrderedDict

st.set_page_config(page_title="Stackmind Insurance", layout="wide")
st.title("🏠 Stackmind Insurance - Property Module ")

# -------------------------------
# Helper: normalize text
# -------------------------------
def norm(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()

# -------------------------------
# Known fields and label variants
# -------------------------------
FIELD_LABELS = OrderedDict([
    ("Property Address", [r"Property Address", r"Property\s*Address[:\s]", r"Property Address[:]?", r"Property Address\s*[:\-]?", r"Address:"]),
    ("Total Units", [r"Total Units", r"Total\s+Units[:\s]", r"Units[:]"]),
    ("Property Type", [r"Property Type", r"Property\s+Type[:\s]"]),
    ("Building Type", [r"Building Type", r"Building\s+Type[:\s]"]),
    ("Building Age", [r"Building Age", r"Building\s+Age[:\s]"]),
    ("Number of Stories", [r"Number of Stories", r"Number of Stories[:\s]", r"Stories[:]"]),
    ("Sale Amount", [r"Sale Amount", r"Sale Amount[:\s]", r"Sale[:\s]"]),
    ("Municipal Evaluation", [r"Municipal Evaluation", r"Municipal\s+Evaluation[:\s]"]),
    ("Building Size", [r"Building Size", r"Building\s+Size[:\s]"]),
    ("Land Size", [r"Land Size", r"Land\s+Size[:\s]"]),
    ("Foundation Type", [r"Foundation Type", r"Foundation\s+Type[:\s]"]),
    ("Exterior Material", [r"Exterior Material", r"Exterior\s+Material[:\s]"]),
    ("Heating System", [r"Heating System", r"Heating[:\s]"]),
    ("Windows", [r"Windows", r"Windows[:]"]),
    ("Roofing", [r"Roofing", r"Roofing[:]"]),
    ("Electrical", [r"Electrical", r"Electrical[:]"]),
    ("Plumbing", [r"Plumbing", r"Plumbing[:]"]),
    ("Sewer Service", [r"Sewer Service", r"Sewer\s+Service[:]"]),
    ("Fire Incidents", [r"Fire Incidents", r"Fire\s+Incidents[:]"]),
    ("Windows Age", [r"Windows Age", r"Windows\s+Age[:]"]),
    ("Plumbing Age", [r"Plumbing Age", r"Plumbing\s+Age[:]"]),
    ("Water Tank Age", [r"Water Tank Age", r"Water\s+Tank\s+Age[:]"]),
    ("Sewer Source", [r"Sewer Source", r"Sewer\s+Source[:]"]),
    ("Document Type", [r"Document Type", r"Document\s+Type[:]"]),
    ("Report Date", [r"Report Date", r"Report\s+Date[:]"]),
])

# -------------------------------
# Extract simple labeled fields from text
# -------------------------------
def extract_by_labels(text):
    results = {}
    for field, patterns in FIELD_LABELS.items():
        found = ""
        for p in patterns:
            # search label then capture rest of line
            regex = re.compile(rf"{p}\s*[:\-]?\s*(.+)", re.IGNORECASE)
            m = regex.search(text)
            if m:
                found = norm(m.group(1))
                # stop at first match
                break
        results[field] = found
    return results

# -------------------------------
# Fallback generic searches (currency, address-like)
# -------------------------------
def fallback_search(text, current):
    # If address blank, try find line with numbers + street keywords or postal code
    if not current.get("Property Address"):
        # Look for typical Canadian postal code or lines containing numbers + street words
        m = re.search(r"([0-9]{1,5}\s+[A-Za-z0-9\-\.\s]{5,100},?\s*[A-Za-z]{2,}\s*\d[A-Z]\s*\d[A-Z]\d?)", text)
        if m:
            current["Property Address"] = norm(m.group(1))
        else:
            # lines with Rue, Street, Ave, Boulevard, Rd, Road, Way
            m2 = re.search(r"([0-9]{1,5}\s+[\w\s\.\-]{3,80}\s+(Street|St|Avenue|Ave|Boulevard|Blvd|Rue|Road|Rd|Way|Terrière|Terrier|Terri[èe]re)[^\n\r]*)", text, re.IGNORECASE)
            if m2:
                current["Property Address"] = norm(m2.group(1))
    # currency like $299,000
    if not current.get("Sale Amount"):
        m = re.search(r"(\$\s?\d{1,3}(?:[,\d{3}]+)?)", text)
        if m:
            current["Sale Amount"] = norm(m.group(1))
    return current

# -------------------------------
# Try extract from pdfplumber tables too
# -------------------------------
def extract_from_tables(pdf):
    extracted = {}
    for page in pdf.pages:
        try:
            tables = page.extract_tables()
        except Exception:
            tables = None
        if tables:
            for tab in tables:
                # convert simple table to dataframe-like and scan rows for label/value
                for row in tab:
                    # row may be list; join cell text
                    row_text = " | ".join([str(c).strip() if c is not None else "" for c in row])
                    for field in FIELD_LABELS:
                        # match if row starts with field name or contains it
                        if re.search(rf"^{re.escape(field)}[:\s]", row_text, re.IGNORECASE) or re.search(rf"{re.escape(field)}", row_text, re.IGNORECASE):
                            # try to get value from row cells (last non-empty cell)
                            nonempties = [c for c in row if c not in (None, "")]
                            if len(nonempties) >= 2:
                                extracted[field] = norm(nonempties[-1])
    return extracted

# -------------------------------
# Parse one PDF file: text + tables
# -------------------------------
def parse_pdf_file(file_obj):
    # file_obj: file-like (uploaded file)
    full_text = []
    table_extracted = {}
    try:
        with pdfplumber.open(file_obj) as pdf:
            # extract tables first
            try:
                table_extracted = extract_from_tables(pdf)
            except Exception:
                table_extracted = {}
            # extract whole text
            for page in pdf.pages:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                full_text.append(text)
    except Exception as e:
        raise e

    text_all = "\n".join(full_text)
    text_all = norm(text_all)

    # first try labeled extraction
    label_results = extract_by_labels(text_all)

    # merge table_extracted (prefer table value if present)
    for k, v in table_extracted.items():
        if v:
            label_results[k] = v

    # fallback search for missing important fields
    label_results = fallback_search(text_all, label_results)

    return label_results, text_all

# -------------------------------
# UI: Session init
# -------------------------------
if "properties" not in st.session_state:
    st.session_state["properties"] = {}

uploaded_files = st.file_uploader(
    "📂 Upload Insurance Documents (PDF)",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    with st.spinner("🔍 Parsing PDFs..."):
        for file in uploaded_files:
            try:
                parsed_fields, raw_text = parse_pdf_file(file)

                # choose unique key for dedupe: Property Address if present, else filename+hash
                address = parsed_fields.get("Property Address") or ""
                key = None
                if address:
                    # check if already exists (address match)
                    for pid, pdata in st.session_state["properties"].items():
                        if pdata.get("Property Address") and pdata.get("Property Address").lower() == address.lower():
                            key = pid
                            break
                if not key:
                    # create new id
                    key = f"Property_{len(st.session_state['properties'])+1:03}"

                # Ensure we keep a fixed list of fields (but real values)
                record = OrderedDict()
                for field in FIELD_LABELS.keys():
                    record[field] = parsed_fields.get(field, "")

                # additional meta
                record["Source File"] = getattr(file, "name", "uploaded.pdf")
                # raw text (optional, can be large) - store small preview
                record["Raw Text Preview"] = (raw_text[:1000] + "...") if raw_text else ""

                # Save or update
                st.session_state["properties"][key] = record

                st.success(f"✅ Parsed and saved: {key} ({record.get('Property Address','No Address')})")

            except Exception as e:
                st.error(f"❌ Error parsing {getattr(file,'name', 'file')}: {e}")

# -------------------------------
# Show results / select properties to display
# -------------------------------
if st.session_state["properties"]:
    st.subheader("🏡 My Properties")

    # multi-select to choose which properties to view (explicit control)
    keys = list(st.session_state["properties"].keys())
    selected_keys = st.multiselect("Select property(ies) to display", options=keys, default=[keys[0]])

    if not selected_keys:
        st.info("Select one or more properties to view details.")
    else:
        for k in selected_keys:
            st.markdown(f"### 📑 {k} — {st.session_state['properties'][k].get('Property Address','(no address)')}")
            data = st.session_state["properties"][k]
            # convert OrderedDict to DataFrame single row for display
            df = pd.DataFrame([data])
            st.dataframe(df, use_container_width=True)

        # quick summary: how many properties
        st.caption(f"Total properties stored: {len(keys)}")
else:
    st.info("📌 No properties yet. Upload one or more PDF files to get started.")
