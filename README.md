
# Docket QC Checker — PyPDF2 + Text Download

This build uses **PyPDF2** for extraction and adds:
- Download raw text for a selected page (.txt)
- Download all pages as a ZIP of .txt files

## Deploy
1. Upload these to your GitHub repo:
   - app.py
   - requirements.txt
   - README.md
2. On https://share.streamlit.io → New app or Manage app → set main file to `app.py` → Deploy.

## Notes
- If Page 1 preview is empty, the PDF might be image-only or encrypted → OCR it once and try again.
