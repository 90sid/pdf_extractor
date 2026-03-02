import json
from typing import Optional, Any, Dict, List
from core.llm_client import get_client, get_model_name

# --------- A) Build template instructions from demo ---------

def generate_instructions_from_demo(
    demo_pdf_text: str,
    doc_schema: list,
    line_schema: Optional[list],
    demo_doc_row: dict,
    demo_line_rows: Optional[list],
) -> str:
    """
    Takes demo PDF text + expected demo output and produces reusable extraction instructions.
    Stored in template JSON as "instructions".
    """
    client = get_client()
    model = get_model_name()

    # Keep prompt size bounded
    demo_text = (demo_pdf_text or "")[:120000]

    prompt = f"""
You are building an extraction template for similar PDFs.

Goal:
- Write concise, reusable extraction instructions that will reliably extract the desired fields.
- Use label anchoring (e.g., "Invoice No", "Bill No", "Invoice #"), nearby values, and robust patterns.
- Include normalization rules for dates and numbers (remove commas/currency symbols).
- If line items exist, explain how to detect the table region and map columns.

Document fields schema (name/type/required):
{json.dumps(doc_schema, ensure_ascii=False, indent=2)}

Line item fields schema (name/type/required):
{json.dumps(line_schema, ensure_ascii=False, indent=2) if line_schema else "None"}

Expected extracted output for THIS demo PDF (document row):
{json.dumps(demo_doc_row, ensure_ascii=False, indent=2)}

Expected extracted output for THIS demo PDF (sample line rows):
{json.dumps(demo_line_rows, ensure_ascii=False, indent=2) if demo_line_rows else "None"}

Demo PDF text:
---START---
{demo_text}
---END---

Return ONLY a plain text instruction block (no JSON, no markdown).
Keep it short and operational (like a playbook).
"""

    resp = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=1200,
    )

    instructions = (resp.output_text or "").strip()
    return instructions


# --------- B) Extract a new PDF using saved template ---------

def _build_output_shape(doc_fields: List[str], has_lines: bool, line_fields: List[str]) -> Dict[str, Any]:
    shape = {
        "document": {k: "" for k in doc_fields},
        "line_items": [],
        "confidence": 0.0,
    }
    if has_lines:
        # just an example object; actual output is an array
        _ = {k: "" for k in line_fields}
    return shape

def _safe_json_loads_maybe(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None

def extract_with_template(pdf_text: str, template: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns:
      {
        "document": {...},
        "line_items": [ {...}, ... ],
        "confidence": 0.0-1.0
      }
    """
    client = get_client()
    model = get_model_name()

    doc_fields = [f["name"] for f in template.get("doc_fields", [])]
    has_lines = bool(template.get("has_line_items"))
    line_fields = [f["name"] for f in (template.get("line_item_fields") or [])]

    instructions = (template.get("instructions") or "").strip()

    # Bound context
    text = (pdf_text or "")[:120000]

    expected_shape = _build_output_shape(doc_fields, has_lines, line_fields)

    system = "You extract structured data from PDF text. Output must be valid JSON only."
    user = f"""
Use the extraction instructions below to extract data from the PDF text.

INSTRUCTIONS:
{instructions}

OUTPUT FORMAT (must match exactly):
{json.dumps(expected_shape, ensure_ascii=False, indent=2)}

Rules:
- JSON ONLY. No markdown. No extra keys beyond: document, line_items, confidence.
- For line_items: you must return ALL charge rows until the subtotal line; do not omit rows that appear after earlier amounts.
- document must include ALL keys exactly as provided; if unknown, use empty string.
- line_items must be an array of objects with keys:
  {json.dumps({k: "" for k in line_fields}, ensure_ascii=False) if has_lines else "[]"}
  If no line items found, return [].
- confidence is a number 0.0 to 1.0.
- Keep values clean: strip whitespace; numbers should not include currency symbols or commas if possible.
- For line_items: extract ALL rows in the table(s), not only the first row. Include rows across all sections/sites until the table ends or the next section starts.


PDF TEXT:
---START---
{text}
---END---
"""

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_output_tokens=3500,
    )

    raw = (resp.output_text or "").strip()

    # Attempt parse + 1 repair attempt
    data = _safe_json_loads_maybe(raw)
    if data is None:
        fix = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": "Fix invalid JSON. Output valid JSON only. Keep the same keys."},
                {"role": "user", "content": raw},
            ],
            max_output_tokens=1200,
        )
        raw2 = (fix.output_text or "").strip()
        data = _safe_json_loads_maybe(raw2)

    # Final fallback if still broken
    if data is None or not isinstance(data, dict):
        return {"document": {k: "" for k in doc_fields}, "line_items": [], "confidence": 0.0}

    # Minimal sanitization: ensure keys exist
    if "document" not in data or not isinstance(data["document"], dict):
        data["document"] = {k: "" for k in doc_fields}
    for k in doc_fields:
        data["document"].setdefault(k, "")

    if "line_items" not in data or not isinstance(data["line_items"], list):
        data["line_items"] = []
    if not has_lines:
        data["line_items"] = []

    conf = data.get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.0
    data["confidence"] = max(0.0, min(1.0, conf))

    return data
