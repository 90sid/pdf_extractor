import os
import pandas as pd
from typing import List, Dict, Any, Optional


def _apply_column_order(df: pd.DataFrame, desired_cols: Optional[List[str]]) -> pd.DataFrame:
    if not desired_cols:
        return df

    # Add any missing columns as blank
    for c in desired_cols:
        if c not in df.columns:
            df[c] = ""

    # Keep only desired columns and order exactly
    df = df[desired_cols]
    return df


def write_run_csvs(
    run_dir: str,
    documents: List[Dict[str, Any]],
    line_items: Optional[List[Dict[str, Any]]] = None,
    merged: bool = True,
    join_key: str = "source_file",
    merged_output_columns: Optional[List[str]] = None,
    write_documents: bool = True,
    write_line_items: bool = True,
) -> Dict[str, str]:
    """
    Writes:
      - documents.csv (optional)
      - line_items.csv (optional)
      - merged.csv (optional; demo style: doc fields repeated for each line item)

    If merged_output_columns is provided, merged.csv is forced into that exact order.
    """
    os.makedirs(run_dir, exist_ok=True)
    out: Dict[str, str] = {}

    doc_df = pd.DataFrame(documents) if documents else pd.DataFrame()
    li_df = pd.DataFrame(line_items) if line_items is not None else None

    # --- documents.csv ---
    if write_documents:
        doc_path = os.path.join(run_dir, "documents.csv")
        doc_df.to_csv(doc_path, index=False)
        out["documents_csv"] = doc_path

    # --- line_items.csv ---
    if write_line_items and li_df is not None:
        li_path = os.path.join(run_dir, "line_items.csv")
        li_df.to_csv(li_path, index=False)
        out["line_items_csv"] = li_path

    # --- merged.csv ---
    if merged:
        merged_path = os.path.join(run_dir, "merged.csv")

        if li_df is None or li_df.empty:
            merged_df = doc_df.copy()
        else:
            if doc_df.empty:
                merged_df = li_df.copy()
            else:
                if join_key not in doc_df.columns:
                    raise ValueError(f"documents missing join_key '{join_key}'")
                if join_key not in li_df.columns:
                    raise ValueError(f"line_items missing join_key '{join_key}'")

                merged_df = li_df.merge(doc_df, on=join_key, how="left")

        merged_df = _apply_column_order(merged_df, merged_output_columns)
        merged_df.to_csv(merged_path, index=False)
        out["merged_csv"] = merged_path

    return out
