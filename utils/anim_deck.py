"""Animated graph PPT — GIFs + native charts + fade-in. Open with Slideshow (F5)."""
from __future__ import annotations

import os
import tempfile
from io import BytesIO
import pandas as pd
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

GREEN = RGBColor(0x1B, 0x4D, 0x3E)
GREEN2 = RGBColor(0x15, 0x3D, 0x31)
CREAM = RGBColor(0xF3, 0xF5, 0xF4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x1F, 0x1F, 0x1F)
MUTED = RGBColor(0xD4, 0xD9, 0xD6)
GOLD = RGBColor(0xC4, 0xA3, 0x5A)

PNS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _run(p, text, size=14, bold=False, color=WHITE, font="Calibri"):
    r = p.add_run()
    r.text = str(text)
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = font
    return r


def _rect(slide, l, t, w, h, fill):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    return sh


def _tb(slide, l, t, w, h, text, size=16, bold=False, color=WHITE, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    _run(p, text, size=size, bold=bold, color=color)
    return box


def _header(slide, title):
    _rect(slide, 0, 0, 13.333, 0.78, GREEN)
    _tb(slide, 0.4, 0.18, 12.5, 0.45, title, 22, True, WHITE)


def _series(df, name_col, val_col, n=12):
    if df is None or getattr(df, "empty", True):
        return [], []
    d = df.copy()
    cols = list(d.columns)
    if name_col not in d.columns:
        name_col = cols[0]
    if val_col not in d.columns:
        # first numeric
        val_col = None
        for c in cols[1:]:
            if pd.api.types.is_numeric_dtype(d[c]) or c.lower() in ("count", "tickets", "%"):
                val_col = c
                break
        if val_col is None and len(cols) > 1:
            val_col = cols[1]
    if val_col is None:
        return [], []
    names = [str(x)[:28] for x in d[name_col].head(n).tolist()]
    vals = pd.to_numeric(d[val_col].head(n), errors="coerce").fillna(0).tolist()
    return names, [float(v) for v in vals]


def _gif_bars(labels, values, title) -> bytes | None:
    if not labels or not values:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation, PillowWriter
        import numpy as np
    except Exception:
        return None
    labels = labels[:10]
    values = values[:10]
    x = np.arange(len(labels))
    frames = 16
    fig, ax = plt.subplots(figsize=(12.4, 5.4), dpi=110)
    fig.patch.set_facecolor("#1B4D3E")

    def draw(i):
        ax.clear()
        ax.set_facecolor("#1B4D3E")
        frac = (i + 1) / frames
        h = [v * frac for v in values]
        ax.bar(x, h, color="#E8F0EC", edgecolor="#C4A35A", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha="right", color="white", fontsize=9)
        ax.tick_params(colors="white")
        ax.set_ylim(0, max(values) * 1.18 if max(values) else 1)
        ax.set_title(title, color="white", fontsize=14, pad=8, fontweight="bold")
        for spine in ax.spines.values():
            spine.set_color("#2D6A4F")
        ax.yaxis.grid(True, color="#2D6A4F", alpha=0.5)
        ax.set_axisbelow(True)

    anim = FuncAnimation(fig, draw, frames=frames, interval=90)
    fd, path = tempfile.mkstemp(suffix=".gif")
    os.close(fd)
    try:
        anim.save(path, writer=PillowWriter(fps=10))
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        plt.close(fig)
        try:
            os.remove(path)
        except Exception:
            pass


def _gif_line(labels, values, title) -> bytes | None:
    if not labels or not values:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation, PillowWriter
        import numpy as np
    except Exception:
        return None
    if len(values) > 28:
        idx = np.linspace(0, len(values) - 1, 28).astype(int)
        labels = [labels[i] for i in idx]
        values = [values[i] for i in idx]
    frames = max(len(values), 8)
    fig, ax = plt.subplots(figsize=(12.4, 5.4), dpi=110)
    fig.patch.set_facecolor("#1B4D3E")
    xs = list(range(len(values)))

    def draw(i):
        ax.clear()
        ax.set_facecolor("#1B4D3E")
        k = min(i + 1, len(values))
        ax.fill_between(xs[:k], values[:k], color="#2D6A4F", alpha=0.55)
        ax.plot(xs[:k], values[:k], color="#E8F0EC", lw=2.6, marker="o", ms=4)
        step = max(1, len(labels) // 8)
        ax.set_xticks(xs[::step])
        ax.set_xticklabels([str(labels[j])[:10] for j in xs[::step]], rotation=25, ha="right", color="white", fontsize=8)
        ax.tick_params(colors="white")
        ax.set_xlim(0, max(len(values) - 1, 1))
        ax.set_ylim(0, max(values) * 1.2 if max(values) else 1)
        ax.set_title(title, color="white", fontsize=14, pad=8, fontweight="bold")
        for spine in ax.spines.values():
            spine.set_color("#2D6A4F")
        ax.yaxis.grid(True, color="#2D6A4F", alpha=0.5)
        ax.set_axisbelow(True)

    anim = FuncAnimation(fig, draw, frames=frames, interval=120)
    fd, path = tempfile.mkstemp(suffix=".gif")
    os.close(fd)
    try:
        anim.save(path, writer=PillowWriter(fps=8))
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        plt.close(fig)
        try:
            os.remove(path)
        except Exception:
            pass


def _add_gif(slide, data: bytes, l, t, w, h):
    if not data:
        return None
    return slide.shapes.add_picture(BytesIO(data), Inches(l), Inches(t), Inches(w), Inches(h))


def _add_chart(slide, kind, cats, vals, series_name, l, t, w, h):
    if not cats or not vals:
        return None
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series(series_name, vals)
    ctype = XL_CHART_TYPE.LINE if kind == "line" else XL_CHART_TYPE.COLUMN_CLUSTERED
    gf = slide.shapes.add_chart(ctype, Inches(l), Inches(t), Inches(w), Inches(h), cd)
    chart = gf.chart
    try:
        chart.has_legend = False
        plot = chart.plots[0]
        plot.has_data_labels = False
        s = chart.series[0]
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = GREEN
        if kind == "line":
            s.format.line.color.rgb = GREEN
    except Exception:
        pass
    return gf


def _fade_transition(slide):
    sld = slide._element
    for old in list(sld):
        if old.tag == qn("p:transition"):
            sld.remove(old)
    tr = etree.SubElement(sld, qn("p:transition"))
    tr.set("spd", "med")
    etree.SubElement(tr, qn("p:fade"))


def _appear_shapes(slide, skip=2):
    """Sequential fade-in (after previous) so Slideshow F5 animates."""
    ids = []
    for sh in slide.shapes:
        try:
            ids.append(int(sh.shape_id))
        except Exception:
            continue
    anim = ids[skip:] if len(ids) > skip else ids
    if not anim:
        return
    sld = slide._element
    for old in list(sld):
        if old.tag == qn("p:timing"):
            sld.remove(old)

    def el(tag, **attrs):
        node = etree.Element(qn(tag))
        for k, v in attrs.items():
            node.set(k, str(v))
        return node

    timing = el("p:timing")
    tnLst = el("p:tnLst")
    timing.append(tnLst)
    par_root = el("p:par")
    tnLst.append(par_root)
    cTn1 = el("p:cTn", id="1", dur="indefinite", restart="never", nodeType="tmRoot")
    par_root.append(cTn1)
    child1 = el("p:childTnLst")
    cTn1.append(child1)
    seq = el("p:seq", concurrent="true", nextAc="seek")
    child1.append(seq)
    cTn2 = el("p:cTn", id="2", restart="whenNotActive", fill="hold", evtFilter="cancelBubble", nodeType="mainSeq")
    seq.append(cTn2)
    child2 = el("p:childTnLst")
    cTn2.append(child2)

    nid = 3
    for i, sid in enumerate(anim):
        par = el("p:par")
        child2.append(par)
        cTn = el("p:cTn", id=str(nid), fill="hold")
        nid += 1
        par.append(cTn)
        st = el("p:stCondLst")
        cTn.append(st)
        delay = "0" if i == 0 else "400"
        st.append(el("p:cond", delay=delay))
        inner = el("p:childTnLst")
        cTn.append(inner)
        par2 = el("p:par")
        inner.append(par2)
        cTnB = el("p:cTn", id=str(nid), fill="hold")
        nid += 1
        par2.append(cTnB)
        st2 = el("p:stCondLst")
        cTnB.append(st2)
        st2.append(el("p:cond", delay="0"))
        ch = el("p:childTnLst")
        cTnB.append(ch)
        anim_el = el("p:animEffect", transition="in", filter="fade")
        ch.append(anim_el)
        cBhv = el("p:cBhv")
        anim_el.append(cBhv)
        cTnC = el("p:cTn", id=str(nid), dur="500")
        nid += 1
        cBhv.append(cTnC)
        tgt = el("p:tgtEl")
        cBhv.append(tgt)
        spTgt = el("p:spTgt", spid=str(sid))
        tgt.append(spTgt)

    prev = el("p:prevCondLst")
    seq.append(prev)
    prev.append(el("p:cond", evt="onPrev", delay="0"))
    nxt = el("p:nextCondLst")
    seq.append(nxt)
    nxt.append(el("p:cond", evt="onNext", delay="0"))
    sld.append(timing)


def build_animated_pptx(
    *,
    isp="ISP",
    rng="",
    kpis=None,
    class_df=None,
    daily_df=None,
    state_df=None,
    sla_df=None,
    site_df=None,
):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # Cover
    s = prs.slides.add_slide(blank)
    _rect(s, 0, 0, 13.333, 7.5, GREEN2)
    _rect(s, 0, 0, 0.16, 7.5, GOLD)
    _tb(s, 0.7, 1.7, 12, 0.35, "XTRNATE  •  ANIMATED PERFORMANCE DECK", 14, True, GOLD)
    _tb(s, 0.7, 2.2, 12, 1.0, f"{isp}", 36, True, WHITE)
    _tb(s, 0.7, 3.3, 12, 0.45, "Animated graphs  •  open with Slideshow (F5)", 18, False, MUTED)
    _tb(s, 0.7, 3.85, 12, 0.4, rng, 16, False, WHITE)
    _tb(s, 0.7, 6.5, 12, 0.3, "Confidential  |  Partner review", 12, False, MUTED)
    _fade_transition(s)

    # KPI
    s = prs.slides.add_slide(blank)
    _header(s, f"{isp}  |  Snapshot")
    cards = kpis or []
    colors = [GREEN, RGBColor(0x2D, 0x6A, 0x4F), RGBColor(0x14, 0x53, 0x2D), RGBColor(0x3F, 0x5E, 0x56), RGBColor(0xB4, 0x53, 0x09)]
    for i, item in enumerate(cards[:5]):
        lab, val = item[0], item[1]
        left = 0.4 + i * 2.56
        _rect(s, left, 1.4, 2.4, 1.7, colors[i % len(colors)])
        _tb(s, left + 0.08, 1.52, 2.24, 0.35, str(lab), 11, True, MUTED, PP_ALIGN.CENTER)
        _tb(s, left + 0.08, 1.95, 2.24, 0.8, str(val), 26, True, WHITE, PP_ALIGN.CENTER)
    _tb(s, 0.5, 3.5, 12, 0.4, "F5 dabao — cards fade-in. Next slides pe graphs grow.", 14, False, INK)
    _fade_transition(s)
    _appear_shapes(s, skip=1)

    # Daily GIF + native chart
    d_names, d_vals = [], []
    if daily_df is not None and not daily_df.empty:
        cols = list(daily_df.columns)
        date_c = cols[0]
        val_c = cols[1] if len(cols) > 1 else cols[0]
        for c in cols:
            cl = str(c).lower()
            if "date" in cl or "day" in cl:
                date_c = c
            if cl in ("count", "tickets", "ticket"):
                val_c = c
        tmp = daily_df.copy()
        tmp["_d"] = tmp[date_c].astype(str).str.slice(0, 10)
        tmp["_v"] = pd.to_numeric(tmp[val_c], errors="coerce").fillna(0)
        d_names = tmp["_d"].tolist()
        d_vals = tmp["_v"].astype(float).tolist()
    s = prs.slides.add_slide(blank)
    _header(s, "Daily tickets  •  animated")
    gif = _gif_line(d_names, d_vals, "Daily ticket count")
    if gif:
        _add_gif(s, gif, 0.35, 1.05, 12.6, 5.9)
    else:
        _add_chart(s, "line", d_names[-18:], d_vals[-18:], "Tickets", 0.4, 1.15, 12.5, 5.7)
        _tb(s, 0.5, 6.9, 12, 0.3, "GIF skip — native chart (edit animation in PowerPoint).", 11, False, INK)
    _fade_transition(s)

    # Classification bars
    c_names, c_vals = _series(class_df, class_df.columns[0] if class_df is not None and len(class_df.columns) else "c", "Count")
    s = prs.slides.add_slide(blank)
    _header(s, "Outage classification  •  bars grow")
    gif = _gif_bars(c_names, c_vals, "Tickets by outage class")
    if gif:
        _add_gif(s, gif, 0.35, 1.05, 12.6, 5.9)
    else:
        _add_chart(s, "bar", c_names, c_vals, "Tickets", 0.4, 1.15, 12.5, 5.7)
    _fade_transition(s)

    # State
    st_names, st_vals = _series(state_df, state_df.columns[0] if state_df is not None and len(getattr(state_df, "columns", [])) else "State", "Count")
    s = prs.slides.add_slide(blank)
    _header(s, "State-wise outage  •  bars grow")
    gif = _gif_bars(st_names, st_vals, "Tickets by state")
    if gif:
        _add_gif(s, gif, 0.35, 1.05, 12.6, 5.9)
    else:
        _add_chart(s, "bar", st_names, st_vals, "Tickets", 0.4, 1.15, 12.5, 5.7)
    _fade_transition(s)

    # SLA
    if sla_df is not None and not sla_df.empty:
        s = prs.slides.add_slide(blank)
        _header(s, "SLA buckets")
        # pick first numeric data row as categories from columns except first
        cols = [c for c in sla_df.columns if str(c).lower() not in ("month", "sla bucket", "band")]
        if "Grand Total" in list(sla_df.iloc[:, 0].astype(str)) or "TOTAL" in list(sla_df.iloc[:, 0].astype(str).str.upper()):
            row = sla_df.iloc[-1]
            names, vals = [], []
            for c in sla_df.columns[1:]:
                v = pd.to_numeric(row[c], errors="coerce")
                if pd.notna(v):
                    names.append(str(c)[:18])
                    vals.append(float(v))
            gif = _gif_bars(names[:8], vals[:8], "SLA mix (total)")
            if gif:
                _add_gif(s, gif, 0.35, 1.05, 12.6, 5.9)
            else:
                _add_chart(s, "bar", names[:8], vals[:8], "Tickets", 0.4, 1.15, 12.5, 5.7)
        else:
            names, vals = _series(sla_df, sla_df.columns[0], sla_df.columns[1] if len(sla_df.columns) > 1 else sla_df.columns[0])
            gif = _gif_bars(names, vals, "SLA")
            if gif:
                _add_gif(s, gif, 0.35, 1.05, 12.6, 5.9)
        _fade_transition(s)

    # Native editable charts slide
    s = prs.slides.add_slide(blank)
    _header(s, "Editable PowerPoint charts  (right-click → Animate)")
    _add_chart(s, "bar", c_names[:8], c_vals[:8], "Class", 0.35, 1.1, 6.2, 5.6)
    _add_chart(s, "line", d_names[-14:], d_vals[-14:], "Daily", 6.8, 1.1, 6.1, 5.6)
    _fade_transition(s)
    _appear_shapes(s, skip=1)

    # Sites table-ish chart
    if site_df is not None and not site_df.empty:
        s = prs.slides.add_slide(blank)
        _header(s, "Top sites")
        sn, sv = _series(site_df, site_df.columns[0], site_df.columns[1] if len(site_df.columns) > 1 else site_df.columns[0], n=10)
        gif = _gif_bars(sn, sv, "Top sites by tickets")
        if gif:
            _add_gif(s, gif, 0.35, 1.05, 12.6, 5.9)
        else:
            _add_chart(s, "bar", sn, sv, "Tickets", 0.4, 1.15, 12.5, 5.7)
        _fade_transition(s)

    s = prs.slides.add_slide(blank)
    _rect(s, 0, 0, 13.333, 7.5, GREEN2)
    _tb(s, 0.7, 2.4, 12, 0.5, "Play in PowerPoint  →  Slide Show  →  From Beginning (F5)", 22, True, WHITE)
    _tb(s, 0.7, 3.2, 12, 0.8, "GIF slides auto-play the graph. KPI + chart slides fade in.\nCharts slide ko PowerPoint mein extra animation de sakte ho.", 16, False, MUTED)
    _fade_transition(s)

    out = BytesIO()
    prs.save(out)
    return out.getvalue()
