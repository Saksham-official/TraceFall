"""PDF rendering with ReportLab (ADR-020).

Every section required by PRODUCT_SPEC.md stage 13 is here, in the order an investigator
reads: what was asked, what was found, what it rests on, and what none of it means.

Two rules govern the layout:

**The tier is a word, never a colour.** `CONFIRMED`, `PROBABLE` and `UNATTRIBUTED` are
printed as text on every attribution row. A printed report may be photocopied in
greyscale, and the distinction must survive that.

**The limitations section is not an appendix to skip.** It is printed in full, and the
report is not signed, certified, or described as evidence anywhere in it.
"""

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reports.assemble import ReportData, headline, risk_headline

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
RULE = colors.HexColor("#D1D5DB")
WARN = colors.HexColor("#92400E")

_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle(
        "title", parent=_base["Title"], fontSize=20, leading=24, textColor=INK, alignment=TA_LEFT
    ),
    "h2": ParagraphStyle(
        "h2", parent=_base["Heading2"], fontSize=12.5, leading=16, spaceBefore=14, textColor=INK
    ),
    "body": ParagraphStyle("body", parent=_base["BodyText"], fontSize=9.2, leading=13.2),
    "muted": ParagraphStyle(
        "muted", parent=_base["BodyText"], fontSize=8, leading=11, textColor=MUTED
    ),
    "mono": ParagraphStyle(
        "mono", parent=_base["BodyText"], fontSize=7.6, leading=10, fontName="Courier"
    ),
    "warn": ParagraphStyle(
        "warn", parent=_base["BodyText"], fontSize=8.6, leading=12, textColor=WARN
    ),
}

TABLE_STYLE = TableStyle(
    [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
    ]
)


