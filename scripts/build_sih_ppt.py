#!/usr/bin/env python
"""Build the SIH 2026 idea presentation for TraceFall (PS SIH26183).

Starts from the official SIH template so the masters, logos, footers and title
styling are the ministry's own, then lays our content into the empty band on
each slide.

Two structural rules, both taken from decks that actually won:
  * every zone of a slide carries a filled label naming which part of the brief
    it answers, in the template's own printed wording;
  * "IDEA TITLE" on slide 2 is a placeholder for the idea's title, so it gets
    replaced with ours — as the 2024 and 2025 NTRO winners both did.

    python scripts/build_sih_ppt.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Pt
from sihdeck import (
    AMBER,
    AMBER_T,
    BLUE,
    BLUE_T,
    BODY,
    FONT,
    GREEN,
    GREEN_T,
    GREY,
    GREY_T,
    INK,
    LEFT,
    MUTED,
    PAGE,
    RED,
    RED_T,
    RIGHT,
    RULE,
    WHITE,
    WIDTH,
    Line,
    card,
    chevron,
    chip,
    columns,
    delete_slide,
    drop,
    drop_prompt,
    hairline,
    move_shape,
    pill,
    rect,
    restyle_footer,
    text,
)

DESK = Path.home() / "Desktop" / "Hackathon PPTs"
TEMPLATE = DESK / "SIH2026-IDEA-Presentation-Format.pptx"
OUT = DESK / "SIH2026-PS26183-TraceFall.pptx"

TEAM = "«Team Name»"
FOOTER = "SIH 2026  |  PS SIH26183 — TraceFall"
IDEA_TITLE = "TraceFall — Which Exchange Received the Money?"

PS_TITLE = (
    "Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from "
    "Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics"
)


def set_title(slide, value: str) -> None:
    """`IDEA TITLE` is the template asking for the idea's title. Give it one."""
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text_frame.text.strip() == "IDEA TITLE":
            move_shape(shape, 1.90, 0.06, 8.60, 1.14)
            for para in shape.text_frame.paragraphs:
                for i, r in enumerate(para.runs):
                    r.text = value if i == 0 else ""
                    r.font.size = Pt(27.0)


# --------------------------------------------------------------------------
# Slide 1 — TITLE PAGE
# --------------------------------------------------------------------------
def slide1(s) -> None:
    """Template layout, kept as the ministry drew it: the big centred TITLE PAGE
    heading, then the fields at reading size rather than caption size."""
    for shape in list(s.shapes):
        if shape.has_text_frame and "Problem Statement ID" in shape.text_frame.text:
            drop(shape)

    fields = [
        ("Problem Statement ID", "SIH26183"),
        ("Problem Statement Title", PS_TITLE),
        ("Theme", "Blockchain & Cybersecurity"),
        ("PS Category", "Software"),
        ("Organisation", "Ministry of Home Affairs"),
        ("Team ID", "«to be allotted»"),
        ("Team Name (Registered on portal)", TEAM),
        ("Institute", "Panipat Institute of Engineering and Technology"),
    ]
    text(
        s,
        0.36,
        1.86,
        6.40,
        3.40,
        [
            Line(
                value,
                13.0,
                False,
                INK,
                space_before=0 if i == 0 else 7.0,
                spacing=0.96,
                lead=f"{label} \u2013  ",
                lead_color=BLUE,
            )
            for i, (label, value) in enumerate(fields)
        ],
    )

    card(s, 0.36, 5.44, 6.40, 1.40, BLUE_T, BLUE)
    text(
        s,
        0.60,
        5.56,
        6.00,
        1.20,
        [
            Line("OUR SOLUTION", 10.5, True, BLUE, caps_spacing=70),
            Line("TraceFall", 22.0, True, INK, space_before=2.0, spacing=0.92),
            Line(
                "The address names no institution. The money does.",
                12.0,
                False,
                BODY,
                space_before=4.0,
            ),
        ],
    )


# --------------------------------------------------------------------------
# Slide 2 — IDEA TITLE
# --------------------------------------------------------------------------
STEPS = [
    (
        "RETRIEVE",
        "We pull the transactions from public blockchain APIs. Every raw reply is "
        "hashed and time-stamped as evidence.",
    ),
    (
        "NORMALIZE",
        "TRON and Ethereum are turned into one common format — including the "
        "internal transfers most tracers miss.",
    ),
    (
        "TRACE",
        "We follow the money hop by hop. Each address passes on only the victim's "
        "share of what left it, never more.",
    ),
    (
        "GRAPH + PATTERNS",
        "Six detectors spot splitting, pooling, fast layering and peel chains.",
    ),
    (
        "ATTRIBUTE",
        "We name the exchange behind a deposit address, with a tier, a confidence "
        "and the evidence for it.",
    ),
    (
        "SCORE + REPORT",
        "19 risk signals, listed one by one, and a PDF case file with every "
        "transaction hash in it.",
    ),
]

