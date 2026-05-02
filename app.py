"""
AI Stock Analysis Agent — Axis Burgundy Private Edition
Luxury financial research interface with editorial PDF output.
"""
import streamlit as st
import sys
import os
import re
import time
import threading
import urllib.request
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from io import BytesIO

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from src.stock_crew.crew import run_stock_analysis


# ═════════════════════════════════════════════════════════
# COLOR PALETTE — Axis Burgundy Private
# ═════════════════════════════════════════════════════════
PALETTE = {
    "burgundy":     "#5B0E2D",
    "burgundy_dk":  "#3D0820",
    "burgundy_lt":  "#8B2347",
    "gold":         "#B8945F",
    "gold_dk":      "#8C6F42",
    "gold_lt":      "#D4B785",
    "ivory":        "#FAF6EE",
    "cream":        "#F2EAD6",
    "ink":          "#1F1612",
    "ink_light":    "#5C4D43",
    "sage":         "#4A6B4A",
    "sage_bg":      "#E8EDE0",
    "rust":         "#8B3A2A",
    "rust_bg":      "#F2E0DA",
    "divider":      "#D4C5A8",
}


def _ensure_fonts():
    """Load serif & mono fonts from local assets; return font name dict with fallbacks."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    # 1. Get the directory where app.py is currently located
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # 2. Build the path to your fonts folder dynamically
    FONT_DIR = os.path.join(BASE_DIR, "src", "stock_crew", "assets", "fonts")

    # 3. Define the specific fonts
    lora_regular_path = os.path.join(FONT_DIR, "Lora-Regular.ttf")
    lora_bold_path = os.path.join(FONT_DIR, "Lora-Bold.ttf")
    dejavu_sans_path = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    dejavu_bold_path = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

# Now use these variables wherever you were using the old string paths
    sources = {
        "Lora-Regular":     lora_regular_path,
        "Lora-Bold":        lora_bold_path,
        "DejaVuSans":       dejavu_sans_path,
        "DejaVuSans-Bold": dejavu_bold_path,
    }

    loaded = {}
    for name, path in sources.items():
        try:
            # Check if the file actually exists locally, then register it
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
                loaded[name] = True
            else:
                print(f"Warning: Could not find {path}")
                loaded[name] = False
        except Exception as e:
            print(f"Error loading {name}: {e}")
            loaded[name] = False

    return {
        "serif":      "Lora-Regular"     if loaded.get("Lora-Regular")    else "Times-Roman",
        "serif_bold": "Lora-Bold"        if loaded.get("Lora-Bold")       else "Times-Bold",
        "body":       "Lora-Regular"     if loaded.get("Lora-Regular")    else "Times-Roman",
        "body_bold":  "Lora-Bold"        if loaded.get("Lora-Bold")       else "Times-Bold",
        "mono":       "DejaVuSans"       if loaded.get("DejaVuSans")      else "Helvetica",
        "mono_bold":  "DejaVuSans-Bold"  if loaded.get("DejaVuSans-Bold") else "Helvetica-Bold",
        "has_lora":   loaded.get("Lora-Regular", False),
        "has_dejavu": loaded.get("DejaVuSans",   False),
    }


def _fix_rupee(text, mono_font):
    """Wrap ₹ in mono font that supports it (Lora doesn't include rupee glyph)."""
    if "₹" in text:
        text = text.replace("₹", f'<font name="{mono_font}">₹</font>')
    return text


def _parse_sections(text):
    secs, cur, buf = {}, "summary", []
    for line in text.split("\n"):
        s, lo = line.strip(), line.strip().lower()
        is_h = (
            s.startswith("#") or
            bool(re.match(r'^\d+\.', s)) or
            bool(re.match(r'^\*\*[^*]+\*\*\s*:?\s*$', s)) or
            bool(re.match(r'^\*\*[^*]+:\*\*', s))
        )
        if   is_h and "bull case"              in lo: secs[cur]="\n".join(buf); cur="bull";    buf=[]
        elif is_h and any(x in lo for x in ["bear case","risks and concern","risk and concern"]): secs[cur]="\n".join(buf); cur="bear"; buf=[]
        elif is_h and "overall recommendation" in lo: secs[cur]="\n".join(buf); cur="rec";     buf=[]
        elif is_h and any(x in lo for x in ["key metric","metric snapshot"]): secs[cur]="\n".join(buf); cur="metrics"; buf=[]
        else: buf.append(line)
    secs[cur] = "\n".join(buf)
    return secs


def _clean_md(t):
    t = re.sub(r'\*\*(.*?)\*\*', r'\1', t)
    t = re.sub(r'\*(.*?)\*',     r'\1', t)
    t = re.sub(r'#{1,4}\s*',     '',    t)
    return t.strip()


def _detect_verdict(rec_text, full_text):
    text = (rec_text + " " + full_text).upper()
    for word in ["STRONG BUY", "AVOID", "HOLD", "BUY"]:
        if (re.search(r'(?:RECOMMENDATION|VERDICT)\s*[:\-]?\s*' + word, text) or
            re.search(r'^\s*' + word + r'\s*$', text, re.MULTILINE) or
            re.search(r'\*\*\s*' + word + r'\s*\*\*', text)):
            return word
    return "HOLD"


def generate_pdf(report_text: str, ticker: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
        Table, TableStyle, KeepTogether, PageBreak, Flowable
    )

    fonts = _ensure_fonts()

    # Replace ₹ with Rs. if even DejaVu failed
    if not fonts["has_dejavu"]:
        report_text = report_text.replace("₹", "Rs.")

    C = colors.HexColor
    BURGUNDY    = C(PALETTE["burgundy"])
    BURGUNDY_DK = C(PALETTE["burgundy_dk"])
    GOLD        = C(PALETTE["gold"])
    GOLD_DK     = C(PALETTE["gold_dk"])
    GOLD_LT     = C(PALETTE["gold_lt"])
    IVORY       = C(PALETTE["ivory"])
    INK         = C(PALETTE["ink"])
    INK_LIGHT   = C(PALETTE["ink_light"])
    SAGE        = C(PALETTE["sage"])
    SAGE_BG     = C(PALETTE["sage_bg"])
    RUST        = C(PALETTE["rust"])
    RUST_BG     = C(PALETTE["rust_bg"])

    # ── Custom flowables ─────────────────────────────────
    class GoldRule(Flowable):
        def __init__(self, width):
            Flowable.__init__(self)
            self.width = width
        def wrap(self, *a): return (self.width, 8)
        def draw(self):
            c = self.canv
            c.setStrokeColor(GOLD)
            c.setLineWidth(0.5)
            c.line(0, 4, self.width/2 - 8, 4)
            c.line(self.width/2 + 8, 4, self.width, 4)
            c.setFillColor(GOLD)
            c.translate(self.width/2, 4)
            c.rotate(45)
            c.rect(-2, -2, 4, 4, stroke=0, fill=1)

    class SectionHeader(Flowable):
        def __init__(self, title, subtitle, width):
            Flowable.__init__(self)
            self.title    = title
            self.subtitle = subtitle
            self.width    = width
        def wrap(self, *a): return (self.width, 38)
        def draw(self):
            c = self.canv
            c.setFillColor(BURGUNDY)
            c.rect(0, 8, 4, 24, stroke=0, fill=1)
            c.setFillColor(BURGUNDY)
            c.setFont(fonts["serif_bold"], 14)
            c.drawString(14, 18, self.title)
            c.setFillColor(GOLD_DK)
            c.setFont(fonts["mono"], 7.5)
            c.drawString(14, 6, self.subtitle.upper())

    # ── Page decorator ───────────────────────────────────
    def page_decor(canv, doc):
        canv.saveState()
        page_w, page_h = A4
        canv.setFillColor(BURGUNDY)
        canv.rect(0, page_h - 12, page_w, 12, stroke=0, fill=1)
        canv.setFillColor(GOLD)
        canv.rect(0, page_h - 14, page_w, 2, stroke=0, fill=1)
        canv.setStrokeColor(GOLD)
        canv.setLineWidth(0.4)
        canv.line(2*cm, 1.4*cm, page_w - 2*cm, 1.4*cm)
        canv.setFillColor(INK_LIGHT)
        canv.setFont(fonts["mono"], 7)
        canv.drawString(2*cm, 1*cm, f"{ticker}  ·  INVESTMENT RESEARCH")
        canv.drawCentredString(page_w/2, 1*cm, "PRIVATE & CONFIDENTIAL")
        canv.drawRightString(page_w - 2*cm, 1*cm, f"PAGE {doc.page:02d}")
        canv.setFillColor(GOLD)
        for x in [page_w - 2.6*cm, page_w - 2.3*cm, page_w - 2*cm]:
            canv.circle(x, page_h - 0.85*cm, 1.2, stroke=0, fill=1)
        canv.restoreState()

    # ── Document ─────────────────────────────────────────
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2.5*cm,  bottomMargin=2*cm,
        title=f"{ticker} — Investment Research Report",
        author="AI Stock Analysis Agent"
    )

    def PS(name, **kw):
        from reportlab.lib.styles import ParagraphStyle as P
        return P(name, **kw)

    sty = {
        "kicker":      PS("k",  fontName=fonts["mono"],       fontSize=8.5,
                          textColor=GOLD, leading=12, alignment=TA_CENTER),
        "cover_title": PS("ct", fontName=fonts["serif_bold"], fontSize=42,
                          textColor=BURGUNDY, leading=46, alignment=TA_CENTER),
        "cover_sub":   PS("cs", fontName=fonts["serif"],      fontSize=14,
                          textColor=INK_LIGHT, leading=18, alignment=TA_CENTER),
        "cover_tk":    PS("ck2", fontName=fonts["mono_bold"], fontSize=18,
                          textColor=BURGUNDY, leading=22, alignment=TA_CENTER),
        "cover_meta":  PS("cm", fontName=fonts["mono"],       fontSize=8.5,
                          textColor=INK_LIGHT, leading=12, alignment=TA_CENTER),
        "body":        PS("bd", fontName=fonts["body"], fontSize=11,
                          textColor=INK, leading=17, alignment=TA_JUSTIFY,
                          spaceAfter=8),
        "rec_lbl":     PS("rl", fontName=fonts["mono"], fontSize=8,
                          textColor=GOLD_DK, alignment=TA_CENTER, leading=11),
        "m_lbl":       PS("ml", fontName=fonts["mono"], fontSize=7,
                          textColor=GOLD_DK, leading=10),
        "m_val":       PS("mv", fontName=fonts["serif_bold"], fontSize=14,
                          textColor=BURGUNDY, leading=17),
        "footer":      PS("ft", fontName=fonts["mono"], fontSize=7,
                          textColor=INK_LIGHT, leading=10, alignment=TA_CENTER),
    }

    # ── Story construction ───────────────────────────────
    secs       = _parse_sections(report_text)
    page_width = doc.width
    story      = []
    now        = datetime.now()

    # ─── COVER PAGE ─────────────────────────────────────
    verdict = _detect_verdict(secs.get("rec", ""), report_text)
    verdict_color = SAGE if "BUY" in verdict else RUST if "AVOID" in verdict else GOLD_DK

    story.append(Spacer(1, 80))
    story.append(Paragraph("PRIVATE  ·  CONFIDENTIAL", sty["kicker"]))
    story.append(Spacer(1, 24))
    story.append(GoldRule(page_width))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Investment", sty["cover_title"]))
    story.append(Paragraph("Research Report", sty["cover_title"]))
    story.append(Spacer(1, 14))
    story.append(GoldRule(page_width))
    story.append(Spacer(1, 28))
    story.append(Paragraph(ticker, sty["cover_tk"]))
    story.append(Paragraph("Equity  ·  India", sty["cover_sub"]))
    story.append(Spacer(1, 70))

    # Cover verdict pill
    verdict_data = [
        [Paragraph("ANALYST VERDICT", PS("vl", fontName=fonts["mono"],
                  fontSize=7, textColor=GOLD_DK, alignment=TA_CENTER, leading=10))],
        [Paragraph(verdict, PS("vw", fontName=fonts["serif_bold"], fontSize=24,
                  textColor=verdict_color, alignment=TA_CENTER, leading=28))]
    ]
    vt = Table(verdict_data, colWidths=[8*cm])
    vt.hAlign = "CENTER"
    vt.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), IVORY),
        ("BOX",          (0,0), (-1,-1), 0.5, GOLD),
        ("LINEABOVE",    (0,0), (-1,0), 1.5, BURGUNDY),
        ("TOPPADDING",   (0,0), (-1,-1), 12),
        ("BOTTOMPADDING",(0,0), (-1,-1), 14),
    ]))
    story.append(vt)

    story.append(Spacer(1, 90))
    story.append(GoldRule(page_width))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Issued  ·  {now.strftime('%d %B %Y')}", sty["cover_meta"]))
    story.append(Paragraph(f"{now.strftime('%I:%M %p IST')}", sty["cover_meta"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph("AI Stock Analysis Agent", sty["cover_meta"]))
    story.append(PageBreak())

    # ─── EXECUTIVE SUMMARY ───────────────────────────────
    summary = _clean_md(secs.get("summary", ""))
    summary = re.sub(r'(?m)^.*[Pp]osition [Ss]ummary.*$', '', summary)
    summary = re.sub(r'(?m)^.*[Cc]urrent [Pp]osition.*$', '', summary)
    summary = re.sub(r'(?m)^Investment Research Report.*$', '', summary).strip()

    if summary:
        story.append(SectionHeader("Executive Summary",
                                    "Current Position & Market Standing", page_width))
        story.append(GoldRule(page_width))
        story.append(Spacer(1, 10))
        for para in summary.split("\n\n"):
            if para.strip():
                story.append(Paragraph(_fix_rupee(para.strip(), fonts["mono"]), sty["body"]))

    # ─── KEY METRICS ─────────────────────────────────────
    metric_lines = [l.strip() for l in secs.get("metrics","").split("\n")
                    if l.strip() and ":" in l and not l.strip().startswith("#")]
    if metric_lines:
        story.append(Spacer(1, 8))
        story.append(SectionHeader("Key Metrics",
                                    "Snapshot of Critical Indicators", page_width))
        story.append(GoldRule(page_width))
        story.append(Spacer(1, 12))

        cells = []
        for line in metric_lines[:8]:
            cl = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
            cl = re.sub(r'^[-•]\s*', '', cl)
            if ":" in cl:
                lbl, _, val = cl.partition(":")
                cells.append((lbl.strip(), val.strip()))
        while len(cells) % 4 != 0:
            cells.append(("", ""))

        rows = []
        for i in range(0, len(cells), 4):
            row = []
            for j in range(4):
                if i+j < len(cells):
                    lbl, val = cells[i+j]
                    if lbl:
                        row.append([
                            Paragraph(lbl.upper(), sty["m_lbl"]),
                            Paragraph(_fix_rupee(val, fonts["mono"]), sty["m_val"])
                        ])
                    else:
                        row.append("")
            rows.append(row)

        if rows:
            col_w = page_width / 4
            tbl = Table(rows, colWidths=[col_w]*4)
            tbl.setStyle(TableStyle([
                ("BACKGROUND",   (0,0), (-1,-1), IVORY),
                ("BOX",          (0,0), (-1,-1), 0.5, GOLD),
                ("INNERGRID",    (0,0), (-1,-1), 0.3, GOLD_LT),
                ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING",   (0,0), (-1,-1), 14),
                ("BOTTOMPADDING",(0,0), (-1,-1), 14),
                ("LEFTPADDING",  (0,0), (-1,-1), 14),
                ("RIGHTPADDING", (0,0), (-1,-1), 14),
            ]))
            story.append(tbl)

    # ─── BULL CASE ───────────────────────────────────────
    bull_lines = [l.strip() for l in secs.get("bull","").split("\n")
                  if l.strip() and re.match(r'^[-*\d]', l.strip())]
    if bull_lines:
        story.append(Spacer(1, 22))
        story.append(SectionHeader("The Bull Case",
                                    "Reasons to Consider This Investment", page_width))
        story.append(GoldRule(page_width))
        story.append(Spacer(1, 10))
        for line in bull_lines:
            c = re.sub(r'^[-*\d.]+\s*', '', _clean_md(line))
            data = [[
                Paragraph("✓", PS("bm", fontName=fonts["mono_bold"], fontSize=14,
                                  textColor=SAGE, alignment=TA_CENTER, leading=18)),
                Paragraph(_fix_rupee(c, fonts["mono"]),
                          PS("bx", fontName=fonts["body"], fontSize=11,
                             textColor=INK, leading=16, alignment=TA_LEFT))
            ]]
            t = Table(data, colWidths=[1*cm, page_width - 1*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND",   (0,0), (-1,-1), SAGE_BG),
                ("LINEBEFORE",   (0,0), (0,-1), 3, SAGE),
                ("VALIGN",       (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",   (0,0), (-1,-1), 10),
                ("BOTTOMPADDING",(0,0), (-1,-1), 10),
                ("LEFTPADDING",  (0,0), (0,-1), 8),
                ("RIGHTPADDING", (0,0), (0,-1), 4),
                ("LEFTPADDING",  (1,0), (1,-1), 6),
                ("RIGHTPADDING", (1,0), (1,-1), 14),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))

    # ─── BEAR CASE ───────────────────────────────────────
    bear_lines = [l.strip() for l in secs.get("bear","").split("\n")
                  if l.strip() and re.match(r'^[-*\d]', l.strip())]
    if bear_lines:
        story.append(Spacer(1, 18))
        story.append(SectionHeader("The Bear Case",
                                    "Risks & Concerns to Monitor", page_width))
        story.append(GoldRule(page_width))
        story.append(Spacer(1, 10))
        for line in bear_lines:
            c = re.sub(r'^[-*\d.]+\s*', '', _clean_md(line))
            data = [[
                Paragraph("✕", PS("xm", fontName=fonts["mono_bold"], fontSize=14,
                                  textColor=RUST, alignment=TA_CENTER, leading=18)),
                Paragraph(_fix_rupee(c, fonts["mono"]),
                          PS("xx", fontName=fonts["body"], fontSize=11,
                             textColor=INK, leading=16, alignment=TA_LEFT))
            ]]
            t = Table(data, colWidths=[1*cm, page_width - 1*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND",   (0,0), (-1,-1), RUST_BG),
                ("LINEBEFORE",   (0,0), (0,-1), 3, RUST),
                ("VALIGN",       (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",   (0,0), (-1,-1), 10),
                ("BOTTOMPADDING",(0,0), (-1,-1), 10),
                ("LEFTPADDING",  (0,0), (0,-1), 8),
                ("RIGHTPADDING", (0,0), (0,-1), 4),
                ("LEFTPADDING",  (1,0), (1,-1), 6),
                ("RIGHTPADDING", (1,0), (1,-1), 14),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))

    # ─── FINAL RECOMMENDATION ────────────────────────────
    rec_raw = secs.get("rec", "")
    if rec_raw.strip():
        story.append(Spacer(1, 22))
        story.append(SectionHeader("Final Recommendation",
                                    "Investment Verdict & Rationale", page_width))
        story.append(GoldRule(page_width))
        story.append(Spacer(1, 18))

        verdict_color_in = SAGE if "BUY" in verdict else RUST if "AVOID" in verdict else BURGUNDY
        vd = [
            [Paragraph("◆ THE VERDICT ◆", sty["rec_lbl"])],
            [Paragraph(verdict, PS("vd2", fontName=fonts["serif_bold"], fontSize=36,
                       textColor=verdict_color_in, alignment=TA_CENTER, leading=42))]
        ]
        vt2 = Table(vd, colWidths=[page_width])
        vt2.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), IVORY),
            ("BOX",          (0,0), (-1,-1), 1, GOLD),
            ("LINEABOVE",    (0,0), (-1,0), 2, BURGUNDY),
            ("LINEBELOW",    (0,-1),(-1,-1), 2, BURGUNDY),
            ("TOPPADDING",   (0,0), (-1,-1), 14),
            ("BOTTOMPADDING",(0,0), (-1,-1), 18),
        ]))
        story.append(vt2)
        story.append(Spacer(1, 18))

        rec_body = _clean_md(rec_raw)
        rec_body = re.sub(r'(?i)overall recommendation.*?\n', '', rec_body)
        rec_body = re.sub(r'(?im)^\s*(buy|hold|avoid|strong buy)\s*$', '', rec_body).strip()
        if rec_body:
            for para in rec_body.split("\n\n"):
                if para.strip():
                    story.append(Paragraph(_fix_rupee(para.strip(), fonts["mono"]), sty["body"]))

    # ─── DISCLAIMER ──────────────────────────────────────
    story.append(Spacer(1, 30))
    story.append(GoldRule(page_width))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "AI STOCK ANALYSIS AGENT  ·  CREWAI  ·  YFINANCE  ·  SERPER  ·  OPENAI  ·  PANDAS-TA",
        sty["footer"]))
    story.append(Paragraph(
        "This report is generated by AI for informational purposes only.",
        sty["footer"]))
    story.append(Paragraph(
        "It does not constitute financial advice. Always do your own research.",
        sty["footer"]))

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    buf.seek(0)
    return buf.read()