def render(data: ReportData, report_id: str) -> bytes:
    """Build the PDF and return its bytes, so the caller hashes exactly what it stores."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"TraceFall report {report_id}",
        author="TraceFall",
    )
    story: list[Any] = []
    _cover(story, data, report_id)
    _summary(story, data)
    _attributions(story, data)
    _risk(story, data)
    _patterns(story, data)
    _transactions(story, data)
    _sources(story, data)
    _limitations(story, data)
    _appendix(story, data)
    document.build(story, onFirstPage=_furniture, onLaterPages=_furniture)
    return buffer.getvalue()


def _furniture(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        18 * mm, 10 * mm, "TraceFall — investigative aid, not a forensic certification"
    )
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def _para(story: list[Any], text: str, style: str = "body") -> None:
    story.append(Paragraph(text, STYLES[style]))


def _heading(story: list[Any], text: str) -> None:
    story.append(Paragraph(text, STYLES["h2"]))


def _table(story: list[Any], header: list[str], rows: list[list[str]], widths: list[float]) -> None:
    if not rows:
        _para(story, "None.", "muted")
        return
    cells = [[Paragraph(h, STYLES["muted"]) for h in header]] + [
        [Paragraph(_escape(c), STYLES["mono" if _looks_like_hash(c) else "body"]) for c in row]
        for row in rows
    ]
    table = Table(cells, colWidths=widths, repeatRows=1)
    table.setStyle(TABLE_STYLE)
    story.append(table)


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _looks_like_hash(value: str) -> bool:
    return len(value) > 24 and " " not in value


def _cover(story: list[Any], data: ReportData, report_id: str) -> None:
    case = data.case
    _para(story, "Cryptocurrency Fund Flow Analysis", "title")
    _para(
        story,
        f"Case {case['case_number']} — {_escape(str(case['title']))}",
        "body",
    )
    story.append(Spacer(1, 6))
    _table(
        story,
        ["Field", "Value"],
        [
            ["Report ID", report_id],
            ["Generated", data.generated_at.strftime("%Y-%m-%d %H:%M UTC")],
            ["Analysis run", str(data.run["id"])],
            ["Run status", str(data.run["status"])],
            ["Suspect address", str(data.address["address"])],
            ["Chain", str(data.address["chain"])],
            ["Reported amount", _reported(data)],
            ["Incident date", str(case["incident_date"] or "not recorded")],
            ["NCRP reference", str(case["ncrp_reference"] or "not recorded")],
            ["FIR reference", str(case["fir_reference"] or "not recorded")],
            ["Case officer", str(case["owner"] or "not recorded")],
            ["Narrative", "Templated. No text in this report was written by a language model."],
        ],
        [45 * mm, 129 * mm],
    )
    story.append(Spacer(1, 10))
    _heading(story, "Finding")
    _para(story, _escape(headline(data)))
    story.append(Spacer(1, 4))
    _para(story, _escape(risk_headline(data)))


def _reported(data: ReportData) -> str:
    amount = data.address["reported_amount"]
    if not amount:
        return "not reported — the trace covers all value the address received"
    symbol = data.address["reported_asset_symbol"] or ""
    return f"{amount} {symbol}".strip()


def _summary(story: list[Any], data: ReportData) -> None:
    _heading(story, "1. Fund flow summary")
    summary = data.summary
    if not summary.get("traced"):
        _para(story, _escape(str(summary.get("note", "No trace was produced."))))
        return

    _table(
        story,
        ["Field", "Value"],
        [
            ["Root address", str(summary["root_address"])],
            ["Total traced (raw units)", str(summary["total_traced_raw"])],
            [
                "Anchored to victim transaction",
                str(summary["anchor_tx_hash"]) if summary["anchored"] else "No — see limitations",
            ],
            ["Addresses in trace", str(summary["node_count"])],
            ["Flows in trace", str(summary["edge_count"])],
            ["Maximum depth", str(summary["max_depth"])],
            ["Taint model", str(summary["taint_model"])],
            ["Branches not followed", str(summary["pruned_branches"])],
        ],
        [45 * mm, 129 * mm],
    )

    story.append(Spacer(1, 8))
    _para(story, "<b>Where the trace ended, and why</b>")
    _table(
        story,
        ["Address", "Reason", "Tainted (raw)"],
        [
            [str(t["address"]), str(t["reason"]), str(t["tainted_amount_raw"])]
            for t in summary["terminal_addresses"]
        ],
        [86 * mm, 48 * mm, 40 * mm],
    )

    if summary["unavailable_addresses"]:
        story.append(Spacer(1, 6))
        _para(
            story,
            "<b>Incomplete.</b> The following addresses were reached but could not be "
            "retrieved, so what left them is unknown. This is a gap in the analysis, not "
            "a finding that the funds stopped: "
            + ", ".join(_escape(a) for a in summary["unavailable_addresses"]),
            "warn",
        )
    if data.run["degradations"]:
        story.append(Spacer(1, 6))
        _para(
            story,
            f"<b>Partial analysis.</b> {len(data.run['degradations'])} stage(s) did not "
            f"complete fully. The run status is {data.run['status']}.",
            "warn",
        )


def _attributions(story: list[Any], data: ReportData) -> None:
    _heading(story, "2. Service and exchange identification")
    _para(
        story,
        "Every claim below carries exactly one tier. <b>CONFIRMED</b> means a named, dated "
        "dataset says so. <b>PROBABLE</b> is an inference from transaction behaviour and "
        "must be verified before it is acted on. <b>UNATTRIBUTED</b> means public data "
        "cannot identify the address — it does not mean the address is innocent.",
        "muted",
    )
    story.append(Spacer(1, 5))
    _table(
        story,
        ["Address", "Tier", "Entity", "Type", "Confidence"],
        [
            [
                str(a["address"]),
                str(a["tier"]),
                str(a["entity_name"] or "—"),
                str(a["entity_type"]),
                f"{a['confidence']:.2f}" if a["confidence"] is not None else "n/a",
            ]
            for a in data.attributions
        ],
        [58 * mm, 27 * mm, 35 * mm, 30 * mm, 24 * mm],
    )

    evidenced = [a for a in data.attributions if a["tier"] != "UNATTRIBUTED" and a["evidence"]]
    for attribution in evidenced:
        story.append(Spacer(1, 7))
        block: list[Any] = [
            Paragraph(
                f"<b>{_escape(str(attribution['address']))}</b> — {attribution['tier']}",
                STYLES["body"],
            )
        ]
        for item in attribution["evidence"]:
            detail = item.get("detail")
            if isinstance(detail, str):
                block.append(Paragraph(f"• {_escape(detail)}", STYLES["muted"]))
        story.append(KeepTogether(block))


def _risk(story: list[Any], data: ReportData) -> None:
    _heading(story, "3. Risk assessment")
    _para(
        story,
        "An investigative prioritisation score. <b>Not a probability of fraud and not "
        "evidence of criminal conduct.</b> Confidence is reported separately and is never "
        "folded into the score: a high score at low confidence means the data was thin, "
        "not that the finding is strong.",
        "muted",
    )
    story.append(Spacer(1, 5))
    _table(
        story,
        ["Address", "Score", "Band", "Confidence"],
        [
            [str(r["address"]), str(r["score"]), str(r["band"]), f"{r['confidence']:.2f}"]
            for r in data.risk
        ],
        [86 * mm, 24 * mm, 34 * mm, 30 * mm],
    )

    root = next((r for r in data.risk if r["address"] == data.address["address"]), None)
    if root is None:
        return
    story.append(Spacer(1, 8))
    _para(story, "<b>Signal breakdown for the suspect address</b>")
    _table(
        story,
        ["Signal", "Points", "Max", "Why"],
        [
            [
                str(s["name"]),
                f"{s['points']:.2f}",
                f"{s['weight']:.0f}",
                str(s["description"]),
            ]
            for s in root["signals"]
        ],
        [38 * mm, 16 * mm, 14 * mm, 106 * mm],
    )
    if root["not_evaluated"]:
        story.append(Spacer(1, 6))
        _para(story, "<b>Not evaluated</b> — checked for, and unavailable. Not scored as zero.")
        _table(
            story,
            ["Signal", "Reason"],
            [[str(n["name"]), str(n["reason"])] for n in root["not_evaluated"]],
            [45 * mm, 129 * mm],
        )


def _patterns(story: list[Any], data: ReportData) -> None:
    _heading(story, "4. Behavioural patterns")
    if not data.patterns:
        _para(story, "No behavioural patterns were detected in this trace.", "muted")
        return
    _para(
        story,
        "Each pattern names a <i>shape</i> in the transaction record. Every shape below "
        "also has innocent explanations, printed with it. None of these is evidence of "
        "fraud.",
        "muted",
    )
    for finding in data.patterns:
        story.append(Spacer(1, 7))
        story.append(
            KeepTogether(
                [
                    Paragraph(
                        f"<b>{finding['pattern_type']}</b> ({finding['severity']}) — "
                        f"{_escape(str(finding['subject_address']))}",
                        STYLES["body"],
                    ),
                    Paragraph(_escape(str(finding["explanation"])), STYLES["body"]),
                    Paragraph(
                        "<b>Also consistent with:</b> "
                        + _escape(str(finding["false_positive_note"])),
                        STYLES["muted"],
                    ),
                    Paragraph(
                        "Triggering transactions: "
                        + ", ".join(str(h) for h in finding["trigger_tx_hashes"][:6]),
                        STYLES["mono"],
                    ),
                ]
            )
        )


def _transactions(story: list[Any], data: ReportData) -> None:
    _heading(story, "5. Key transactions")
    _table(
        story,
        ["From", "To", "Tainted (raw)", "Transfers"],
        [
            [
                str(t["from"]),
                str(t["to"]),
                str(t["tainted_amount_raw"]),
                str(t["transfer_count"]),
            ]
            for t in data.key_transactions[:25]
        ],
        [58 * mm, 58 * mm, 36 * mm, 22 * mm],
    )


def _sources(story: list[Any], data: ReportData) -> None:
    _heading(story, "6. Data sources and retrieval")
    _table(
        story,
        ["Provider", "Requests", "First retrieved", "Last retrieved", "Cached snapshot"],
        [
            [
                str(s["provider"]),
                str(s["requests"]),
                str(s["first"]),
                str(s["last"]),
                "yes" if s.get("is_fixture") else "no",
            ]
            for s in data.sources
        ],
        [30 * mm, 20 * mm, 45 * mm, 45 * mm, 34 * mm],
    )
    story.append(Spacer(1, 6))
    _para(story, "<b>Tracing convention</b>")
    _para(story, _escape(data.tracing_convention), "muted")
    story.append(Spacer(1, 4))
    versions = ", ".join(f"{k} {v}" for k, v in sorted(data.run["engine_versions"].items()))
    _para(story, f"Engine versions: {_escape(versions)}", "muted")


def _limitations(story: list[Any], data: ReportData) -> None:
    story.append(PageBreak())
    _heading(story, "7. Limitations and disclaimer")
    for line in data.disclaimers:
        _para(story, f"• {_escape(line)}")
        story.append(Spacer(1, 3))


def _appendix(story: list[Any], data: ReportData) -> None:
    _heading(story, "8. Evidence appendix")
    _para(
        story,
        f"Every transaction hash the findings in this report rest on "
        f"({len(data.evidence)} total). Each can be verified independently on a public "
        f"block explorer.",
        "muted",
    )
    story.append(Spacer(1, 5))
    for item in data.evidence:
        _para(story, str(item["tx_hash"]), "mono")