COMPARE = [
    (
        "An address names nobody.",
        " A bank account number tells you the bank. A wallet address tells you nothing.",
        "Behaviour names it.",
        " An address that collects from many strangers and sweeps it onward is a deposit address.",
    ),
    (
        "Two or three hops, by hand.",
        " The money splits faster than a person can follow it.",
        "Every branch, automatically.",
        " The victim's share is carried correctly through each hop.",
    ),
    (
        "\u201cProbably Binance.\u201d",
        " A guess, with nothing behind it.",
        "A tier and its evidence.",
        " CONFIRMED, PROBABLE or UNATTRIBUTED \u2014 never rounded up to certainty.",
    ),
    (
        "6\u201312 hours, usually \u201cunknown\u201d.",
        "  Long after the money has moved on.  (field estimate)",
        "About 90 seconds on cached data.",
        " An evidenced answer to check, not a browser to click through.",
    ),
]

UNIQUE = [
    (
        BLUE,
        BLUE_T,
        "THE THREE TIERS CAN NEVER BE MIXED UP",
        "The database itself rejects any claim that is not CONFIRMED, PROBABLE or UNATTRIBUTED.",
    ),
    (
        AMBER,
        AMBER_T,
        "CONFIDENCE IS ONLY AS STRONG AS ITS WEAKEST LINK",
        "0.90 deposit \u00d7 0.80 exchange = 0.72. Never higher than that, and never above 0.95.",
    ),
    (
        GREY,
        GREY_T,
        "SEVEN NAMED REASONS A TRACE STOPS",
        "\u201cWe could not look further\u201d is never reported as \u201cthe money stopped here\u201d.",
    ),
    (
        GREEN,
        GREEN_T,
        "EVERY DETECTOR LISTS ITS OWN FALSE ALARMS",
        "A detector that cannot name an innocent explanation is not allowed to run.",
    ),
]


