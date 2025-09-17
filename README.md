
# Docket QC Checker — pdfminer-only

This build uses only **pdfminer.six** for text extraction (more reliable on Streamlit Cloud).

## Deploy
1. Create a GitHub repo and upload:
   - app.py
   - requirements.txt
   - README.md
2. On https://share.streamlit.io → New app → pick your repo → set main file to `app.py` → Deploy.

## Debugging
- Page 1 text preview is shown in the app. If it displays readable text, extraction works.
- If it's empty, the PDF is likely image-only or encrypted. OCR it once, then try again.
