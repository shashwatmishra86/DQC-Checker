
import re
import io
import json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Docket QC Checker (Web)", layout="wide")
st.title("🧰 Docket QC Checker — Web (Improved Text Extraction)")
st.caption("If your PDF is a scan (image-only), please OCR it first (see tips below).")

def extract_text_bytes(pdf_bytes):
    text_pages = []

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                try:
                    text_pages.append(page.extract_text() or "")
                except Exception:
                    text_pages.append("")
    except Exception:
        pass

    if not any(text_pages) or all(tp.strip()=="" for tp in text_pages):
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            tmp = []
            for page in reader.pages:
                try:
                    tmp.append(page.extract_text() or "")
                except Exception:
                    tmp.append("")
            if any(tmp):
                text_pages = tmp
        except Exception:
            pass

    if not any(text_pages) or all(tp.strip()=="" for tp in text_pages):
        try:
            from pdfminer.high_level import extract_text
            full = extract_text(io.BytesIO(pdf_bytes))
            if full and full.strip():
                pages = full.split("\f")
                text_pages = [p if p is not None else "" for p in pages if p is not None]
        except Exception:
            pass

    return text_pages

DIM_TRIPLE = re.compile(r'(?P<w>\d{2,4})\s*[x×]\s*(?P<d>\d{2,4})\s*[x×]\s*(?P<h>\d{2,4})')
MODULE_WITH_TRIPLE = re.compile(r'(?P<mod>[A-Za-z0-9\-_/]+)\s*[-: ]\s*(?P<w>\d{2,4})\s*[x×]\s*(?P<d>\d{2,4})\s*[x×]\s*(?P<h>\d{2,4})')
MODULE_SPACE_TRIPLE = re.compile(r'(?P<mod>[A-Za-z0-9\-_/]+)\s+(?P<w>\d{2,4})\s*[x×]\s*(?P<d>\d{2,4})\s*[x×]\s*(?P<h>\d{2,4})')
CHAIN_LINE = re.compile(r'\b(\d{2,4})(?:\s*\+\s*|\s+)(\d{2,4})(?:(?:\s*\+\s*|\s+)(\d{2,4})){1,20}')

def section_label(line):
    t = line.upper()
    if "PLAN VIEW - BASE" in t: return "Plan Base"
    if "PLAN VIEW - WALL" in t: return "Plan Wall"
    if "PLAN VIEW - LOFT" in t: return "Plan Loft"
    if "ELEVATION A" in t and "INTERNAL" not in t: return "Elevation A"
    if "ELEVATION B" in t and "INTERNAL" not in t: return "Elevation B"
    if "ELEVATION C" in t and "INTERNAL" not in t: return "Elevation C"
    if "ELEVATION D" in t and "INTERNAL" not in t: return "Elevation D"
    if "CONSOLIDATED CABINETS LIST" in t: return "Consolidated"
    return None

def parse_pdf_text(pages):
    records = []
    current = "Unknown"
    for pageno, text in enumerate(pages, start=1):
        lines = (text or "").splitlines()
        for idx, line in enumerate(lines):
            lbl = section_label(line)
            if lbl:
                current = lbl
            for m in MODULE_WITH_TRIPLE.finditer(line):
                records.append({"page": pageno, "context": current, "type": "module_dim",
                                "module": m.group("mod"),
                                "w": int(m.group("w")), "d": int(m.group("d")), "h": int(m.group("h")),
                                "line": line.strip()})
            for m in MODULE_SPACE_TRIPLE.finditer(line):
                records.append({"page": pageno, "context": current, "type": "module_dim",
                                "module": m.group("mod"),
                                "w": int(m.group("w")), "d": int(m.group("d")), "h": int(m.group("h")),
                                "line": line.strip()})
            cm = CHAIN_LINE.search(line)
            if cm:
                import re as _re
                nums = [int(x) for x in _re.findall(r'\b\d{2,4}\b', line)]
                if len(nums) >= 3:
                    records.append({"page": pageno, "context": current, "type": "chain",
                                    "numbers": nums, "line": line.strip()})
    import pandas as pd
    return pd.DataFrame(records)

