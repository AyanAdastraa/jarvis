from pathlib import Path
from datetime import datetime
import html
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    KeepTogether,
    Preformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents


# ============================================================
# PATHS
# ============================================================
from core.sandbox import resolve_workspace_path

def get_output_path(filename: str) -> Path:
    # We resolve it inside the workspace, potentially inside an "output" directory.
    # The sandbox resolver guarantees it's inside the workspace.
    return resolve_workspace_path(f"output/{filename}")

# ============================================================
# COLORS
# ============================================================

BLACK = colors.HexColor("#111111")
DARK = colors.HexColor("#1F2937")
GRAY = colors.HexColor("#6B7280")
LIGHT_GRAY = colors.HexColor("#E5E7EB")
VERY_LIGHT = colors.HexColor("#F7F7F7")
ACCENT = colors.HexColor("#111827")


# ============================================================
# STYLES
# ============================================================

def build_styles():

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="JTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            alignment=TA_CENTER,
            textColor=BLACK,
            spaceAfter=20,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=19,
            alignment=TA_CENTER,
            textColor=GRAY,
            spaceAfter=15,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JHeading1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=BLACK,
            spaceBefore=18,
            spaceAfter=10,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JHeading2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=20,
            textColor=DARK,
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JHeading3",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=17,
            textColor=DARK,
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=17,
            textColor=BLACK,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JBullet",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=16,
            leftIndent=18,
            firstLineIndent=-10,
            spaceAfter=5,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JNumber",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=16,
            leftIndent=20,
            firstLineIndent=-15,
            spaceAfter=5,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JCode",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=8.5,
            leading=12,
            leftIndent=8,
            rightIndent=8,
            spaceBefore=6,
            spaceAfter=10,
            backColor=VERY_LIGHT,
            borderColor=LIGHT_GRAY,
            borderWidth=0.5,
            borderPadding=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="JTOC",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=DARK,
        )
    )

    return styles


# ============================================================
# DOCUMENT TEMPLATE
# ============================================================

class JarvisDocTemplate(BaseDocTemplate):

    def __init__(
        self,
        filename,
        title="JARVIS Document",
        author="JARVIS",
        **kwargs,
    ):

        super().__init__(
            filename,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=25 * mm,
            bottomMargin=20 * mm,
            **kwargs,
        )

        self.document_title = title
        self.document_author = author

        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )

        template = PageTemplate(
            id="normal",
            frames=[frame],
            onPage=self.draw_page,
        )

        self.addPageTemplates([template])

    def draw_page(self, canvas, doc):

        canvas.saveState()

        page_number = canvas.getPageNumber()

        # Header
        if page_number > 1:

            canvas.setStrokeColor(LIGHT_GRAY)
            canvas.setLineWidth(0.5)

            canvas.line(
                self.leftMargin,
                A4[1] - 15 * mm,
                A4[0] - self.rightMargin,
                A4[1] - 15 * mm,
            )

            canvas.setFont(
                "Helvetica",
                8,
            )

            canvas.setFillColor(GRAY)

            canvas.drawString(
                self.leftMargin,
                A4[1] - 11 * mm,
                self.document_title[:80],
            )

            canvas.drawRightString(
                A4[0] - self.rightMargin,
                A4[1] - 11 * mm,
                "JARVIS",
            )

        # Footer
        if page_number > 1:

            canvas.setStrokeColor(LIGHT_GRAY)
            canvas.setLineWidth(0.5)

            canvas.line(
                self.leftMargin,
                13 * mm,
                A4[0] - self.rightMargin,
                13 * mm,
            )

            canvas.setFont(
                "Helvetica",
                8,
            )

            canvas.setFillColor(GRAY)

            canvas.drawString(
                self.leftMargin,
                8 * mm,
                "Generated by JARVIS",
            )

            canvas.drawRightString(
                A4[0] - self.rightMargin,
                8 * mm,
                f"Page {page_number}",
            )

        canvas.restoreState()

    def afterFlowable(self, flowable):

        if not isinstance(
            flowable,
            Paragraph,
        ):
            return

        style_name = flowable.style.name

        if style_name not in {
            "JHeading1",
            "JHeading2",
            "JHeading3",
        }:
            return

        level = {
            "JHeading1": 0,
            "JHeading2": 1,
            "JHeading3": 2,
        }[style_name]

        text = flowable.getPlainText()

        key = (
            f"toc-{level}-"
            + re.sub(
                r"[^a-zA-Z0-9]+",
                "-",
                text.lower(),
            )
        )

        self.canv.bookmarkPage(key)

        self.notify(
            "TOCEntry",
            (
                level,
                text,
                self.page,
                key,
            ),
        )


# ============================================================
# HELPERS
# ============================================================

def escape_text(text):

    return html.escape(
        str(text),
        quote=False,
    )


def inline_format(text):

    text = escape_text(text)

    # Bold
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
    )

    # Italic
    text = re.sub(
        r"\*(.+?)\*",
        r"<i>\1</i>",
        text,
    )

    # Inline code
    text = re.sub(
        r"`(.+?)`",
        r"<font name='Courier'>\1</font>",
        text,
    )

    return text