# ═════════════════════════════════════════════════════════
# STREAMLIT UI
# ═════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AI Stock Research  ·  Burgundy Private",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ── Custom CSS — Axis Burgundy Private ───────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=Lora:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {{
    font-family: 'Lora', Georgia, serif;
}}

.stApp {{
    background: {PALETTE['ivory']};
    background-image:
        radial-gradient(at 0% 0%, rgba(184,148,95,0.04) 0%, transparent 50%),
        radial-gradient(at 100% 100%, rgba(91,14,45,0.03) 0%, transparent 50%);
    color: {PALETTE['ink']};
}}

/* Hide Streamlit chrome */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding-top: 2rem !important; padding-bottom: 2rem !important; }}

/* ═══ HERO HEADER ═══ */
.hero {{
    background: linear-gradient(135deg, {PALETTE['burgundy_dk']} 0%, {PALETTE['burgundy']} 50%, {PALETTE['burgundy_lt']} 100%);
    border-radius: 0;
    padding: 56px 64px 48px 64px;
    margin: -1rem -1rem 32px -1rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 8px 40px rgba(91,14,45,0.25);
}}
.hero::before {{
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 4px;
    background: linear-gradient(90deg, {PALETTE['gold_dk']}, {PALETTE['gold']}, {PALETTE['gold_lt']}, {PALETTE['gold']}, {PALETTE['gold_dk']});
}}
.hero::after {{
    content: '';
    position: absolute; bottom: 0; left: 0; right: 0; height: 1px;
    background: {PALETTE['gold']};
    opacity: 0.4;
}}
.hero-kicker {{
    font-family: 'JetBrains Mono', monospace;
    color: {PALETTE['gold_lt']};
    font-size: 0.72rem;
    letter-spacing: 4px;
    text-transform: uppercase;
    margin-bottom: 18px;
    display: flex; align-items: center; gap: 12px;
}}
.hero-kicker::before, .hero-kicker::after {{
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, transparent, {PALETTE['gold']}, transparent);
    max-width: 80px;
}}
.hero h1 {{
    font-family: 'Cormorant Garamond', 'Lora', serif;
    font-size: 3.2rem;
    font-weight: 600;
    color: {PALETTE['ivory']};
    margin: 0 0 8px 0;
    letter-spacing: -1px;
    line-height: 1.1;
    font-style: italic;
}}
.hero h1 .accent {{
    color: {PALETTE['gold_lt']};
    font-style: normal;
    font-weight: 700;
}}
.hero-sub {{
    font-family: 'Lora', serif;
    color: {PALETTE['cream']};
    font-size: 1rem;
    margin: 12px 0 0 0;
    opacity: 0.9;
    font-style: italic;
}}
.hero-meta {{
    font-family: 'JetBrains Mono', monospace;
    color: {PALETTE['gold_lt']};
    font-size: 0.72rem;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    margin-top: 24px;
    opacity: 0.7;
}}

