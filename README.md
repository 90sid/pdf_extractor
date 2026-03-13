# PDF Extractor (LLM-powered)

A Streamlit app that learns an extraction template from:
- a demo PDF, and
- a demo output file (CSV/XLSX)

Then it applies that template to a batch of similar PDFs and exports either:
- merged output (demo-style),
- separate `documents.csv` and `line_items.csv`, or
- both.

## What this project does

This app is designed for semi-structured business documents such as:
- utility bills
- invoices
- waste management bills
- vendor statements
- similar recurring PDFs

The idea is:
1. User uploads one sample PDF.
2. User uploads the expected output format in Excel/CSV.
3. The app infers the schema from the demo output.
4. The LLM studies the demo PDF + expected output and writes internal extraction instructions.
5. A template is saved by name.
6. User uploads a batch of similar PDFs.
7. The app extracts data and exports CSV files.

---

## Core concepts

### 1) Template-driven extraction
A template is a JSON file stored in `templates/`.

Each template contains:
- `template_name`
- `doc_fields` → invoice/header-level fields
- `line_item_fields` → row-level fields
- `has_line_items` → whether the PDF contains repeated table rows
- `instructions` → LLM-generated extraction guidance
- `output_columns` → exact merged output column order
- normalization + validation rules

This means users do not need to rewrite prompts every time.

### 2) LLM as the extraction brain
The LLM is used in two places:

#### A. Template generation
Input:
- demo PDF text
- demo output schema
- sample expected row(s)

Output:
- reusable extraction instructions stored in the template JSON

#### B. Batch extraction
Input:
- PDF text
- template JSON

Output:
- strict structured JSON:
  - `document`
  - `line_items`
  - `confidence`

### 3) OCR fallback
The app is text-first.

It first tries native PDF text extraction.
If the PDF appears scanned or text extraction is too weak, it falls back to OCR.

So it supports:
- normal digital PDFs
- scanned image PDFs
- mixed-quality PDFs

### 4) Output modes
Users can choose:
- **Merged (demo format)** → one flat CSV like the sample layout
- **Separate** → `documents.csv` + `line_items.csv`
- **Both**

### 5) Template editor
A non-technical user can edit:
- field names
- field types
- required flags
- merged output column order

This is for output layout control, not core extraction logic.

---

## High-level project flow

### Step 1: Create template
In Streamlit tab: **Create / Save Template**

User uploads:
- one demo PDF
- one demo output file (CSV/XLSX)

The system then:
1. reads the PDF text
2. applies OCR fallback if needed
3. reads the demo output
4. detects whether output is:
   - document-only, or
   - merged document + line items, or
   - separate docs + line items
5. builds schema:
   - `doc_fields`
   - `line_item_fields`
6. sends demo context to the LLM
7. stores the returned instructions in a template JSON

Saved template location:
- `templates/<template_name>.json`

### Step 2: Edit template (optional)
In Streamlit tab: **Template Editor**

User can:
- rename fields
- reorder merged output columns
- review doc fields and line item fields
- save updated template

### Step 3: Run batch extraction
In Streamlit tab: **Run Batch Extraction**

User selects:
- a template
- output format (merged / separate / both)
- one or more PDFs

For each PDF:
1. extract text
2. OCR if needed
3. call LLM with template instructions
4. receive structured JSON
5. build document rows and line-item rows
6. write CSV output(s)
7. post-process merged output for common extraction mistakes

---

## Main files and what they do

### `app.py`
Main Streamlit UI.

Contains:
- Create Template tab
- Template Editor tab
- Run Batch Extraction tab
- file upload handling
- save/load templates
- output downloads
- merged output post-processing hook

### `core/pdf_text.py`
Handles PDF reading.

Responsibilities:
- extract text from text-based PDFs
- use OCR fallback for scanned PDFs
- return `used_ocr` flag

### `core/template_builder.py`
Builds the template schema from the demo output.