def slide2(s) -> None:
    set_title(s, IDEA_TITLE)

    rect(s, LEFT, 1.24, WIDTH, 0.52, PAGE)
    rect(s, LEFT, 1.24, 0.07, 0.52, BLUE)
    text(
        s,
        0.54,
        1.24,
        12.30,
        0.52,
        [
            Line(
                "A victim's wallet address goes in; the exchange that must receive "
                "the freeze request comes out, with the evidence attached.",
                14.0,
                True,
                INK,
            )
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )

    y = pill(
        s,
        LEFT,
        1.86,
        9.40,
        "PROPOSED SOLUTION (DESCRIBE YOUR IDEA/SOLUTION/PROTOTYPE)  \u00b7  "
        "DETAILED EXPLANATION OF THE PROPOSED SOLUTION",
        BLUE,
        size=9.0,
        h=0.29,
    )

    for i, ((x, w), (name, blurb)) in enumerate(zip(columns(LEFT, WIDTH, 6, 0.28), STEPS)):
        card(s, x, y, w, 1.24, BLUE_T, BLUE)
        chip(s, x + 0.14, y + 0.11, 0.36, 0.25, f"0{i + 1}", BLUE, size=8.0, radius=0.25)
        text(
            s,
            x + 0.56,
            y + 0.13,
            w - 0.66,
            0.24,
            [Line(name, 8.8, True, BLUE, caps_spacing=20)],
        )
        text(s, x + 0.16, y + 0.44, w - 0.32, 0.74, [Line(blurb, 9.0, False, BODY)])
        if i < 5:
            chevron(s, x + w + 0.05, y + 0.52, 0.19, RULE)

    lw, rw = 7.55, 4.98
    rx = LEFT + lw + 0.20
    ly = pill(s, LEFT, 3.62, 3.60, "HOW IT ADDRESSES THE PROBLEM", RED, size=9.0, h=0.29)
    pill(
        s,
        rx,
        3.62,
        4.60,
        "INNOVATION AND UNIQUENESS OF THE SOLUTION",
        GREEN,
        size=9.0,
        h=0.29,
    )

    for x, w, label, ink, tint in [
        (LEFT, 3.62, "AN INVESTIGATOR TODAY", GREY, GREY_T),
        (LEFT + 3.72, 3.83, "WITH TRACEFALL", BLUE, BLUE_T),
    ]:
        rect(s, x, ly, w, 0.26, tint)
        text(
            s,
            x + 0.10,
            ly,
            w - 0.20,
            0.26,
            [Line(label, 8.2, True, ink, caps_spacing=60)],
            anchor=MSO_ANCHOR.MIDDLE,
        )

    row_y = ly + 0.30
    for lead_a, rest_a, lead_b, rest_b in COMPARE:
        h = 0.52
        rect(s, LEFT, row_y, 3.62, h, PAGE)
        rect(s, LEFT + 3.72, row_y, 3.83, h, BLUE_T)
        text(
            s,
            LEFT + 0.12,
            row_y,
            3.38,
            h,
            [Line(rest_a, 9.0, False, MUTED, lead=lead_a)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(
            s,
            LEFT + 3.84,
            row_y,
            3.59,
            h,
            [Line(rest_b, 9.0, False, BODY, lead=lead_b)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        row_y += h + 0.05

    cy = ly + 0.30
    for i, (ink, tint, title, blurb) in enumerate(UNIQUE):
        card(s, rx, cy, rw, 0.52, tint, ink)
        chip(s, rx + 0.13, cy + 0.10, 0.34, 0.23, f"0{i + 1}", ink, size=7.5, radius=0.25)
        text(
            s,
            rx + 0.53,
            cy,
            rw - 0.68,
            0.52,
            [
                Line(title, 8.4, True, ink, caps_spacing=20),
                Line(blurb, 8.4, False, BODY, space_before=1.5),
            ],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        cy += 0.57

    rect(s, LEFT, 6.62, lw, 0.28, PAGE)
    lx = LEFT
    for ink, name, meaning in [
        (GREEN, "CONFIRMED", "in a published dataset"),
        (AMBER, "PROBABLE", "worked out, with a confidence"),
        (GREY, "UNATTRIBUTED", "we do not know, and we say so"),
    ]:
        rect(s, lx + 0.14, 6.705, 0.10, 0.10, ink)
        text(
            s,
            lx + 0.30,
            6.62,
            2.30,
            0.28,
            [Line(f" {meaning}", 8.2, False, BODY, lead=name)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        lx += 2.50


# --------------------------------------------------------------------------
# Slide 3 — TECHNICAL APPROACH
# --------------------------------------------------------------------------
LANES = [
    (
        "INPUT",
        "The suspect address, as the victim reported it  \u00b7  the amount and the time, "
        "used to anchor the right transfer  \u00b7  the chain is worked out from the "
        "address itself",
    ),
    (
        "RETRIEVE & NORMALIZE",
        "Rate-limited, retried, switched between providers  \u00b7  every raw reply hashed "
        "with SHA-256 and kept  \u00b7  TRON and Ethereum reduced to one Transfer model",
    ),
    (
        "ANALYSE",
        "The trace runs in exact fractions with five stop conditions  \u00b7  the graph is "
        "built in memory and chokepoints found  \u00b7  six pattern detectors  \u00b7  "
        "deposit-address score",
    ),
    (
        "OUTPUT",
        "The exchange named, with its tier and its evidence  \u00b7  19 risk signals listed "
        "one by one  \u00b7  a PDF case file  \u00b7  anything incomplete comes back marked "
        "PARTIAL",
    ),
]

SIGNALS = [
    ("Sweeps to one place", "0.30"),
    ("Keeps almost nothing", "0.20"),
    ("Forwards within the hour", "0.15"),
    ("Three or more senders", "0.15"),
    ("One or two destinations", "0.10"),
    ("Never acts on its own", "0.10"),
]

CHAIN = [
    ("RAW RESPONSE", "stored, SHA-256"),
    ("TRANSFER", "one canonical row"),
    ("TRACE EDGE", "with its share"),
    ("ATTRIBUTION", "tier + evidence"),
    ("PDF APPENDIX", "hash + fetch time"),
]

STACK = [
    ("Frontend", "React \u00b7 TypeScript \u00b7 Vite \u00b7 Tailwind \u00b7 Cytoscape.js"),
    ("Backend", "Python 3.12 \u00b7 FastAPI \u00b7 SQLAlchemy \u00b7 Pydantic"),
    ("Data", "PostgreSQL 16 \u00b7 Redis 7"),
    ("Chain data", "TronGrid \u00b7 TronScan \u00b7 Blockscout \u00b7 Etherscan"),
    ("Analytics & AI", "NetworkX \u00b7 LightGBM + SHAP (optional)"),
    ("Reports & tests", "ReportLab \u00b7 pytest \u00b7 Playwright"),
]

BUILT = [
    ("Full pipeline runs:", " retrieval \u2192 tracing \u2192 graph \u2192 patterns \u2192 attribution \u2192 risk \u2192 PDF"),
    ("28 REST endpoints,", " and a workspace with seven tabs and an interactive fund-flow graph"),
    ("435 backend and 47 frontend tests", " pass with no network access at all"),
    ("94 source files,", " clean under ruff and mypy strict"),
    ("Append-only audit log", " and evidence store, enforced by the database itself"),
    ("Security headers", " and per-IP rate limiting on every response"),
    ("Not claimed:", " the ML classifier is not built, and sign-in is single-factor"),
]


def slide3(s) -> None:
    pill(
        s,
        LEFT,
        1.28,
        7.20,
        "METHODOLOGY AND PROCESS FOR IMPLEMENTATION (FLOW CHARTS/IMAGES/ WORKING PROTOTYPE)",
        BLUE,
        size=8.6,
        h=0.29,
    )
    pill(s, 8.05, 1.28, 4.98, "TECHNOLOGIES USED", BLUE, size=9.5, h=0.29)

    lw = 7.55
    y = 1.74
    for i, (name, items) in enumerate(LANES):
        card(s, LEFT, y, lw, 0.70, BLUE_T, BLUE)
        text(
            s,
            LEFT + 0.18,
            y,
            1.86,
            0.70,
            [Line(name, 9.4, True, BLUE, caps_spacing=30)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(
            s,
            LEFT + 2.10,
            y,
            lw - 2.28,
            0.70,
            [Line(items, 9.0, False, BODY)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if i < 3:
            chevron(s, LEFT + lw / 2 - 0.10, y + 0.72, 0.20, RULE, down=True)
        y += 0.70 + 0.24

    rx, rw = 8.05, 4.98
    ty = 1.76
    for label, names in STACK:
        text(
            s,
            rx,
            ty,
            1.28,
            0.22,
            [Line(label, 9.0, True, BLUE)],
        )
        text(s, rx + 1.32, ty, rw - 1.32, 0.22, [Line(names, 9.0, False, BODY)])
        ty += 0.245

    card(s, rx, 3.32, rw, 1.92, GREEN_T, GREEN)
    text(
        s,
        rx + 0.20,
        3.32,
        rw - 0.40,
        1.92,
        [Line("BUILT AND VERIFIED TODAY", 10.5, True, GREEN, caps_spacing=40)]
        + [
            Line(rest, 9.0, False, BODY, space_before=4.0, lead=f"\u00b7  {lead}")
            for lead, rest in BUILT
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )

    cy = 5.36
    card(s, LEFT, cy, WIDTH, 0.66, AMBER_T, AMBER)
    text(
        s,
        LEFT + 0.20,
        cy,
        3.34,
        0.66,
        [
            Line("HOW WE SPOT A DEPOSIT ADDRESS", 9.0, True, AMBER, caps_spacing=40),
            Line("Six weighted signals. 0.70 or more \u2192 PROBABLE.", 8.6, False, BODY),
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    sx = LEFT + 3.66
    chip_w = (RIGHT - 0.18 - sx - 5 * 0.06) / 6
    for label, weight in SIGNALS:
        rect(s, sx, cy + 0.09, chip_w, 0.48, WHITE, radius=0.14)
        text(
            s,
            sx + 0.09,
            cy + 0.09,
            chip_w - 0.18,
            0.48,
            [Line(label, 8.2, False, BODY), Line(weight, 9.0, True, AMBER)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        sx += chip_w + 0.06

    ey = 6.18
    text(
        s,
        LEFT,
        ey,
        2.90,
        0.48,
        [Line("EVERY NUMBER OPENS INTO ITS EVIDENCE", 8.6, True, INK, caps_spacing=40)],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    sx = LEFT + 3.00
    cell = (RIGHT - sx - 4 * 0.20) / 5
    for i, (name, note) in enumerate(CHAIN):
        rect(s, sx, ey, cell, 0.48, PAGE)
        rect(s, sx, ey, 0.045, 0.48, BLUE)
        text(
            s,
            sx + 0.12,
            ey,
            cell - 0.22,
            0.48,
            [
                Line(name, 8.4, True, BLUE, caps_spacing=20),
                Line(note, 8.2, False, MUTED),
            ],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        if i < 4:
            chevron(s, sx + cell + 0.02, ey + 0.16, 0.16, RULE)
        sx += cell + 0.20


# --------------------------------------------------------------------------
# Slide 4 — FEASIBILITY AND VIABILITY
# --------------------------------------------------------------------------
FEASIBLE = [
    (
        "IT ALREADY RUNS",
        "An address goes in; a named exchange, an itemised risk score and a PDF "
        "come out. 482 tests pass with no internet.",
    ),
    (
        "NO PAID DATA NEEDED",
        "Free public APIs and openly licensed datasets. No commercial forensics "
        "licence \u2014 which is why a district cyber cell could afford it.",
    ),
    (
        "ORDINARY DEPLOYMENT",
        "One server: Python, PostgreSQL, Redis and a web app. No cluster, no GPU "
        "and no graph database to run.",
    ),
    (
        "THE SAME ANSWER EVERY TIME",
        "Exact fractions, never floats. The same input gives the same answer \u2014 "
        "and every claim traces back to a stored, hashed API reply.",
    ),
]

RISKS = [
    (
        "TRON's free API is slow.",
        " We measured half a request per second per method, so a cold 200-address "
        "trace takes about 400 seconds \u2014 not 120.",
        "We work to an address budget, not to hope.",
        " About 60 new addresses inside 120 seconds; anything short of complete "
        "comes back marked PARTIAL. Cached and repeat traces stay fast.",
    ),
    (
        "Public TRON labels are few and dirty.",
        " Of 151 published exchange addresses we checked, 9 were not even valid "
        "TRON addresses.",
        "We check every label on the chain ourselves.",
        " 94 of the 151 survived that check. Each one records its source, its "
        "licence and the date we captured it.",
    ),
    (
        "A simple tracer cannot see internal transfers.",
        " On one sanctioned address, 173,600 ETH arrived where the ordinary "
        "transaction list showed nothing at all.",
        "We fetch them and treat them like any other transfer.",
        " Without that step a tracer misses 95.2% of the money that came in, and "
        "draws its biggest arrow the wrong way round.",
    ),
    (
        "A behaviour test raises false alarms.",
        " Payment processors, OTC desks and company sweep accounts all look like "
        "deposit addresses.",
        "Behaviour alone never gives CONFIRMED,",
        " and a detector that cannot name an innocent explanation for the shape it "
        "flags is not allowed to run.",
    ),
    (
        "A live demo depends on someone else's API.",
        " One rate-limit reply during a timed presentation ends the demo.",
        "Offline by default.",
        " Real chain data, captured and frozen, replayed from disk behind a visible "
        "\u201ccached snapshot\u201d banner. The whole suite runs with no network.",
    ),
]


def slide4(s) -> None:
    y = pill(
        s,
        LEFT,
        1.28,
        3.90,
        "ANALYSIS OF THE FEASIBILITY OF THE IDEA",
        GREEN,
        size=9.0,
        h=0.29,
    )
    for (x, w), (title, blurb) in zip(columns(LEFT, WIDTH, 4, 0.18), FEASIBLE):
        card(s, x, y, w, 1.00, GREEN_T, GREEN)
        text(
            s,
            x + 0.18,
            y,
            w - 0.36,
            1.00,
            [
                Line(title, 9.4, True, GREEN, caps_spacing=40),
                Line(blurb, 9.0, False, BODY, space_before=3.0),
            ],
            anchor=MSO_ANCHOR.MIDDLE,
        )

    lw = 6.20
    rx = LEFT + lw + 0.14
    rw = RIGHT - rx
    y = pill(s, LEFT, 2.84, 3.70, "POTENTIAL CHALLENGES AND RISKS", RED, size=9.0, h=0.29)
    pill(
        s,
        rx,
        2.84,
        4.70,
        "STRATEGIES FOR OVERCOMING THESE CHALLENGES",
        BLUE,
        size=9.0,
        h=0.29,
    )

    for lead_a, rest_a, lead_b, rest_b in RISKS:
        h = 0.62
        rect(s, LEFT, y, lw, h, RED_T)
        rect(s, LEFT, y, 0.05, h, RED)
        rect(s, rx, y, rw, h, PAGE)
        rect(s, rx, y, 0.05, h, BLUE)
        text(
            s,
            LEFT + 0.20,
            y,
            lw - 0.40,
            h,
            [Line(rest_a, 9.0, False, BODY, lead=lead_a)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(
            s,
            rx + 0.20,
            y,
            rw - 0.40,
            h,
            [Line(rest_b, 9.0, False, BODY, lead=lead_b)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        y += h + 0.05

    text(
        s,
        LEFT,
        y + 0.04,
        WIDTH,
        0.24,
        [
            Line(
                "Every figure above is our own measurement, taken on 2026-09-05 and "
                "written up in the repository \u2014 not an estimate.",
                8.6,
                True,
                MUTED,
            )
        ],
    )


# --------------------------------------------------------------------------
# Slide 5 — IMPACT AND BENEFITS
# --------------------------------------------------------------------------
SCALE = [
    ("22,68,346", "cybercrime incidents on NCRP in 2024, up 42% on 2023"),
    ("\u20b922,845.73 cr", "reported lost to cybercrime in 2024"),
    ("\u20b97,130 cr", "saved through CFCFRMS across 23.02 lakh complaints"),
]

USERS = [
    (
        "DISTRICT / STATE CYBER CELL INVESTIGATOR",
        "PRIMARY USER",
        "Not a blockchain expert, and does not need to become one. Types in the "
        "address the victim reported and gets back a named institution to serve, "
        "the hops in between, and the hashes to attach to the request.",
    ),
    (
        "I4C / CENTRAL ANALYST",
        "SECONDARY",
        "Sees the same deposit address turn up in complaints from different states "
        "\u2014 which turns twenty unconnected case files into one operation.",
    ),
    (
        "SUPERVISORY OFFICER",
        "SECONDARY",
        "Sorts a queue by where the money still seems to be, and can read why any "
        "finding was made without having to ask an engineer.",
    ),
]

BENEFITS = [
    (
        "REACHES THE EXCHANGE IN TIME",
        "A freeze request needs someone to send it to. Naming that exchange early "
        "is the difference between getting the money back and not.",
    ),
    (
        "FINDS VICTIMS WHO NEVER COMPLAINED",
        "Tracing backwards from a scam wallet lists the other addresses that paid "
        "into it \u2014 people who never filed a complaint.",
    ),
    (
        "NO PER-SEAT LICENCE COST",
        "Commercial forensics platforms cost more than most state cyber cells can "
        "pay. This runs on free public data, on one server.",
    ),
    (
        "AN ANSWER THAT CAN BE CHECKED",
        "Every number opens into its signals, its transactions, and the stored raw "
        "reply with its hash and the time it was fetched.",
    ),
]

BOUNDS = [
    (
        "It does not name a person.",
        " Public blockchain data cannot do that, and we will not pretend otherwise.",
    ),
    (
        "It does not decide that fraud happened.",
        " A risk score is an argument built from named signals \u2014 not a probability "
        "of guilt.",
    ),
    (
        "It is not plugged into NCRP or CFCFRMS.",
        " We offer an integration-ready API and claim nothing more than that.",
    ),
]


def slide5(s) -> None:
    y = pill(
        s,
        LEFT,
        1.28,
        4.00,
        "POTENTIAL IMPACT ON THE TARGET AUDIENCE",
        BLUE,
        size=9.0,
        h=0.29,
    )

    rect(s, LEFT, y, WIDTH, 0.58, PAGE)
    rect(s, LEFT, y, 0.05, 0.58, BLUE)
    sx = LEFT + 0.22
    for figure, note in SCALE:
        text(
            s,
            sx,
            y,
            4.00,
            0.58,
            [Line(figure, 15.0, True, BLUE), Line(note, 8.6, False, BODY)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        sx += 4.15
    text(
        s,
        LEFT,
        y + 0.60,
        WIDTH,
        0.20,
        [
            Line(
                "Ministry of Home Affairs, Lok Sabha Unstarred Question 432, "
                "answered 2 December 2025",
                8.0,
                False,
                MUTED,
                align=PP_ALIGN.RIGHT,
            )
        ],
    )

    y = 2.54
    for (x, w), (title, badge, blurb) in zip(columns(LEFT, WIDTH, 3, 0.20), USERS):
        ink, tint = (BLUE, BLUE_T) if badge == "PRIMARY USER" else (GREY, GREY_T)
        card(s, x, y, w, 1.24, tint, ink)
        text(
            s,
            x + 0.18,
            y + 0.11,
            w - 0.36,
            1.02,
            [
                Line(badge, 8.0, True, ink, caps_spacing=70),
                Line(title, 10.0, True, INK, space_before=1.5),
                Line(blurb, 9.0, False, BODY, space_before=3.5),
            ],
        )

    y = pill(
        s,
        LEFT,
        3.86,
        5.00,
        "BENEFITS OF THE SOLUTION (SOCIAL, ECONOMIC, ENVIRONMENTAL, ETC.)",
        GREEN,
        size=9.0,
        h=0.29,
    )

    half = (WIDTH - 0.46) / 2
    rect(s, LEFT, y, half, 0.86, GREY_T)
    rect(s, LEFT, y, 0.05, 0.86, GREY)
    text(
        s,
        LEFT + 0.22,
        y,
        half - 0.40,
        0.86,
        [
            Line("HOW IT IS DONE TODAY", 8.6, True, GREY, caps_spacing=60),
            Line(
                "A block explorer is opened and clicked through two or three hops by "
                "hand. Six to twelve hours per address, and it usually ends in "
                "\u201cunknown\u201d.",
                9.0,
                False,
                MUTED,
                space_before=3.0,
            ),
            Line(
                "Field estimate. No measured study exists, and we do not claim one.",
                8.0,
                False,
                MUTED,
                space_before=2.5,
            ),
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    chevron(s, LEFT + half + 0.11, y + 0.32, 0.22, RULE)
    rect(s, LEFT + half + 0.46, y, half, 0.86, BLUE_T)
    rect(s, LEFT + half + 0.46, y, 0.05, 0.86, BLUE)
    text(
        s,
        LEFT + half + 0.68,
        y,
        half - 0.40,
        0.86,
        [
            Line("WITH TRACEFALL", 8.6, True, BLUE, caps_spacing=60),
            Line(
                "The automated stages finish in about ninety seconds on cached or "
                "warm data. The investigator checks an evidenced answer instead of "
                "producing one.",
                9.0,
                False,
                INK,
                space_before=3.0,
            ),
            Line(
                "Measured on captured chain data. A cold live trace is limited by "
                "provider rate limits, and says so on screen.",
                8.0,
                False,
                MUTED,
                space_before=2.5,
            ),
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )

    by = y + 0.94
    for (x, w), (title, blurb) in zip(columns(LEFT, WIDTH, 4, 0.18), BENEFITS):
        rect(s, x, by, w, 0.80, PAGE)
        rect(s, x, by, 0.05, 0.80, BLUE)
        text(
            s,
            x + 0.18,
            by,
            w - 0.36,
            0.80,
            [
                Line(title, 8.8, True, BLUE, caps_spacing=40),
                Line(blurb, 8.6, False, BODY, space_before=2.5),
            ],
            anchor=MSO_ANCHOR.MIDDLE,
        )

    sy = by + 0.88
    card(s, LEFT, sy, WIDTH, 0.72, RED_T, RED)
    text(
        s,
        LEFT + 0.22,
        sy,
        2.60,
        0.72,
        [
            Line("WHERE THIS SYSTEM STOPS", 9.0, True, RED, caps_spacing=40),
            Line("Said by us, before anyone asks.", 8.4, False, BODY),
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    bx = LEFT + 2.96
    for lead, rest in BOUNDS:
        text(
            s,
            bx,
            sy,
            3.10,
            0.72,
            [Line(rest, 8.6, False, BODY, lead=lead)],
            anchor=MSO_ANCHOR.MIDDLE,
        )
        bx += 3.26


# --------------------------------------------------------------------------
# Slide 6 — RESEARCH AND REFERENCES
# --------------------------------------------------------------------------
REFS: list[tuple[str, object, list[tuple[str, str, str]]]] = [
    (
        "Government mandate, scale and law",
        BLUE,
        [
            (
                "MHA / I4C — SOP for NCRP–CFCFRMS, 2 January 2026",
                "Where funds reach an exchange not onboarded to CFCFRMS, the officer "
                "“may conduct a VDA forensic analysis … to ascertain that which VASP or "
                "VDA Exchange has control of the wallet.” Issuance confirmed in "
                "Rajya Sabha USQ 553, 4 Feb 2026.",
                "mha.gov.in/MHA1/Par2017/pdfs/par2026-pdfs/RS04022026/553.pdf",
            ),
            (
                "MHA — Lok Sabha Unstarred Q. 432, 2 December 2025",
                "22,68,346 NCRP incidents in 2024 (+42.08%); ₹22,845.73 crore reported "
                "lost; ₹7,130 crore saved via CFCFRMS.",
                "mha.gov.in/MHA1/Par2017/pdfs/par2025-pdfs/LS02122025/432.pdf",
            ),
            (
                "Standing Committee on Home Affairs — 254th Report, 20 Aug 2025",
                "Recommends training in “digital forensics, blockchain analysis and "
                "virtual asset tracing”.",
                "sansad.in › Committee_File › ReportFile › 254_2025_8_12.pdf",
            ),
            (
                "Ministry of Finance — Gazette S.O. 1072(E), 7 March 2023",
                "Brings virtual digital asset services under the PMLA, 2002.",
                "egazette.gov.in/WriteReadData/2023/244184.pdf",
            ),
            (
                "PIB / FIU-IND, 1 October 2025",
                "50 VDA service providers registered; non-compliance notices issued to "
                "25 offshore exchanges.",
                "pib.gov.in/PressReleasePage.aspx?PRID=2173758",
            ),
        ],
    ),
    (
        "Why TRON and USDT",
        AMBER,
        [
            (
                "UNODC — Casinos, Money Laundering, Underground Banking and "
                "Transnational Organized Crime in East and Southeast Asia, Jan 2024",
                "\u201cUSDT on the TRON blockchain has become a preferred choice for "
                "regional cyberfraud operations and money launderers alike due to its "
                "stability and the ease, anonymity, and low fees of its "
                "transactions.\u201d (p. 50) The same page reports an audit finding "
                "17.07 billion USDT tied to underground exchanges and criminal "
                "activity between Sept 2022 and Sept 2023.",
                "unodc.org/roseap › Casino_Underground_Banking_Report_2024.pdf",
            ),
            (
                "TRM Labs — 2025 Crypto Crime Report, 10 February 2025",
                "58% of illicit crypto volume in 2024 was on TRON, ahead of Ethereum "
                "(24%) and Bitcoin (12%). Illicit volume overall, not investment "
                "fraud alone.",
                "trmlabs.com/reports-and-whitepapers/2025-crypto-crime-report",
            ),
            (
                "Enforcement Directorate — press release, 20 November 2025",
                "Proceeds of a \u20b9285-crore cyber-fraud network turned into USDT over "
                "exchange P2P using non-KYC accounts; \u20b98.46 crore attached across 92 "
                "accounts. Names USDT; the chain is not stated.",
                "enforcementdirectorate.gov.in › Press Release-PAO-Cyber Fraud Case",
            ),
            (
                "Enforcement Directorate — press release, 26 September 2025",
                "An investment scam promising 5–6% monthly returns collected funds "
                "through payment aggregators and USDT; ₹391 crore attached across 185 "
                "accounts.",
                "enforcementdirectorate.gov.in › Press Release-Navab Hassan QFX",
            ),
        ],
    ),
    (
        "Data sources and our own measurements",
        GREEN,
        [
            (
                "TronGrid · Blockscout · Etherscan",
                "Transaction data for TRON and Ethereum, used under their API terms. "
                "We never scrape explorer label databases.",
                "developers.tron.network/reference/rate-limits · docs.blockscout.com",
            ),
            (
                "OFAC SDN sanctioned digital-currency addresses",
                "405 addresses ingested (281 TRON, 124 Ethereum), extracted with the "
                "MIT-licensed 0xB10C tool.",
                "github.com/0xB10C/ofac-sanctioned-digital-currency-addresses",
            ),
            (
                "Dune spellbook — TRON exchange addresses",
                "A lead list only. Its BSL 1.1 licence does not cover our use, so we "
                "re-establish every address ourselves and never load theirs in.",
                "github.com/duneanalytics/spellbook",
            ),
            (
                "Our measurements, 2026-09-05 (written up in the repository)",
                "TronGrid sustains half a request per second per method; Blockscout took "
                "195 requests without throttling. 9 of 151 published TRON exchange "
                "labels are not valid addresses; 94 survived our checks.",
                "docs/research/OQ-01-provider-rate-limits.md · OQ-08-tron-label-coverage.md",
            ),
            (
                "Our design record — 21 architecture decisions and a written limits list",
                "Why TRON and Ethereum first; why value is shared out in proportion; why "
                "there is no graph database; why the database enforces the three "
                "tiers; and what we will not claim.",
                "docs/DECISIONS.md · docs/LIMITATIONS.md",
            ),
        ],
    ),
]


def slide6(s) -> None:
    y = pill(
        s,
        LEFT,
        1.28,
        4.60,
        "DETAILS / LINKS OF THE REFERENCE AND RESEARCH WORK",
        BLUE,
        size=9.0,
        h=0.29,
    )

    col_h = 4.24
    for (x, w), (group, ink, items) in zip(columns(LEFT, WIDTH, 3, 0.20), REFS):
        rect(s, x, y, w, col_h, PAGE)
        rect(s, x, y, 0.05, col_h, ink)
        text(
            s,
            x + 0.20,
            y + 0.12,
            w - 0.38,
            0.24,
            [Line(group.upper(), 9.0, True, ink, caps_spacing=50)],
        )
        hairline(s, x + 0.20, y + 0.41, w - 0.40, RULE)
        lines: list[Line] = []
        for i, (name, note, url) in enumerate(items):
            lines.append(Line(name, 9.0, True, INK, space_before=0 if i == 0 else 7.0))
            if note:
                lines.append(Line(note, 8.4, False, BODY, space_before=1.5))
            if url:
                lines.append(Line(url, 8.0, False, BLUE, space_before=1.5))
        text(s, x + 0.20, y + 0.52, w - 0.40, col_h - 0.64, lines)

    ny = y + col_h + 0.14
    half = (WIDTH - 0.20) / 2
    rect(s, LEFT, ny, half, 0.74, AMBER_T)
    rect(s, LEFT, ny, 0.05, 0.74, AMBER)
    text(
        s,
        LEFT + 0.22,
        ny,
        half - 0.40,
        0.74,
        [
            Line("HOW WE USE THESE SOURCES", 8.8, True, AMBER, caps_spacing=60),
            Line(
                "We never scrape explorer label databases \u2014 their terms forbid it. A "
                "dataset whose licence does not allow our use is treated as a lead to "
                "check ourselves, never loaded in. Every label we ship records its "
                "source, its licence and the date we captured it.",
                8.6,
                False,
                BODY,
                space_before=2.5,
            ),
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    rx6 = LEFT + half + 0.20
    rect(s, rx6, ny, half, 0.74, GREY_T)
    rect(s, rx6, ny, 0.05, 0.74, GREY)
    text(
        s,
        rx6 + 0.22,
        ny,
        half - 0.40,
        0.74,
        [
            Line("WHAT WE COULD NOT VERIFY", 8.8, True, GREY, caps_spacing=60),
            Line(
                "No Indian government source we found names TRON specifically \u2014 the "
                "chain evidence is UNODC and TRM Labs, and the deck says so. FIU-IND "
                "publishes how many providers are registered but not who they are, so "
                "we do not claim to cross-check that list.",
                8.6,
                False,
                BODY,
                space_before=2.5,
            ),
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )


# --------------------------------------------------------------------------
def main() -> int:
    if not TEMPLATE.exists():
        print(f"template not found: {TEMPLATE}", file=sys.stderr)
        return 1
    shutil.copy(TEMPLATE, OUT)
    prs = Presentation(OUT)

    delete_slide(prs, 6)  # the template's own "IMPORTANT INSTRUCTIONS" slide
    slides = list(prs.slides)
    for s in slides[1:]:
        drop_prompt(s)
        restyle_footer(s, FOOTER, TEAM)

    for builder, s in zip((slide1, slide2, slide3, slide4, slide5, slide6), slides):
        builder(s)

    prs.save(OUT)
    print(f"wrote {OUT}  ({len(list(prs.slides))} slides)")

    soffice = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if soffice.exists():
        subprocess.run(
            [
                str(soffice),
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(OUT.parent),
                str(OUT),
            ],
            check=True,
            capture_output=True,
        )
        print(f"wrote {OUT.with_suffix('.pdf')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