/* ═══ INPUT SECTION ═══ */
.search-section {{
    background: white;
    border: 1px solid {PALETTE['divider']};
    border-radius: 4px;
    padding: 24px 32px;
    margin-bottom: 24px;
    position: relative;
    box-shadow: 0 2px 12px rgba(91,14,45,0.04);
}}
.search-section::before {{
    content: '';
    position: absolute; top: 0; left: 0; bottom: 0;
    width: 4px;
    background: {PALETTE['burgundy']};
}}
.search-label {{
    font-family: 'JetBrains Mono', monospace;
    color: {PALETTE['gold_dk']};
    font-size: 0.7rem;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    margin-bottom: 8px;
}}

.stTextInput > div > div > input {{
    background: {PALETTE['ivory']} !important;
    border: 1px solid {PALETTE['divider']} !important;
    border-radius: 2px !important;
    color: {PALETTE['ink']} !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.05rem !important;
    padding: 14px 18px !important;
    letter-spacing: 1px !important;
}}
.stTextInput > div > div > input:focus {{
    border-color: {PALETTE['burgundy']} !important;
    box-shadow: 0 0 0 2px rgba(91,14,45,0.1) !important;
    background: white !important;
}}
.stTextInput > div > div > input::placeholder {{
    color: {PALETTE['ink_light']} !important;
    font-style: italic !important;
    opacity: 0.6 !important;
}}

