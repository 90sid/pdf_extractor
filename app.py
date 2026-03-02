import os
import json
import uuid
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from core.pdf_text import pdf_to_text
from core.template_builder import read_demo_output, build_template_spec
from core.extractor import generate_instructions_from_demo, extract_with_template
from core.csv_writer import write_run_csvs

st.set_page_config(page_title="PDF Extractor", layout="wide")

TEMPLATES_DIR = "templates"
RUNS_DIR = "runs"
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(RUNS_DIR, exist_ok=True)


def list_templates():
    return sorted([f[:-5] for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")])


def load_template(name: str) -> dict:
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_template(name: str, data: dict) -> str:
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def fields_to_df(fields: list) -> pd.DataFrame:
    # fields: [{name,type,required}, ...]
    return pd.DataFrame(fields)


def df_to_fields(df: pd.DataFrame) -> list:
    # Ensure required columns exist
    df = df.copy()
    if "name" not in df.columns:
        df["name"] = ""
    if "type" not in df.columns:
        df["type"] = "string"
    if "required" not in df.columns:
        df["required"] = False

    out = []
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "type": str(row.get("type", "string")).strip() or "string",
                "required": bool(row.get("required", False)),
            }
        )
    return out


# ---------- JSON-safe helper (fix Timestamp / NaN serialization) ----------
def make_json_safe(obj):
    """
    Convert pandas/numpy objects to JSON-safe primitives so json.dumps() won't crash.
    - Timestamp -> "YYYY-MM-DD"
    - NaN/NaT -> ""
    """
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_json_safe(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    # NaN / NaT
    try:
        if pd.isna(obj):
            return ""
    except Exception:
        pass
    return obj


st.title("📄 PDF Extractor (LLM-powered)")
model_name = os.getenv("OPENAI_MODEL", "gpt-4.1")
key_ok = bool(os.getenv("OPENAI_API_KEY", "").strip())
st.caption(f"Model: {model_name} | API key loaded: {'✅' if key_ok else '❌'}")

tab1, tab2, tab3 = st.tabs(["Create / Save Template", "Template Editor", "Run Batch Extraction"])

# ----------------------- TAB 1: CREATE TEMPLATE -----------------------
with tab1:
    st.subheader("Upload demo PDF + demo output (CSV/XLSX) to create a template")
    template_name = st.text_input("Template Name (unique)", value="")

    demo_pdf = st.file_uploader("Demo PDF", type=["pdf"])
    demo_output = st.file_uploader("Demo Output (CSV/XLSX)", type=["csv", "xlsx", "xls"])

    if st.button("Generate Template", disabled=not (template_name and demo_pdf and demo_output)):
        tmp_dir = os.path.join(RUNS_DIR, "_tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        demo_pdf_path = os.path.join(tmp_dir, f"demo_{uuid.uuid4().hex}.pdf")
        out_path = os.path.join(tmp_dir, f"demo_output_{uuid.uuid4().hex}_{demo_output.name}")

        with open(demo_pdf_path, "wb") as f:
            f.write(demo_pdf.getbuffer())
        with open(out_path, "wb") as f:
            f.write(demo_output.getbuffer())

        pdf_res = pdf_to_text(demo_pdf_path)
        st.info(f"Demo PDF loaded. OCR used: {pdf_res.used_ocr} | pages: {pdf_res.page_count}")

        # UPDATED: read_demo_output returns 3 values
        doc_df, line_df, output_columns = read_demo_output(out_path)

        st.write("Demo documents output preview:")
        st.dataframe(doc_df.head(5))

        if line_df is not None:
            st.write("Demo line-items preview:")
            st.dataframe(line_df.head(5))

        spec = build_template_spec(template_name, doc_df, line_df)

        # IMPORTANT: make demo rows JSON-safe before passing to LLM prompt builder
        demo_doc_row = make_json_safe(doc_df.iloc[0].to_dict()) if len(doc_df) else {}
        demo_line_rows = (
            make_json_safe(line_df.head(10).to_dict(orient="records"))
            if line_df is not None and len(line_df)
            else None
        )

        with st.spinner("Generating extraction instructions with LLM..."):
            instructions = generate_instructions_from_demo(
                demo_pdf_text=pdf_res.text,
                doc_schema=spec.doc_fields,
                line_schema=spec.line_item_fields,
                demo_doc_row=demo_doc_row,
                demo_line_rows=demo_line_rows,
            )

        template_dict = spec.__dict__
        template_dict["instructions"] = instructions

        # IMPORTANT: keep the demo output column order for merged output
        # (So merged.csv matches the excel layout user uploaded)
        template_dict["output_columns"] = output_columns

        save_path = save_template(template_name, template_dict)
        st.success(f"Template saved: {save_path}")
        st.json(template_dict)

# ----------------------- TAB 2: TEMPLATE EDITOR -----------------------
with tab2:
    st.subheader("Edit template column names and output order (non-technical friendly)")
    templates = list_templates()
    if not templates:
        st.warning("No templates found. Create one in the first tab.")
    else:
        selected = st.selectbox("Select template to edit", templates, key="edit_template_select")
        t = load_template(selected)

        st.markdown("### Document fields (documents.csv)")
        doc_df_editor = fields_to_df(t.get("doc_fields", []))
        edited_doc_df = st.data_editor(
            doc_df_editor,
            num_rows="dynamic",
            use_container_width=True,
            key="doc_fields_editor",
        )

        st.markdown("### Line item fields (line_items.csv)")
        li_fields = t.get("line_item_fields") or []
        li_df_editor = fields_to_df(li_fields)
        edited_li_df = st.data_editor(
            li_df_editor,
            num_rows="dynamic",
            use_container_width=True,
            key="li_fields_editor",
        )

        st.markdown("### Output column order for merged.csv (demo format)")
        st.caption("One column name per line. This controls the exact column order in merged.csv.")
        current_output_cols = t.get("output_columns")
        if not current_output_cols:
            doc_names = [x["name"] for x in t.get("doc_fields", [])]
            li_names = [x["name"] for x in (t.get("line_item_fields") or [])]
            current_output_cols = ["source_file"] + doc_names + li_names

        output_text = st.text_area(
            "Merged output columns (exact order)",
            value="\n".join(current_output_cols),
            height=260,
            key="output_cols_text",
        )

        st.markdown("### Save")
        if st.button("Save Template Changes"):
            new_doc_fields = df_to_fields(edited_doc_df)
            new_li_fields = df_to_fields(edited_li_df)

            t["doc_fields"] = new_doc_fields
            t["line_item_fields"] = new_li_fields
            t["has_line_items"] = True if new_li_fields else bool(t.get("has_line_items"))

            cols = [c.strip() for c in output_text.splitlines() if c.strip()]
            t["output_columns"] = cols

            save_path = save_template(selected, t)
            st.success(f"Saved: {save_path}")

            st.write("Updated template preview:")
            st.json(t)

# ----------------------- TAB 3: RUN BATCH -----------------------
with tab3:
    st.subheader("Select template + upload batch PDFs")
    templates = list_templates()
    if not templates:
        st.warning("No templates found. Create one in the first tab.")
    else:
        selected = st.selectbox("Template", templates, key="run_template_select")

        output_mode = st.radio(
            "Select output format",
            options=["Merged (demo format)", "Separate (documents + line items)", "Both"],
            index=2,
        )

        batch_pdfs = st.file_uploader("Batch PDFs", type=["pdf"], accept_multiple_files=True)

        if st.button("Run Extraction", disabled=not (selected and batch_pdfs)):
            template = load_template(selected)

            run_id = uuid.uuid4().hex[:10]
            run_dir = os.path.join(RUNS_DIR, run_id)
            os.makedirs(run_dir, exist_ok=True)

            documents_rows = []
            line_items_rows = [] if template.get("has_line_items") else None

            progress = st.progress(0)
            total = len(batch_pdfs)

            for idx, up in enumerate(batch_pdfs, start=1):
                pdf_path = os.path.join(run_dir, up.name)
                with open(pdf_path, "wb") as f:
                    f.write(up.getbuffer())

                pdf_res = pdf_to_text(pdf_path)

                with st.spinner(f"Extracting: {up.name}"):
                    result = extract_with_template(pdf_res.text, template)

                doc_row = result.get("document", {})
                doc_row["source_file"] = up.name
                doc_row["used_ocr"] = pdf_res.used_ocr
                doc_row["confidence"] = result.get("confidence", 0.0)
                doc_row["needs_review"] = (doc_row["confidence"] < 0.7)

                documents_rows.append(doc_row)

                if line_items_rows is not None:
                    for li in result.get("line_items", []) or []:
                        li["source_file"] = up.name
                        line_items_rows.append(li)

                progress.progress(idx / total)

            want_merged = output_mode in ["Merged (demo format)", "Both"]
            want_separate = output_mode in ["Separate (documents + line items)", "Both"]

            merged_cols = template.get("output_columns") if want_merged else None

            paths = write_run_csvs(
                run_dir=run_dir,
                documents=documents_rows,
                line_items=line_items_rows,
                merged=want_merged,
                join_key="source_file",
                merged_output_columns=merged_cols,
                write_documents=want_separate,
                write_line_items=want_separate and (line_items_rows is not None),
            )

            # ✅ Post-process merged output to fix repeated invoice-total-as-line-amount bug
            if "merged_csv" in paths:
                from core.postprocess import fix_repeated_invoice_total_amount

                merged_df = pd.read_csv(paths["merged_csv"])
                merged_df = fix_repeated_invoice_total_amount(merged_df)
                merged_df.to_csv(paths["merged_csv"], index=False)

            st.success(f"Done. Run folder: {run_dir}")

            # Previews
            if want_separate:
                st.write("Documents preview:")
                st.dataframe(pd.DataFrame(documents_rows).head(50))

                if line_items_rows is not None:
                    st.write("Line items preview:")
                    if line_items_rows:
                        st.dataframe(pd.DataFrame(line_items_rows).head(50))
                    else:
                        st.info("No line items extracted in this run.")

            if want_merged and "merged_csv" in paths:
                st.write("Merged preview (demo format):")
                merged_df = pd.read_csv(paths["merged_csv"])
                st.dataframe(merged_df.head(50))

            # Downloads
            if want_separate:
                if "documents_csv" in paths:
                    with open(paths["documents_csv"], "rb") as f:
                        st.download_button("Download documents.csv", f, file_name="documents.csv")
                if "line_items_csv" in paths:
                    with open(paths["line_items_csv"], "rb") as f:
                        st.download_button("Download line_items.csv", f, file_name="line_items.csv")

            if want_merged and "merged_csv" in paths:
                with open(paths["merged_csv"], "rb") as f:
                    st.download_button("Download merged.csv (demo format)", f, file_name="merged.csv")
