
# Docket QC Checker — Web Deploy

This bundle is ready for **no-install web hosting** (Streamlit Community Cloud or Hugging Face Spaces).

## Deploy to Streamlit Community Cloud (free)
1. Create a **GitHub repo** and upload these files (`app.py`, `requirements.txt`, `README.md`).  
2. Go to https://share.streamlit.io/ → **Sign in** → **New app** → point to your repo and branch → **Deploy**.  
3. (Optional) Set a password: in Streamlit Cloud, open **App → Settings → Secrets**, add:
```
STREAMLIT_PASSWORD = "yourpassword"
```
4. Share the URL with your team. They can upload PDFs directly in the browser.

## Deploy to Hugging Face Spaces (free)
1. Create a **Space** → type: **Streamlit**.  
2. Upload the same files (`app.py`, `requirements.txt`, `README.md`).  
3. The app builds automatically and gives you a URL to share.  
4. For a password, use a **HF secret** named `STREAMLIT_PASSWORD` and read it in the app via `st.secrets` (already supported).

## Notes
- Files are processed **in-memory**; the app does not save PDFs to disk.  
- For best results, upload **searchable PDFs** (OCR scans if needed).  
- Adjust the **tolerance** from the app UI.  
- You can also upload a custom `rules.json` to enable/disable checks and contexts.