Responsibilities:
- read CSV/XLSX
- detect merged demo format
- split doc fields vs line item fields
- infer column types
- return `TemplateSpec`

### `core/extractor.py`
LLM integration.

Responsibilities:
- generate instructions from demo PDF + output
- extract structured data from batch PDFs using saved template
- enforce JSON-only output shape
- repair invalid JSON if needed

### `core/llm_client.py`
Creates the OpenAI client and reads:
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

### `core/csv_writer.py`
Writes output files.

Responsibilities:
- create `documents.csv`
- create `line_items.csv`
- create `merged.csv`
- enforce merged output column order from template

### `core/postprocess.py`
Post-extraction cleanup.

Current use case:
- fixes cases where invoice total gets repeated as every line-item amount

You can extend this file for:
- cleaning description fields
- removing service address from description
- standardizing vendor-specific patterns

### `templates/`
Stores saved template JSON files.

Examples:
- `republic final.json`
- `demo1_esg.json`
- `roadrunner.json`

### `runs/`
Temporary output folder for each batch run.

Typically contains:
- uploaded PDFs for that run
- `documents.csv`
- `line_items.csv`
- `merged.csv`

---

## How OCR works

The system follows this logic:
1. try regular text extraction
2. if extracted text is too small / poor
3. use OCR

The output stores whether OCR was used:
- `used_ocr = True`
- `used_ocr = False`

This helps debug bad scans.

---

## How line items are handled

There are two data levels:

### Document fields
These are one-per-invoice fields like:
- Invoice Number
- Account Number
- Invoice Date
- Due Date
- Utility Name
- Service Address

### Line item fields
These repeat per row, like:
- Description
- Product
- Quantity
- Unit Price
- Amount
- WO Number
- PO Number

When `has_line_items = true`, extraction returns:
- one document object
- many line item objects

When merged output is requested, document fields are repeated for every line-item row.

---

## How template generation works

The template is learned from:
- demo PDF content
- demo output layout

The app does not simply save a user-written prompt.
It creates a structured template and lets the LLM generate internal instructions.

This is more stable because:
- output columns are controlled separately
- extraction instructions are reusable
- merged/separate exports are flexible

---

## Current known protections / fixes

### 1) JSON safety for demo rows
Excel may load date cells as `Timestamp`.
Before sending demo rows to the LLM prompt builder, the app converts them into JSON-safe strings.

### 2) Repeated invoice total bug
Some invoices accidentally produce the invoice total as the line-item amount for every row.
A post-process fix recalculates the line-item amount from:
- `Quantity * Unit Price`, or
- `Unit Price`

### 3) Merged output column control
Merged output follows `output_columns` stored in the template.
So non-technical users can control final layout without rewriting prompts.

---

## How to run locally

### 1. Create and activate a virtual environment

Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

Mac/Linux:
```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Create `.env`
```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1
```

### 4. Run Streamlit
```bash
streamlit run app.py
```

---

## How to deploy on Streamlit Community Cloud

### Required repo files
- `app.py`
- `requirements.txt`
- `packages.txt`
- `core/`
- `templates/`

### `packages.txt`
For OCR support on Streamlit Cloud:
```txt
tesseract-ocr
poppler-utils
```

### Secrets on Streamlit Cloud


```toml
OPENAI_API_KEY="your_key_here"
OPENAI_MODEL="gpt-4.1"
```

---

## Typical user flow

### For a business user
1. Open app
2. Go to **Create / Save Template**
3. Upload demo PDF
4. Upload sample output Excel/CSV
5. Save template
6. Go to **Run Batch Extraction**
7. Select template
8. Upload similar PDFs
9. Choose output mode
10. Download CSV

### For an admin / developer
1. Review generated template JSON
2. Adjust field split if needed
3. Use Template Editor for final output layout
4. Add post-process fixes for vendor-specific quirks

---