.stButton > button {{
    background: linear-gradient(135deg, {PALETTE['burgundy']} 0%, {PALETTE['burgundy_dk']} 100%) !important;
    color: {PALETTE['ivory']} !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    border: 1px solid {PALETTE['gold']} !important;
    border-radius: 2px !important;
    padding: 14px 28px !important;
    transition: all 0.3s ease !important;
    position: relative !important;
}}
.stButton > button:hover {{
    background: linear-gradient(135deg, {PALETTE['burgundy_dk']} 0%, {PALETTE['burgundy']} 100%) !important;
    box-shadow: 0 4px 20px rgba(91,14,45,0.3) !important;
    transform: translateY(-1px) !important;
}}
.stButton > button:disabled {{
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}}

/* Download button — gold variant */
.stDownloadButton > button {{
    background: linear-gradient(135deg, {PALETTE['gold_dk']} 0%, {PALETTE['gold']} 100%) !important;
    color: {PALETTE['burgundy_dk']} !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    border: 1px solid {PALETTE['burgundy']} !important;
    border-radius: 2px !important;
    padding: 14px 28px !important;
    transition: all 0.3s ease !important;
}}
.stDownloadButton > button:hover {{
    background: linear-gradient(135deg, {PALETTE['gold']} 0%, {PALETTE['gold_lt']} 100%) !important;
    box-shadow: 0 4px 20px rgba(184,148,95,0.4) !important;
    transform: translateY(-1px) !important;
}}

