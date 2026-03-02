import fitz  # PyMuPDF
from dataclasses import dataclass
from typing import Optional
import pytesseract
from PIL import Image
import io

@dataclass
class PDFTextResult:
    text: str
    used_ocr: bool
    page_count: int

def extract_text_pymupdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
    return "\n".join(parts)

def ocr_pdf_pymupdf(pdf_path: str, max_pages: Optional[int] = None) -> str:
    doc = fitz.open(pdf_path)
    parts = []
    page_limit = min(len(doc), max_pages) if max_pages else len(doc)
    for i in range(page_limit):
        page = doc[i]
        pix = page.get_pixmap(dpi=200)  # better OCR accuracy
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        parts.append(pytesseract.image_to_string(img))
    return "\n".join(parts)

def pdf_to_text(pdf_path: str, ocr_threshold_chars: int = 200) -> PDFTextResult:
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    text = extract_text_pymupdf(pdf_path)
    cleaned = (text or "").strip()

    if len(cleaned) < ocr_threshold_chars:
        ocr_text = ocr_pdf_pymupdf(pdf_path)
        return PDFTextResult(text=ocr_text, used_ocr=True, page_count=page_count)

    return PDFTextResult(text=text, used_ocr=False, page_count=page_count)
