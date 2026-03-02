import pandas as pd

def fix_repeated_invoice_total_amount(df: pd.DataFrame) -> pd.DataFrame:
    """
    If Amount is wrongly constant across most rows (often invoice total),
    replace line Amount with:
      - Quantity * Unit Price if Quantity exists
      - else Unit Price
    """
    if df is None or df.empty:
        return df

    # Find columns (case-insensitive)
    def find_col(names):
        for c in df.columns:
            if str(c).strip().lower() in names:
                return c
        return None

    amt_col = find_col({"amount"})
    up_col = find_col({"unit price", "unit_price", "unit rate", "unit_rate"})
    qty_col = find_col({"quantity", "qty"})

    if not amt_col or not up_col:
        return df

    mode_vals = df[amt_col].dropna().mode()
    if mode_vals.empty:
        return df
    common_amount = mode_vals.iloc[0]

    try:
        share = (df[amt_col] == common_amount).mean()
    except Exception:
        return df

    # If 60%+ of rows share identical Amount, likely wrong
    if share < 0.60:
        return df

    def to_float(x):
        if pd.isna(x):
            return None
        s = str(x).strip().replace("$", "").replace(",", "")
        if s == "":
            return None
        try:
            return float(s)
        except Exception:
            return None

    def compute_row(r):
        up = to_float(r.get(up_col))
        if up is None:
            return r.get(amt_col)
        if qty_col:
            qty = to_float(r.get(qty_col))
            if qty is not None:
                return qty * up
        return up

    df[amt_col] = df.apply(compute_row, axis=1)
    return df