/* ═══ AGENT PIPELINE ═══ */
.agent-row {{
    background: white;
    border: 1px solid {PALETTE['divider']};
    border-left: 3px solid {PALETTE['divider']};
    border-radius: 2px;
    padding: 14px 20px;
    margin: 8px 0;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: all 0.3s ease;
}}
.agent-row.active {{
    border-left-color: {PALETTE['burgundy']};
    background: white;
    box-shadow: 0 4px 16px rgba(91,14,45,0.08);
}}
.agent-row.active .agent-name {{ color: {PALETTE['burgundy']}; }}
.agent-icon {{
    width: 36px; height: 36px;
    border-radius: 50%;
    background: {PALETTE['ivory']};
    border: 1px solid {PALETTE['gold_lt']};
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: {PALETTE['burgundy']};
}}
.agent-row.active .agent-icon {{
    background: {PALETTE['burgundy']};
    color: {PALETTE['gold_lt']};
    border-color: {PALETTE['gold']};
}}
.agent-name {{
    font-family: 'Lora', serif;
    font-weight: 600;
    color: {PALETTE['ink']};
    font-size: 0.95rem;
}}
.agent-desc {{
    font-family: 'JetBrains Mono', monospace;
    color: {PALETTE['ink_light']};
    font-size: 0.7rem;
    letter-spacing: 0.5px;
    margin-top: 2px;
}}

/* ═══ REPORT SECTIONS ═══ */
.report-section {{
    background: white;
    border: 1px solid {PALETTE['divider']};
    border-radius: 2px;
    padding: 32px 40px;
    margin: 16px 0;
    position: relative;
    box-shadow: 0 2px 12px rgba(91,14,45,0.04);
}}
.report-section::before {{
    content: '';
    position: absolute; top: 0; left: 0; bottom: 0;
    width: 3px;
    background: {PALETTE['burgundy']};
}}

.section-title {{
    font-family: 'Cormorant Garamond', 'Lora', serif;
    color: {PALETTE['burgundy']};
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0 0 4px 0;
    letter-spacing: -0.3px;
}}
.section-sub {{
    font-family: 'JetBrains Mono', monospace;
    color: {PALETTE['gold_dk']};
    font-size: 0.7rem;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid {PALETTE['divider']};
    position: relative;
}}
.section-sub::after {{
    content: '';
    position: absolute;
    bottom: -1px; left: 0; width: 60px; height: 1px;
    background: {PALETTE['burgundy']};
}}

.section-body {{
    color: {PALETTE['ink']};
    line-height: 1.85;
    font-size: 1rem;
    font-family: 'Lora', serif;
}}
.section-body b {{ color: {PALETTE['burgundy']}; font-weight: 600; }}

/* ═══ TOP METRIC CARDS ═══ */
.top-card {{
    background: white;
    border: 1px solid {PALETTE['divider']};
    border-radius: 2px;
    padding: 24px;
    text-align: center;
    position: relative;
    overflow: hidden;
    box-shadow: 0 2px 12px rgba(91,14,45,0.04);
}}
.top-card::before {{
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, {PALETTE['burgundy']}, {PALETTE['gold']});
}}
.top-card-lbl {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: {PALETTE['gold_dk']};
    text-transform: uppercase;
    letter-spacing: 2.5px;
    margin-bottom: 10px;
}}
.top-card-val {{
    font-family: 'Cormorant Garamond', 'Lora', serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: {PALETTE['burgundy']};
}}

.tk-pill {{
    display: inline-block;
    background: {PALETTE['burgundy']};
    color: {PALETTE['gold_lt']};
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    font-size: 0.95rem;
    padding: 6px 16px;
    border-radius: 2px;
    letter-spacing: 1.5px;
    border: 1px solid {PALETTE['gold']};
}}