def three_way_compare(df):
    elev = df[(df["type"]=="module_dim") & (df["context"].str.startswith("Elevation"))].copy()
    cons = df[(df["type"]=="module_dim") & (df["context"]=="Consolidated")].copy()
    elev_keyed = elev.groupby("module").agg({"w":"first","d":"first","h":"first","page":"first","context":"first","line":"first"})
    cons_keyed = cons.groupby("module").agg({"w":"first","d":"first","h":"first","page":"first","context":"first","line":"first"})
    rows = []
    for mod, er in elev_keyed.iterrows():
        if mod in cons_keyed.index:
            cr = cons_keyed.loc[mod]
            remark = []
            if er["w"] != cr["w"]:
                remark.append(f"Width: Elev {er['w']} vs List {cr['w']} (Δ{er['w']-cr['w']} mm)")
            if er["d"] != cr["d"]:
                remark.append(f"Depth: Elev {er['d']} vs List {cr['d']} (Δ{er['d']-cr['d']} mm)")
            if er["h"] != cr["h"]:
                remark.append(f"Height: Elev {er['h']} vs List {cr['h']} (Δ{er['h']-cr['h']} mm)")
            if remark:
                rows.append({
                    "Check": "Elevation vs Consolidated",
                    "Module": mod,
                    "Elevation (W×D×H)": f"{er['w']}×{er['d']}×{er['h']}",
                    "Consolidated (W×D×H)": f"{cr['w']}×{cr['d']}×{cr['h']}",
                    "Mismatch": "; ".join(remark),
                    "Elevation Page": int(er["page"]),
                    "List Page": int(cr["page"])
                })
    import pandas as pd
    return pd.DataFrame(rows)

def sum_check(df):
    out = []
    for _, row in df[df["type"]=="chain"].iterrows():
        nums = row["numbers"]
        context = row["context"]
        if context in ("Plan Base","Plan Wall","Plan Loft","Elevation A","Elevation B","Elevation C","Elevation D") and len(nums) >= 4:
            parts = nums[:-1]
            total = nums[-1]
            if sum(parts) == total:
                result = "Match"
                stated_total = total
            else:
                cand = max(nums)
                result = "Mismatch" if sum(parts) != cand else "Match"
                stated_total = cand
            out.append({
                "Drawing Type": context,
                "Page": int(row["page"]),
                "Parts": "+".join(map(str, parts)),
                "Computed Sum": sum(parts),
                "Stated Total": stated_total,
                "Result": result
            })
    import pandas as pd
    return pd.DataFrame(out)

pdf = st.file_uploader("Upload docket PDF", type=["pdf"])
if pdf:
    pdf_bytes = pdf.read()
    pages = extract_text_bytes(pdf_bytes)

    if not pages or all((p or "").strip()=="" for p in pages):
        st.error("Could not extract any selectable text from this PDF. It may be a scanned image.")
        st.markdown("""
**How to fix (OCR options):**
- **Adobe Acrobat** → *Scan & OCR* → *Recognize Text* → Save as new PDF.
- **PDF24 Creator** (Windows, free) → *OCR* → Save.
- **Smallpdf/iLovePDF OCR** (online) → Upload → OCR → Download (check privacy policy).
- **Export from CAD** with text as real fonts (not outlines).
""" )
    else:
        df = parse_pdf_text(pages)
        with st.expander("Parsed records (debug)"):
            st.dataframe(df, use_container_width=True)

        issues = []

        st.subheader("❌ Elevation vs Consolidated — Mismatches")
        cmp_df = three_way_compare(df)
        if cmp_df.empty:
            st.success("No clear Elevation vs Consolidated mismatches found.")
        else:
            st.dataframe(cmp_df, use_container_width=True)
            cmp_df.insert(0, "Check Type", "Elevation vs Consolidated")
            issues.append(cmp_df)

        st.subheader("🧮 Sum Check (Plan/Elevations)")
        sum_df = sum_check(df)
        if sum_df.empty:
            st.info("No dimension chains detected for sum-check.")
        else:
            st.dataframe(sum_df, use_container_width=True)
            mism = sum_df[sum_df["Result"] == "Mismatch"].copy()
            if not mism.empty:
                mism.insert(0, "Check Type", "Sum Check")
                issues.append(mism)

        if issues:
            final = pd.concat(issues, ignore_index=True)
            st.download_button("⬇️ Download Issues (Excel)", data=final.to_excel(index=False),
                               file_name="QC_Issues.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.success("No issues detected by the current heuristics.")
