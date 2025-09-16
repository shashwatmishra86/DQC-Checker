
import re
import io
import json
import pandas as pd
import streamlit as st

# --- Simple optional password gate (set STREAMLIT_PASSWORD in secrets) ---
PW = st.secrets.get("STREAMLIT_PASSWORD", None)
if PW:
    st.sidebar.subheader("Access")
    pwd = st.sidebar.text_input("Password", type="password")
    if pwd != PW:
        st.stop()

st.set_page_config(page_title="Docket QC Checker (Web)", layout="wide")
st.title("🧰 Docket QC Checker — Web")

st.caption("No data is stored on the server; files are processed in-memory only.")

# ---------------------- Rules handling ----------------------
DEFAULT_RULES = {
    "version": "1.0",
    "tolerance_mm": 0,
    "enable_checks": {
        "elevation_vs_consolidated": True,
        "sum_check": True
    },
    "sum_check_contexts": ["Plan Base","Plan Wall","Plan Loft","Elevation A","Elevation B","Elevation C","Elevation D"]
}

def merge_rules(user_rules):
    rules = DEFAULT_RULES.copy()
    if not user_rules: return rules
    rules.update(user_rules)
    if "enable_checks" in user_rules:
        rules["enable_checks"].update(user_rules["enable_checks"])
    if "sum_check_contexts" in user_rules:
        rules["sum_check_contexts"] = user_rules["sum_check_contexts"]
    return rules

rules_col1, rules_col2 = st.columns([1,1])
with rules_col1:
    rules_file = st.file_uploader("Upload rules.json (optional)", type=["json"])
with rules_col2:
    tol = st.number_input("Tolerance (mm) override", min_value=0, max_value=50, value=0, step=1)

user_rules = None
if rules_file is not None:
    try:
        user_rules = json.loads(rules_file.read().decode("utf-8"))
    except Exception as e:
        st.warning(f"Invalid rules.json: {e}")

rules = merge_rules(user_rules)
rules["tolerance_mm"] = tol  # override from UI

# ---------------------- PDF text extraction ----------------------
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
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                try:
                    text_pages.append(page.extract_text() or "")
                except Exception:
                    text_pages.append("")
        except Exception:
            text_pages = []
    return text_pages

# ---------------------- Parsers ----------------------
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
                nums = [int(x) for x in re.findall(r'\b\d{2,4}\b', line)]
                if len(nums) >= 3:
                    records.append({"page": pageno, "context": current, "type": "chain",
                                    "numbers": nums, "line": line.strip()})
    return pd.DataFrame(records)

# ---------------------- Checks ----------------------
def three_way_compare(df, tolerance=0):
    elev = df[(df["type"]=="module_dim") & (df["context"].str.startswith("Elevation"))].copy()
    cons = df[(df["type"]=="module_dim") & (df["context"]=="Consolidated")].copy()
    elev_keyed = elev.groupby("module").agg({"w":"first","d":"first","h":"first","page":"first","context":"first","line":"first"})
    cons_keyed = cons.groupby("module").agg({"w":"first","d":"first","h":"first","page":"first","context":"first","line":"first"})
    rows = []
    for mod, er in elev_keyed.iterrows():
        if mod in cons_keyed.index:
            cr = cons_keyed.loc[mod]
            remark = []
            if abs(er["w"] - cr["w"]) > tolerance:
                remark.append(f"Width: Elev {er['w']} vs List {cr['w']} (Δ{er['w']-cr['w']} mm)")
            if abs(er["d"] - cr["d"]) > tolerance:
                remark.append(f"Depth: Elev {er['d']} vs List {cr['d']} (Δ{er['d']-cr['d']} mm)")
            if abs(er["h"] - cr["h"]) > tolerance:
                remark.append(f"Height: Elev {er['h']} vs List {cr['h']} (Δ{er['h']-cr['h']} mm)")
            if remark:
                rows.append({
                    "Check": "Elevation vs Consolidated",
                    "Module": mod,
                    "Elevation (W×D×H)": f"{er['w']}×{er['d']}×{er['h']}",
                    "Consolidated (W×D×H)": f"{cr['w']}×{cr['d']}×{cr['h']}",
                    "Mismatch": "; ".join(remark),
                    "Tolerance (mm)": tolerance,
                    "Elevation Page": int(er["page"]),
                    "List Page": int(cr["page"])
                })
    return pd.DataFrame(rows)

def sum_check(df, allowed_contexts, tolerance=0):
    out = []
    for _, row in df[df["type"]=="chain"].iterrows():
        nums = row["numbers"]
        context = row["context"]
        if context in allowed_contexts and len(nums) >= 4:
            parts = nums[:-1]
            total = nums[-1]
            diff = sum(parts) - total
            if abs(diff) <= tolerance:
                out.append({"Drawing Type": context, "Page": int(row["page"]), "Parts": "+".join(map(str, parts)),
                            "Computed Sum": sum(parts), "Stated Total": total, "Δ (mm)": diff, "Result": "Match"})
            else:
                cand = max(nums)
                diff2 = sum(parts) - cand
                if abs(diff2) <= tolerance:
                    out.append({"Drawing Type": context, "Page": int(row["page"]), "Parts": "+".join(map(str, parts)),
                                "Computed Sum": sum(parts), "Stated Total": cand, "Δ (mm)": diff2, "Result": "Match"})
                else:
                    out.append({"Drawing Type": context, "Page": int(row["page"]), "Parts": "+".join(map(str, parts)),
                                "Computed Sum": sum(parts), "Stated Total": cand, "Δ (mm)": diff2, "Result": "Mismatch"})
    return pd.DataFrame(out)

# ---------------------- UI ----------------------
pdf = st.file_uploader("Upload docket PDF", type=["pdf"])
if pdf:
    pdf_bytes = pdf.read()
    pages = extract_text_bytes(pdf_bytes)
    if not pages:
        st.error("Could not extract text from the PDF. Try OCR or a different file.")
    else:
        df = parse_pdf_text(pages)
        with st.expander("Parsed records (debug)"):
            st.dataframe(df, use_container_width=True)

        issues = []
        if rules["enable_checks"].get("elevation_vs_consolidated", True):
            st.subheader("❌ Elevation vs Consolidated — Mismatches")
            cmp_df = three_way_compare(df, tolerance=rules.get("tolerance_mm", 0))
            if cmp_df.empty:
                st.success("No mismatches beyond tolerance.")
            else:
                st.dataframe(cmp_df, use_container_width=True)
                cmp_df.insert(0, "Check Type", "Elevation vs Consolidated")
                issues.append(cmp_df)

        if rules["enable_checks"].get("sum_check", True):
            st.subheader("🧮 Sum Check (Plan/Elevations)")
            sum_df = sum_check(df, rules.get("sum_check_contexts", DEFAULT_RULES["sum_check_contexts"]),
                               tolerance=rules.get("tolerance_mm", 0))
            if sum_df.empty:
                st.info("No chain lines detected for sum-check.")
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
            st.success("No issues detected by the current rules/tolerance.")
