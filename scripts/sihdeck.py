"""Small drawing layer over python-pptx for the SIH idea deck.

Not product code. Everything here exists so ``build_sih_ppt.py`` reads as layout
rather than as XML plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

# --- palette -------------------------------------------------------------
# The same colour means the same thing on every slide.
INK = RGBColor(0x25, 0x37, 0x40)  # headings
BODY = RGBColor(0x46, 0x60, 0x6C)  # body copy
MUTED = RGBColor(0x6E, 0x81, 0x8A)  # de-emphasised copy / "today"
RULE = RGBColor(0xD3, 0xDA, 0xDE)  # hairlines
PAGE = RGBColor(0xF6, 0xF8, 0xF9)  # page tint
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

BLUE = RGBColor(0x1B, 0x55, 0x7E)  # primary / structure
BLUE_T = RGBColor(0xE7, 0xEF, 0xF5)
GREEN = RGBColor(0x11, 0x7A, 0x3D)  # CONFIRMED
GREEN_T = RGBColor(0xE5, 0xF3, 0xEA)
AMBER = RGBColor(0xC8, 0x7D, 0x0E)  # PROBABLE
AMBER_T = RGBColor(0xFD, 0xF2, 0xDE)
GREY = RGBColor(0x6E, 0x81, 0x8A)  # UNATTRIBUTED
GREY_T = RGBColor(0xEF, 0xF2, 0xF4)
RED = RGBColor(0xD9, 0x55, 0x14)  # risk / gap
RED_T = RGBColor(0xFD, 0xEA, 0xDF)

FONT = "Calibri"

# --- canvas --------------------------------------------------------------
LEFT = 0.30
RIGHT = 13.03
WIDTH = RIGHT - LEFT
TOP = 1.28
BOTTOM = 6.88


@dataclass(frozen=True)
class Line:
    """One paragraph inside a text box."""

    text: str
    size: float = 9.0
    bold: bool = False
    color: RGBColor = BODY
    space_before: float = 0.0
    spacing: float = 0.92
    align: PP_ALIGN = PP_ALIGN.LEFT
    caps_spacing: int = 0  # character spacing, 1/100 pt
    lead: str = ""  # bold phrase rendered before `text`, same line
    lead_color: RGBColor | None = None  # colour of `lead`; defaults to INK


def _blank(shape) -> None:
    """No outline, and no theme shadow.

    ``shadow.inherit = False`` alone is not enough: an autoshape also carries a
    ``<p:style>`` element pointing at the theme's effect list, which LibreOffice
    honours when it renders the PDF. Dropping it is what actually removes the
    drop shadow.
    """
    shape.line.fill.background()
    shape.shadow.inherit = False
    style = shape._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style")
    if style is not None:
        shape._element.remove(style)


def rect(slide, x, y, w, h, fill, *, radius: float | None = None):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius is not None:
        s.adjustments[0] = radius
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    _blank(s)
    s.text_frame.word_wrap = True
    return s


def hairline(slide, x, y, w, color=RULE):
    return rect(slide, x, y, w, 0.012, color)


def text(slide, x, y, w, h, lines: list[Line], *, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = ln.align
        p.line_spacing = ln.spacing
        if ln.space_before:
            p.space_before = Pt(ln.space_before)
        # A bold lead-in phrase followed by lighter detail is what makes a
        # dense slide scannable: the eye catches the claim, then the evidence.
        parts = ([(ln.lead, True, ln.color)] if ln.lead else []) + [(ln.text, ln.bold, ln.color)]
        for value, bold, colour in parts:
            if not value:
                continue
            run = p.add_run()
            run.text = value
            f = run.font
            f.name = FONT
            f.size = Pt(ln.size)
            f.bold = bold
            is_lead = bold and ln.lead and value is ln.lead
            f.color.rgb = (ln.lead_color or INK) if is_lead else colour
            if ln.caps_spacing:
                run.font._rPr.set("spc", str(ln.caps_spacing))
    return box


def caption(slide, x, y, w, label: str, color=BLUE):
    """Section heading: small letterspaced caps over a hairline."""
    text(slide, x, y, w, 0.22, [Line(label.upper(), 8.5, True, color, caps_spacing=70)])
    hairline(slide, x, y + 0.235, w)
    return y + 0.32


def card(slide, x, y, w, h, tint, spine, *, radius=0.10):
    """Tinted rounded panel with a coloured spine down its left edge."""
    rect(slide, x, y, w, h, tint, radius=radius)
    rect(slide, x, y, 0.055, h, spine)


def chip(slide, x, y, w, h, label: str, fill, *, size=8.0, color=WHITE, radius=0.30):
    s = rect(slide, x, y, w, h, fill, radius=radius)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = label
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = color
    return s


def chevron(slide, x, y, size, color, *, down: bool = False):
    s = slide.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(x), Inches(y), Inches(size), Inches(size))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    if down:
        s.rotation = 90
    _blank(s)
    return s


def columns(x0: float, total: float, n: int, gap: float) -> list[tuple[float, float]]:
    w = (total - gap * (n - 1)) / n
    return [(x0 + i * (w + gap), w) for i in range(n)]


# --- template surgery ----------------------------------------------------


def drop(shape) -> None:
    shape._element.getparent().remove(shape._element)


def drop_prompt(slide) -> None:
    """Remove the template's printed prompt box.

    Its wording is re-used verbatim as this deck's section captions, so nothing
    the template prints is reworded or lost.
    """
    for shape in list(slide.shapes):
        if not shape.has_text_frame:
            continue
        t = shape.text_frame.text
        if "Proposed Solution" in t or "Technologies to be used" in t:
            drop(shape)
        elif "Analysis of the feasibility" in t or "Potential impact on the" in t:
            drop(shape)
        elif "Details / Links of the reference" in t:
            drop(shape)


def restyle_footer(slide, footer: str, team: str) -> None:
    for shape in list(slide.shapes):
        if not shape.has_text_frame:
            continue
        t = shape.text_frame.text.strip()
        if t.startswith("@SIH Idea submission"):
            _set(shape, footer, 8.5, WHITE, PP_ALIGN.CENTER)
        elif t == "Your Team Name":
            shape.fill.solid()
            shape.fill.fore_color.rgb = INK
            _blank(shape)
            _set(shape, team, 7.5, WHITE, PP_ALIGN.CENTER)


def _set(shape, value: str, size: float, color, align) -> None:
    tf = shape.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    for extra in list(tf.paragraphs[1:]):
        extra._p.getparent().remove(extra._p)
    p.alignment = align
    run = p.add_run()
    run.text = value
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = color


def delete_slide(prs, index: int) -> None:
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    rid = slides[index].get(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )
    prs.part.drop_rel(rid)
    xml_slides.remove(slides[index])


def move_shape(shape, x, y, w, h) -> None:
    shape.left, shape.top, shape.width, shape.height = (
        Inches(x),
        Inches(y),
        Inches(w),
        Inches(h),
    )


__all__ = [n for n in dir() if not n.startswith("_")]


def _emu(v: float) -> Emu:  # pragma: no cover - convenience
    return Inches(v)


# --- devices learned from the winning decks ---------------------------------


def pill(slide, x, y, w, label: str, fill=BLUE, *, size=9.5, h=0.30):
    """High-contrast section label.

    Every winning deck marks each zone of a slide with a filled label rather
    than quiet grey text. It is what lets a judge see, in one glance, which
    part of the slide answers which part of the brief.
    """
    s = rect(slide, x, y, w, h, fill, radius=0.5)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = label
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = WHITE
    run.font._rPr.set("spc", "30")
    return y + h + 0.14


def logo_row(slide, logos: list[tuple[str, str]], x, y, w, h, *, label_size=7.2):
    """A row of technology marks, each captioned. `logos` is (png path, label)."""
    n = len(logos)
    cell = w / n
    icon = min(h - 0.20, 0.40)
    for i, (path, name) in enumerate(logos):
        cx = x + i * cell
        slide.shapes.add_picture(
            path, Inches(cx + (cell - icon) / 2), Inches(y), Inches(icon), Inches(icon)
        )
        text(
            slide,
            cx,
            y + icon + 0.05,
            cell,
            0.18,
            [Line(name, label_size, False, BODY, align=PP_ALIGN.CENTER)],
        )