def make_table(rows, styles):

    if not rows:
        return None

    processed = []

    for row_index, row in enumerate(rows):

        processed_row = []

        for cell in row:

            processed_row.append(
                Paragraph(
                    inline_format(str(cell)),
                    styles["JBody"],
                )
            )

        processed.append(processed_row)

    table = Table(
        processed,
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    DARK,
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    LIGHT_GRAY,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    return table


# ============================================================
# MARKDOWN → FLOWABLES
# ============================================================

def markdown_to_story(content, styles):

    lines = content.splitlines()

    story = []

    code_mode = False
    code_lines = []

    table_rows = []

    def flush_table():

        nonlocal table_rows

        if table_rows:

            table = make_table(
                table_rows,
                styles,
            )

            if table:
                story.append(table)
                story.append(
                    Spacer(1, 12)
                )

            table_rows = []

    for raw_line in lines:

        line = raw_line.rstrip()

        # --------------------------------------------
        # CODE BLOCK
        # --------------------------------------------

        if line.strip().startswith("```"):

            if code_mode:

                code_mode = False

                story.append(
                    Preformatted(
                        "\n".join(code_lines),
                        styles["JCode"],
                    )
                )

                code_lines = []

            else:

                flush_table()

                code_mode = True

            continue

        if code_mode:

            code_lines.append(line)
            continue

        # --------------------------------------------
        # TABLE
        # --------------------------------------------

        if "|" in line:

            pieces = [
                x.strip()
                for x in line.strip("|").split("|")
            ]

            # Markdown separator row
            if all(
                re.fullmatch(
                    r":?-{3,}:?",
                    x,
                )
                for x in pieces
            ):
                continue

            if pieces:

                table_rows.append(pieces)
                continue

        else:

            flush_table()

        # --------------------------------------------
        # EMPTY
        # --------------------------------------------

        if not line.strip():

            story.append(
                Spacer(1, 5)
            )

            continue

        # --------------------------------------------
        # H1
        # --------------------------------------------

        if line.startswith("# "):

            text = line[2:].strip()

            story.append(
                Paragraph(
                    inline_format(text),
                    styles["JHeading1"],
                )
            )

            continue

        # --------------------------------------------
        # H2
        # --------------------------------------------

        if line.startswith("## "):

            text = line[3:].strip()

            story.append(
                Paragraph(
                    inline_format(text),
                    styles["JHeading2"],
                )
            )

            continue

        # --------------------------------------------
        # H3
        # --------------------------------------------

        if line.startswith("### "):

            text = line[4:].strip()

            story.append(
                Paragraph(
                    inline_format(text),
                    styles["JHeading3"],
                )
            )

            continue

        # --------------------------------------------
        # BULLETS
        # --------------------------------------------

        if re.match(
            r"^\s*[-*]\s+",
            line,
        ):

            text = re.sub(
                r"^\s*[-*]\s+",
                "",
                line,
            )

            story.append(
                Paragraph(
                    "• " + inline_format(text),
                    styles["JBullet"],
                )
            )

            continue

        # --------------------------------------------
        # NUMBERED LIST
        # --------------------------------------------

        match = re.match(
            r"^\s*(\d+)\.\s+(.+)",
            line,
        )

        if match:

            number = match.group(1)
            text = match.group(2)

            story.append(
                Paragraph(
                    f"{number}. {inline_format(text)}",
                    styles["JNumber"],
                )
            )

            continue

        # --------------------------------------------
        # NORMAL PARAGRAPH
        # --------------------------------------------

        story.append(
            Paragraph(
                inline_format(line),
                styles["JBody"],
            )
        )

    flush_table()

    return story


# ============================================================
# MAIN PDF GENERATOR
# ============================================================

def create_professional_pdf(
    title,
    content,
    filename="jarvis_report.pdf",
    subtitle=None,
    author="JARVIS",
):

    filename = Path(filename).name

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    output_path = get_output_path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = build_styles()

    doc = JarvisDocTemplate(
        str(output_path),
        title=title,
        author=author,
    )

    story = []

    # ========================================================
    # COVER
    # ========================================================

    story.append(
        Spacer(1, 55 * mm)
    )

    story.append(
        Paragraph(
            escape_text(title),
            styles["JTitle"],
        )
    )

    if subtitle:

        story.append(
            Paragraph(
                inline_format(subtitle),
                styles["JSubtitle"],
            )
        )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            datetime.now().strftime(
                "%d %B %Y"
            ),
            ParagraphStyle(
                "CoverDate",
                parent=styles["JSubtitle"],
                fontSize=10,
            ),
        )
    )

    story.append(
        Spacer(1, 45 * mm)
    )

    story.append(
        Paragraph(
            "Generated by JARVIS",
            ParagraphStyle(
                "CoverBrand",
                parent=styles["JSubtitle"],
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=DARK,
            ),
        )
    )

    story.append(
        PageBreak()
    )

    # ========================================================
    # TABLE OF CONTENTS
    # ========================================================

    toc = TableOfContents()

    toc.levelStyles = [
        ParagraphStyle(
            name="TOC1",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=18,
            leftIndent=0,
            firstLineIndent=0,
        ),
        ParagraphStyle(
            name="TOC2",
            fontName="Helvetica",
            fontSize=10,
            leading=16,
            leftIndent=15,
            firstLineIndent=0,
        ),
        ParagraphStyle(
            name="TOC3",
            fontName="Helvetica",
            fontSize=9,
            leading=14,
            leftIndent=30,
            firstLineIndent=0,
        ),
    ]

    story.append(
        Paragraph(
            "Table of Contents",
            styles["JHeading1"],
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(toc)

    story.append(
        PageBreak()
    )

    # ========================================================
    # CONTENT
    # ========================================================

    story.extend(
        markdown_to_story(
            content,
            styles,
        )
    )

    # ========================================================
    # BUILD
    # ========================================================

    doc.multiBuild(story)

    return str(output_path)