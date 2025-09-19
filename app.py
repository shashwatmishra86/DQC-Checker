
import io
import re
import pandas as pd
import streamlit as st
import PyPDF2

st.set_page_config(page_title="Docket QC Checker (PyPDF2 pinned)", layout="wide")
st.title("🧰 Docket QC Checker — PyPDF2 (pinned 3.0.1)")
st.caption("Text extraction via PyPDF2; includes Page 1 preview and raw text download.")

def extract_text_pages(pdf_bytes):
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages

CHAIN_LINE = re.compile(r'\b(\d{2,4})(?:\s*\+\s*|\s+)(\d{2,4})(?:(?:\s*\+\s*|\s+)(\d{2,4})){1,20}')
MODULE_WITH_TRIPLE = re.compile(r'(?P<mod>[A-Za-z0-9\-_/]+)\s*[-: ]\s*(?P<w>\d{2,4})\s*[x×]\s*(?P<d>\d{2,4})\s*[x×]\s*(?P<h>\d{2,4})')
MODULE_SPACE_TRIPLE = re.compile(r'(?P<mod>[A-Za-z0-9\-_/]+)\s+(?P<w>\d{2,4})\s*[x×]\s*(?P<d>\d{2,4})\s*[x×]\s*(?P<h>\d{2,4})')

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
        for line in lines:
            lbl = section_label(line)
            if lbl: current = lbl
            for m in MODULE_WITH_TRIPLE.finditer(line):
                records.append({"page": pageno, "context": current, "type": "module_dim",
                                "module": m.group("mod"), "w": int(m.group("w")),
                                "d": int(m.group("d")), "h": int(m.group("h")),
                                "line": line.strip()})
            for m in MODULE_SPACE_TRIPLE.finditer(line):
                records.append({"page": pageno, "context": current, "type": "module_dim",
                                "module": m.group("mod"), "w": int(m.group("w")),
                                "d": int(m.group("d")), "h": int(m.group("h")),
                                "line": line.strip()})
            cm = CHAIN_LINE.search(line)
            if cm:
                nums = [int(x) for x in re.findall(r'\b\d{2,4}\b', line)]
                if len(nums) >= 3:
                    records.append({"page": pageno, "context": current, "type": "chain",
                                    "numbers": nums, "line": line.strip()})
    return pd.DataFrame(records)

def three_way_compare(df):
    elev = df[(df["type"]=="module_dim") & (df["context"].str.startswith("Elevation"))].copy()
    cons = df[(df["type"]=="module_dim") & (df["context"]=="Consolidated")].copy()
    if elev.empty or cons.empty:
        return pd.DataFrame()
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
    return pd.DataFrame(rows)

def sum_check(df):
    out = []
    for _, row in df[df["type"]=="chain"].iterrows():
        nums = row["numbers"]
        context = row["context"]
        if context in ("Plan Base","Plan Wall","Plan Loft","Elevation A","Elevation B","Elevation C","Elevation D") and len(nums) >= 4:
            parts = nums[:-1]
            last = nums[-1]
            if sum(parts) == last:
                stated_total = last
                result = "Match"
            else:
                cand = max(nums)
                stated_total = cand
                result = "Match" if sum(parts) == cand else "Mismatch"
            out.append({
                "Drawing Type": context,
                "Page": int(row["page"]),
                "Parts": "+".join(map(str, parts)),
                "Computed Sum": sum(parts),
                "Stated Total": stated_total,
                "Result": result
            })
    return pd.DataFrame(out)

pdf = st.file_uploader("Upload docket PDF", type=["pdf"])
if pdf:
    pdf_bytes = pdf.read()
    pages = extract_text_pages(pdf_bytes)

    st.subheader("Debug: Text Extraction Preview (Page 1)")
    if not pages:
        st.error("No text extracted. The PDF may be image-only or encrypted.")
        st.stop()
    st.code((pages[0] or "")[:1500] or "[Page 1 looked empty]", language="text")

    st.download_button("Download Page 1 text (.txt)",
                       data=(pages[0] or "").encode("utf-8"),
                       file_name="page_1.txt",
                       mime="text/plain")

    df = parse_pdf_text(pages)
    with st.expander("Parsed records (debug)"):
        st.dataframe(df, use_container_width=True)

    issues = []

    st.subheader("❌ Elevation vs Consolidated — Mismatches")
    cmp_df = three_way_compare(df)
    if cmp_df.empty:
        st.success("No Elevation vs Consolidated mismatches found by module code.")
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