/* ═══ BULL / BEAR ITEMS ═══ */
.bull-item {{
    background: {PALETTE['sage_bg']};
    border-left: 3px solid {PALETTE['sage']};
    border-radius: 0 2px 2px 0;
    padding: 14px 18px;
    margin: 10px 0;
    color: {PALETTE['ink']};
    font-family: 'Lora', serif;
    font-size: 0.95rem;
    line-height: 1.65;
    display: flex;
    gap: 12px;
}}
.bull-item-mark {{
    color: {PALETTE['sage']};
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 1.1rem;
    flex-shrink: 0;
}}

.bear-item {{
    background: {PALETTE['rust_bg']};
    border-left: 3px solid {PALETTE['rust']};
    border-radius: 0 2px 2px 0;
    padding: 14px 18px;
    margin: 10px 0;
    color: {PALETTE['ink']};
    font-family: 'Lora', serif;
    font-size: 0.95rem;
    line-height: 1.65;
    display: flex;
    gap: 12px;
}}
.bear-item-mark {{
    color: {PALETTE['rust']};
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 1.1rem;
    flex-shrink: 0;
}}

/* ═══ VERDICT PILL ═══ */
.verdict-frame {{
    background: linear-gradient(135deg, {PALETTE['ivory']} 0%, {PALETTE['cream']} 100%);
    border-top: 2px solid {PALETTE['burgundy']};
    border-bottom: 2px solid {PALETTE['burgundy']};
    border-left: 1px solid {PALETTE['gold']};
    border-right: 1px solid {PALETTE['gold']};
    padding: 24px;
    text-align: center;
    margin: 20px 0;
}}
.verdict-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: {PALETTE['gold_dk']};
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 12px;
}}
.verdict-word {{
    font-family: 'Cormorant Garamond', 'Lora', serif;
    font-size: 3.5rem;
    font-weight: 700;
    line-height: 1;
}}
.v-buy   {{ color: {PALETTE['sage']}; }}
.v-hold  {{ color: {PALETTE['burgundy']}; }}
.v-avoid {{ color: {PALETTE['rust']}; }}

/* ═══ KEY METRICS GRID ═══ */
.metric-cell {{
    background: {PALETTE['ivory']};
    border: 1px solid {PALETTE['gold_lt']};
    border-radius: 2px;
    padding: 18px 16px;
    text-align: left;
    min-height: 90px;
}}
.metric-cell-lbl {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    color: {PALETTE['gold_dk']};
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 8px;
}}
.metric-cell-val {{
    font-family: 'Cormorant Garamond', 'Lora', serif;
    font-size: 1.4rem;
    font-weight: 600;
    color: {PALETTE['burgundy']};
}}

/* ═══ SIDEBAR ═══ */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {PALETTE['burgundy_dk']} 0%, {PALETTE['burgundy']} 100%) !important;
    border-right: 1px solid {PALETTE['gold']} !important;
}}
[data-testid="stSidebar"] * {{ color: {PALETTE['ivory']} !important; }}

.sidebar-h {{
    font-family: 'JetBrains Mono', monospace !important;
    color: {PALETTE['gold_lt']} !important;
    font-size: 0.65rem !important;
    letter-spacing: 3px !important;
    text-transform: uppercase !important;
    padding: 16px 0 12px 0 !important;
    border-bottom: 1px solid {PALETTE['gold']} !important;
    margin-bottom: 14px !important;
    opacity: 0.9 !important;
}}

.sb-agent {{
    background: rgba(250,246,238,0.05);
    border: 1px solid rgba(212,183,133,0.2);
    border-left: 2px solid {PALETTE['gold']};
    border-radius: 2px;
    padding: 11px 14px;
    margin: 6px 0;
    display: flex; align-items: center; gap: 10px;
}}
.sb-agent-num {{
    width: 22px; height: 22px;
    border-radius: 50%;
    background: {PALETTE['gold']};
    color: {PALETTE['burgundy_dk']} !important;
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem; font-weight: 700;
    flex-shrink: 0;
}}
.sb-agent-name {{
    font-family: 'Lora', serif !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    color: {PALETTE['ivory']} !important;
}}
.sb-agent-desc {{
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.65rem !important;
    color: {PALETTE['gold_lt']} !important;
    margin-top: 2px !important;
    letter-spacing: 0.5px !important;
    opacity: 0.85 !important;
}}

.sb-ticker {{
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
    color: {PALETTE['gold_lt']} !important;
    background: rgba(250,246,238,0.05);
    border: 1px solid rgba(212,183,133,0.2);
    border-radius: 2px;
    padding: 7px 12px;
    margin: 4px 0;
    letter-spacing: 1px;
}}

.sb-tip {{
    background: rgba(212,183,133,0.08);
    border: 1px solid rgba(212,183,133,0.25);
    border-radius: 2px;
    padding: 14px 16px;
    margin-top: 20px;
    font-family: 'Lora', serif !important;
    font-size: 0.8rem !important;
    line-height: 1.7 !important;
    color: {PALETTE['cream']} !important;
    font-style: italic !important;
}}

/* ═══ PROGRESS BAR ═══ */
[data-testid="stProgress"] > div > div {{
    height: 15px !important; 
}}

[data-testid="stProgress"] > div > div > div > div {{
    background: linear-gradient(90deg, {PALETTE['burgundy']}, {PALETTE['gold']}) !important;
}}
/* ═══ EXPANDER ═══ */
.streamlit-expanderHeader {{
    font-family: 'JetBrains Mono', monospace !important;
    background: {PALETTE['ivory']} !important;
    border: 1px solid {PALETTE['divider']} !important;
    color: {PALETTE['burgundy']} !important;
    font-size: 0.8rem !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
}}

/* ═══ SUCCESS / ERROR ═══ */
.stAlert {{
    background: {PALETTE['ivory']} !important;
    border-left: 3px solid {PALETTE['burgundy']} !important;
    border-radius: 2px !important;
    font-family: 'Lora', serif !important;
    color: {PALETTE['ink']} !important;
}}

