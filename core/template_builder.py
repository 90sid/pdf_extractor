from dataclasses import dataclass
from typing import List, Optional, Tuple
import pandas as pd
import os
import re
from datetime import datetime


@dataclass
class TemplateSpec:
    template_name: str
    doc_fields: List[dict]
    line_item_fields: Optional[List[dict]]
    has_line_items: bool
    normalization: dict
    validation_rules: List[str]
    created_at: str


def _infer_type(series: pd.Series) -> str:
    s = series.dropna().astype(str).head(30).tolist()
    if not s:
        return "string"

    date_like = 0
    num_like = 0

    for v in s:
        v2 = v.strip()

        # date-like
        if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", v2) or re.match(r"^\d{4}-\d{2}-\d{2}$", v2):
            date_like += 1

        # number-like (currency/negative)
        if re.match(r"^[₹$]?\s?-?\d{1,3}(,\d{3})*(\.\d+)?$", v2) or re.match(r"^-?\d+(\.\d+)?$", v2):
            num_like += 1

    if date_like >= max(3, len(s)//3):
        return "date"
    if num_like >= max(3, len(s)//3):
        return "number"
    return "string"


def _is_line_item_col(col: str) -> bool:
    c = str(col).strip().lower()
    patterns = [
        r"\bproduct\b", r"\bitem\b",
        r"\bdescription\b", r"\bline[_ ]?description\b",
        r"\bline[_ ]?date\b", r"^date$",
        r"\bqty\b", r"\bquantity\b",
        r"\bunit[_ ]?rate\b", r"\brate\b",
        r"\bline[_ ]?total\b", r"\bunit[_ ]?price\b",
        r"\bwo\b", r"\bwo[_ ]?#\b", r"\bwo[_ ]?number\b",
        r"\bpo\b", r"\bpo[_ ]?#\b", r"\bpo[_ ]?number\b",
        r"\bsite[_ ]?id\b", r"\bsite[_ ]?address\b",
    ]
    return any(re.search(p, c) for p in patterns)


def _find_join_key(cols: List[str]) -> Optional[str]:
    lowered = [c.strip().lower() for c in cols]
    for key in ["file name", "file_name", "filename", "source_file", "file"]:
        for i, c in enumerate(lowered):
            if c == key:
                return cols[i]
    return None


def read_demo_output(path: str) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], List[str]]:
    """
    Returns:
      doc_df (one row per file/invoice)
      line_df (many rows; or None)
      output_columns (original column order from demo file - used for merged output)
    """
    ext = os.path.splitext(path)[1].lower()

    def split_merged(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        cols = [str(c) for c in df.columns]
        join_key = _find_join_key(cols)

        line_cols = [c for c in cols if _is_line_item_col(c)]
        doc_cols = [c for c in cols if c not in line_cols]

        # Keep join key on both sides if present
        if join_key:
            if join_key not in doc_cols:
                doc_cols = [join_key] + doc_cols
            if join_key not in line_cols:
                line_cols = [join_key] + line_cols

        doc_df = df[doc_cols].copy()
        # one doc row per file if possible
        if join_key and join_key in doc_df.columns:
            doc_df = doc_df.drop_duplicates(subset=[join_key], keep="first")

        line_df = df[line_cols].copy()
        return doc_df, line_df

    if ext == ".csv":
        df = pd.read_csv(path)
        output_columns = [str(c) for c in df.columns]

        # If it looks like merged (has any line-item cols), split it
        if any(_is_line_item_col(c) for c in df.columns):
            doc_df, line_df = split_merged(df)
            # only treat as line items if line_df has at least 1 non-key column
            if len(line_df.columns) > 1:
                return doc_df, line_df, output_columns

        return df, None, output_columns

    if ext in [".xlsx", ".xls"]:
        xls = pd.ExcelFile(path)
        sheets = xls.sheet_names

        # If multiple sheets: docs + line items
        if len(sheets) >= 2:
            doc_df = pd.read_excel(path, sheet_name=sheets[0])
            output_columns = [str(c) for c in doc_df.columns]

            # choose likely line sheet
            line_sheet = None
            for sh in sheets[1:]:
                if re.search(r"(item|line|detail)", sh, re.I):
                    line_sheet = sh
                    break
            if line_sheet is None:
                line_sheet = sheets[1]

            line_df = pd.read_excel(path, sheet_name=line_sheet)
            return doc_df, line_df, output_columns

        # Single sheet: could be merged
        df = pd.read_excel(path, sheet_name=sheets[0])
        output_columns = [str(c) for c in df.columns]

        if any(_is_line_item_col(c) for c in df.columns):
            doc_df, line_df = split_merged(df)
            if len(line_df.columns) > 1:
                return doc_df, line_df, output_columns

        return df, None, output_columns

    raise ValueError("Unsupported demo output format. Use CSV or XLSX.")


def build_template_spec(template_name: str, doc_df: pd.DataFrame, line_df: Optional[pd.DataFrame]) -> TemplateSpec:
    doc_fields = [{"name": str(col), "type": _infer_type(doc_df[col]), "required": True} for col in doc_df.columns]

    has_line_items = line_df is not None and len(line_df.columns) > 0 and len(line_df) > 0
    line_item_fields = None

    if has_line_items:
        # mark line fields not required by default
        line_item_fields = [{"name": str(col), "type": _infer_type(line_df[col]), "required": False} for col in line_df.columns]

    return TemplateSpec(
        template_name=template_name,
        doc_fields=doc_fields,
        line_item_fields=line_item_fields,
        has_line_items=has_line_items,
        normalization={
            "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"],
            "currency_symbols": ["₹", "$", "INR", "USD"]
        },
        validation_rules=[
            "If totals exist: total ~= subtotal + tax",
            "If line items exist: total ~= sum(line_items.amount)"
        ],
        created_at=datetime.utcnow().isoformat() + "Z",
    )
