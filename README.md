
# Docket QC Checker — Web (Improved Text Extraction)

This version adds a **pdfminer.six** fallback. If your PDF still shows *"Could not extract text"*, it is likely a **scanned image**. Please **OCR** the file first using:
- **Adobe Acrobat** → Scan & OCR → Recognize Text.
- **PDF24 Creator** (Windows, free) → OCR.
- **Smallpdf / iLovePDF OCR** (online; check privacy conditions).

## Deploy
- Upload `app.py`, `requirements.txt`, `README.md` to GitHub → Deploy on Streamlit Cloud.