/* ═══ FOOTER ═══ */
.app-footer {{
    text-align: center;
    padding: 32px 0 12px 0;
    margin-top: 32px;
    border-top: 1px solid {PALETTE['divider']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: {PALETTE['ink_light']};
    letter-spacing: 2px;
    text-transform: uppercase;
}}
.app-footer .gold-rule {{
    width: 60px; height: 2px;
    background: {PALETTE['gold']};
    margin: 0 auto 16px auto;
}}
.app-footer .disclaimer {{
    margin-top: 12px;
    font-style: italic;
    text-transform: none;
    font-family: 'Lora', serif;
    color: {PALETTE['ink_light']};
    opacity: 0.7;
    letter-spacing: 0;
    font-size: 0.78rem;
}}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────
for k, v in [("report", None), ("ticker", None), ("running", False)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────
def get_verdict(text: str):
    text_u = text.upper()
    rec_section = ""
    if "OVERALL RECOMMENDATION" in text_u:
        rec_section = text_u.split("OVERALL RECOMMENDATION")[-1][:400]
    check = rec_section + " " + text_u
    for word in ["STRONG BUY", "AVOID", "HOLD", "BUY"]:
        if (re.search(r'(?:RECOMMENDATION|VERDICT)\s*[:\-]?\s*' + word, check) or
            re.search(r'\*\*\s*' + word + r'\s*\*\*', check) or
            re.search(r'^\s*' + word + r'\s*$', check, re.MULTILINE)):
            cls = "v-buy" if "BUY" in word else "v-avoid" if word == "AVOID" else "v-hold"
            return word, cls
    return "HOLD", "v-hold"


def parse_secs(report: str) -> dict:
    return _parse_sections(report)


def md_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*',     r'\1', text)
    text = re.sub(r'#{1,4}\s*',     '',    text)
    return text.strip()


# ═════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:8px 0 16px 0;'>
        <div style="font-family:'Cormorant Garamond',serif;font-size:1.6rem;font-weight:700;color:#FAF6EE;letter-spacing:1px;">
            <span style="color:#D4B785;">◆</span>  EQUITY RESEARCH
        </div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.62rem;color:#D4B785;letter-spacing:3px;text-transform:uppercase;margin-top:4px;opacity:0.85;">
            Intelligent Agent
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='sidebar-h'>The Pipeline</div>", unsafe_allow_html=True)

    for i, (name, desc) in enumerate([
        ("Market Data",  "Live prices · volume · range"),
        ("Fundamentals", "P/E · ROE · margins · EPS"),
        ("Sentiment",    "News · analyst ratings"),
        ("Technicals",   "RSI · MACD · Bollinger"),
        ("Synthesis",    "Bull · bear · verdict"),
    ], 1):
        st.markdown(f"""
        <div class='sb-agent'>
            <div class='sb-agent-num'>{i:02d}</div>
            <div>
                <div class='sb-agent-name'>{name}</div>
                <div class='sb-agent-desc'>{desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div class='sidebar-h'>Quick Tickers</div>", unsafe_allow_html=True)
    for t in ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",
              "AXISBANK.NS", "ICICIBANK.NS", "BAJFINANCE.NS", "SBIN.NS"]:
        st.markdown(f"<div class='sb-ticker'>{t}</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class='sb-tip'>
        Use the <b>.NS</b> suffix for NSE-listed stocks.<br>
        Each report takes approximately 60 seconds to compose.
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════
# HERO HEADER
# ═════════════════════════════════════════════════════════
st.markdown(f"""
<div class='hero'>
    <div class='hero-kicker'>◆  Private Wealth Research  ◆</div>
    <h1>Investment <span class='accent'>Intelligence</span></h1>
    <h1 style='font-size:2.4rem;margin-top:-6px;'>powered by AI</h1>
    <p class='hero-sub'>Five specialized agents. Live market data. Editorial-grade research.</p>
    <div class='hero-meta'>{datetime.now().strftime('%A · %d %B %Y · %I:%M %p IST')}</div>
</div>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════
# INPUT SECTION
# ═════════════════════════════════════════════════════════
st.markdown("""
<div style='margin-bottom:8px;'>
    <div class='search-label'>◆ Ticker Symbol</div>
</div>
""", unsafe_allow_html=True)

col_in, col_btn = st.columns([5, 1.2])
with col_in:
    ticker_input = st.text_input(
        "Stock Ticker",
        placeholder="RELIANCE.NS  ·  TCS.NS  ·  HDFCBANK.NS  ·  AXISBANK.NS",
        label_visibility="collapsed",
        key="ticker_field"
    )
with col_btn:
    go = st.button(
        "◆ COMPOSE",
        use_container_width=True,
        disabled=st.session_state.running
    )


# ═════════════════════════════════════════════════════════
# RUN ANALYSIS
# ═════════════════════════════════════════════════════════
if go:
    if not ticker_input.strip():
        st.error("Please enter a ticker symbol — e.g. RELIANCE.NS")
    else:
        tc = ticker_input.strip().upper()
        st.session_state.running = True
        st.session_state.report  = None
        st.session_state.ticker  = tc

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### ⚙️ Agent Pipeline Execution", unsafe_allow_html=True)

        # 1. Define the exact names of your stages/agents
        stages = [
            "Market Data Specialist",
            "Fundamental Analyst",
            "Sentiment Analyst",
            "Technical Analyst",
            "Senior Investment Analyst"
        ]

        # 2. Create empty containers for each progress bar
        ui_slots = {stage: st.empty() for stage in stages}

        # 3. Initialize all bars to 0% (Pending)
        for stage, slot in ui_slots.items():
            slot.progress(0, text=f"⏳ Pending: {stage}")

        # 4. Create the Callback Function
        def update_progress(stage_name: str, status: str):
            """This function will be called by your backend."""
            if stage_name in ui_slots:
                if status == "running":
                    ui_slots[stage_name].progress(50, text=f"⚙️ WORKING: {stage_name}...")
                elif status == "complete":
                    ui_slots[stage_name].progress(100, text=f"✅ COMPLETE: {stage_name}")

        try:
            # 5. Pass the callback function INTO your backend execution
            result = run_stock_analysis(tc, progress_callback=update_progress)
            
            st.session_state.report = str(result)
            st.session_state.running = False
            time.sleep(0.5)
            st.rerun()

        except Exception as e:
            st.session_state.running = False
            st.error(f"❌ Composition Failed: {e}")
# ═════════════════════════════════════════════════════════
# DISPLAY REPORT
# ═════════════════════════════════════════════════════════
if st.session_state.report and not st.session_state.running:

    report  = st.session_state.report
    sym     = st.session_state.ticker
    verdict, vcls = get_verdict(report)
    now_str = datetime.now().strftime("%d %b %Y · %I:%M %p")
    secs    = parse_secs(report)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── TOP BAR ─────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class='top-card'>
            <div class='top-card-lbl'>Subject</div>
            <div class='top-card-val'><span class='tk-pill'>{sym}</span></div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class='top-card'>
            <div class='top-card-lbl'>Composed</div>
            <div class='top-card-val' style='font-size:1.1rem'>{now_str}</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class='top-card'>
            <div class='top-card-lbl'>Verdict</div>
            <div class='top-card-val'>
                <span class='{vcls}' style='font-size:1.6rem;font-weight:700;font-style:italic;'>{verdict}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── EXECUTIVE SUMMARY ───────────────────────────────
    summary = md_html(secs.get("summary", ""))
    summary = re.sub(r'(?m)^.*[Pp]osition [Ss]ummary.*$', '', summary).strip()
    summary = re.sub(r'(?m)^.*[Cc]urrent [Pp]osition.*$', '', summary).strip()
    summary = re.sub(r'(?m)^Investment Research Report.*$', '', summary).strip()
    if summary:
        st.markdown(f"""
        <div class='report-section'>
            <div class='section-title'>Executive Summary</div>
            <div class='section-sub'>Current Position & Market Standing</div>
            <div class='section-body'>{summary}</div>
        </div>
        """, unsafe_allow_html=True)

    # ─── KEY METRICS GRID ────────────────────────────────
    metric_lines = [l.strip() for l in secs.get("metrics","").split("\n")
                    if l.strip() and ":" in l and not l.strip().startswith("#")]
    if metric_lines:
        st.markdown(f"""
        <div class='report-section' style='padding-bottom:24px'>
            <div class='section-title'>Key Metrics</div>
            <div class='section-sub'>Snapshot of Critical Indicators</div>
        """, unsafe_allow_html=True)

        rows = []
        for line in metric_lines[:8]:
            cl = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
            cl = re.sub(r'^[-•]\s*', '', cl)
            if ":" in cl:
                lbl, _, val = cl.partition(":")
                rows.append((lbl.strip(), val.strip()))

        # Render in 4-col rows
        for r_start in range(0, len(rows), 4):
            cols = st.columns(4)
            for j in range(4):
                if r_start + j < len(rows):
                    lbl, val = rows[r_start + j]
                    with cols[j]:
                        st.markdown(f"""
                        <div class='metric-cell'>
                            <div class='metric-cell-lbl'>{lbl}</div>
                            <div class='metric-cell-val'>{val}</div>
                        </div>
                        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # ─── BULL & BEAR ─────────────────────────────────────
    bull_lines = [l.strip() for l in secs.get("bull","").split("\n")
                  if l.strip() and re.match(r'^[-*\d]', l.strip())]
    bear_lines = [l.strip() for l in secs.get("bear","").split("\n")
                  if l.strip() and re.match(r'^[-*\d]', l.strip())]

    cb, cc = st.columns(2)
    with cb:
        bull_html = ""
        for line in bull_lines:
            c = re.sub(r'^[-*\d.]+\s*', '', md_html(line))
            bull_html += f"<div class='bull-item'><span class='bull-item-mark'>✓</span><span>{c}</span></div>"
        if not bull_html:
            bull_html = "<p style='color:#5C4D43;font-style:italic;font-size:0.9rem'>Not extracted — see full report below.</p>"
        st.markdown(f"""
        <div class='report-section'>
            <div class='section-title'>The Bull Case</div>
            <div class='section-sub'>Reasons to Consider</div>
            {bull_html}
        </div>
        """, unsafe_allow_html=True)

    with cc:
        bear_html = ""
        for line in bear_lines:
            c = re.sub(r'^[-*\d.]+\s*', '', md_html(line))
            bear_html += f"<div class='bear-item'><span class='bear-item-mark'>✕</span><span>{c}</span></div>"
        if not bear_html:
            bear_html = "<p style='color:#5C4D43;font-style:italic;font-size:0.9rem'>Not extracted — see full report below.</p>"
        st.markdown(f"""
        <div class='report-section'>
            <div class='section-title'>The Bear Case</div>
            <div class='section-sub'>Risks &amp; Concerns</div>
            {bear_html}
        </div>
        """, unsafe_allow_html=True)

    # ─── FINAL RECOMMENDATION ────────────────────────────
    rec_raw = secs.get("rec", "")
    rec_body = md_html(rec_raw)
    rec_body = re.sub(r'(?i)overall recommendation.*?\n', '', rec_body)
    rec_body = re.sub(r'(?im)^\s*(buy|hold|avoid|strong buy)\s*$', '', rec_body).strip()

    if rec_body:
        st.markdown(f"""
        <div class='report-section'>
            <div class='section-title'>Final Recommendation</div>
            <div class='section-sub'>Investment Verdict & Rationale</div>
            <div class='verdict-frame'>
                <div class='verdict-label'>◆ The Verdict ◆</div>
                <div class='verdict-word {vcls}'>{verdict}</div>
            </div>
            <div class='section-body' style='margin-top:8px'>{rec_body}</div>
        </div>
        """, unsafe_allow_html=True)

    # ─── RAW REPORT ──────────────────────────────────────
    with st.expander("◆ View the unabridged report"):
        st.markdown(report)

    # ─── ACTIONS ─────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    a1, a2, _ = st.columns([1.3, 1.3, 2])

    with a1:
        try:
            pdf_data = generate_pdf(report, sym)
            fname = f"{sym}_research_{datetime.now().strftime('%Y%m%d')}.pdf"
            st.download_button(
                label="◆ DOWNLOAD PDF",
                data=pdf_data,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.warning(f"PDF generation issue: {e}")

    with a2:
        if st.button("◆ NEW RESEARCH", use_container_width=True):
            st.session_state.report  = None
            st.session_state.ticker  = None
            st.rerun()

    # ─── FOOTER ──────────────────────────────────────────
    st.markdown("""
    <div class='app-footer'>
        <div class='gold-rule'></div>
        AI Stock Analysis Agent  ·  CrewAI  ·  yfinance  ·  Serper  ·  OpenAI  ·  pandas-ta
        <div class='disclaimer'>
            For informational purposes only. Not financial advice. Always conduct your own research.
        </div>
    </div>
    """, unsafe_allow_html=True)
