"""Extracts text from an image (e.g. a receipt/invoice photo sent over
WhatsApp).

SPEC.md originally called for a local Ollama vision model for this. That
needs a fairly large local model download and a running Ollama server —
not something this scaffold can assume is present. Tesseract OCR is used
here instead: it's free, fully offline, works well for printed receipt
text, and needs only a small system package (not a multi-GB model). If
you'd rather use Ollama's vision models, this is the one function to
swap out — nothing else in the WhatsApp flow needs to change.

Setup (one-time, needs internet to download the package/language data,
same as vendor_assets.py — after that, fully offline):
  Windows : choco install tesseract  (or the installer from
            https://github.com/UB-Mannheim/tesseract/wiki)
  Linux   : sudo apt install tesseract-ocr tesseract-ocr-ara
  macOS   : brew install tesseract tesseract-lang
  then:     pip install pytesseract Pillow
"""
from __future__ import annotations


def extract_text_from_image(image_bytes: bytes) -> str:
    try:
        import io

        import pytesseract
        from PIL import Image
    except ImportError:
        return (
            "[تعذّر تشغيل OCR — لازم تثبّت pytesseract و Pillow و Tesseract OCR "
            "على الجهاز أولاً. راجع التعليق أعلى هذا الملف للخطوات.]"
        )

    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Arabic + English — receipts in this shop are usually bilingual.
        text = pytesseract.image_to_string(image, lang="ara+eng")
        return text.strip() or "[لم يتم العثور على أي نص في الصورة]"
    except Exception as exc:  # pytesseract raises its own exception types
        return f"[حدث خطأ أثناء قراءة الصورة: {exc}]"
