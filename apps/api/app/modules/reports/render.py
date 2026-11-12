"""
Report files (brief section 10): CSV for analysis, XLSX with live subtotals, and compact statement-style PDF
with title, period and filters, generation time and person, page numbers, itemised rows, subtotals, totals
and a reconciliation footer. Pure-Python libraries only (xlsxwriter, ReportLab), as the build guideline asks.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import xlsxwriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import get_settings
from app.modules.reports.catalogue import Result
from app.modules.reports.schemas import Column

ORGANISATION = "Empire Networks Pvt Ltd"
PHI_NOTICE = "Contains patient information (PHI). Store and share it only as your HIPAA policy allows."
NAVY = colors.HexColor("#0B1D33")
LINE = colors.HexColor("#E5E7ED")
SOFT = colors.HexColor("#F4F5F8")


@dataclass
class Meta:
    title: str
    period: str
    filters: list[str]
    scope: list[str]
    generated_at: datetime
    generated_by: str
    reference: str
    contains_phi: bool


def local(moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(get_settings().business_timezone))


def text_value(column: Column, value: Any) -> str:
    """A value as people read it: 05 Nov 2026, $1,234.56, 45.2%."""
    if value is None or value == "":
        return ""
    match column.kind:
        case "date":
            return value.strftime("%d %b %Y") if isinstance(value, date) else str(value)
        case "datetime":
            return local(value).strftime("%d %b %Y %H:%M") if isinstance(value, datetime) else str(value)
        case "money":
            return f"${Decimal(value):,.2f}"
        case "percent":
            return f"{value:.1f}%"
        case "int":
            return f"{value:,}" if isinstance(value, int) else f"{value}"
    return str(value)


def _safe(text: str) -> str:
    """Cells starting with = + - @ would run as formulas in a spreadsheet: neutralise them."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def groups(result: Result) -> list[tuple[str | None, list[dict[str, Any]]]]:
    """Rows split into subtotal groups, in order (one group of everything when there's no grouping)."""
    if not result.group_by:
        return [(None, result.rows)]
    out: list[tuple[str | None, list[dict[str, Any]]]] = []
    for row in result.rows:
        key = row.get(result.group_by)
        if not out or out[-1][0] != key:
            out.append((key, []))
        out[-1][1].append(row)
    return out


def subtotal(result: Result, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {key: sum((r.get(key) or 0) for r in rows) for key in result.sum_keys}


# ---- CSV ------------------------------------------------------------------------------------------------


def to_csv(result: Result) -> bytes:
    """Plain data for analysis: one header row, then one row per item. Parameters are in the export log."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([c.label for c in result.columns])
    for row in result.rows:
        out = []
        for c in result.columns:
            value = row.get(c.key)
            if value is None:
                out.append("")
            elif c.kind == "date" and isinstance(value, date):
                out.append(value.isoformat())
            elif c.kind == "datetime" and isinstance(value, datetime):
                out.append(local(value).strftime("%Y-%m-%d %H:%M"))
            elif c.kind == "money":
                out.append(f"{Decimal(value):.2f}")
            elif c.kind in ("int", "percent"):
                out.append(str(value))
            else:
                out.append(_safe(str(value)))
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8-sig")  # the BOM makes Excel read accents correctly


# ---- XLSX -----------------------------------------------------------------------------------------------


def to_xlsx(result: Result, meta: Meta) -> bytes:
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True, "remove_timezone": True})
    title = book.add_format({"bold": True, "font_size": 14, "font_color": "#0B1D33"})
    quiet = book.add_format({"font_color": "#727988"})
    warn = book.add_format({"font_color": "#D24D57", "bold": True})
    head = book.add_format({"bold": True, "bg_color": "#0B1D33", "font_color": "#FFFFFF", "border": 1})
    kinds = {
        "text": {},
        "date": {"num_format": "dd mmm yyyy"},
        "datetime": {"num_format": "dd mmm yyyy hh:mm"},
        "money": {"num_format": "$#,##0.00"},
        "int": {"num_format": "#,##0"},
        "percent": {"num_format": '0.0"%"'},
    }
    plain = {k: book.add_format(v) for k, v in kinds.items()}
    bold = {k: book.add_format({**v, "bold": True, "bg_color": "#F4F5F8"}) for k, v in kinds.items()}
    total = {k: book.add_format({**v, "bold": True, "top": 2}) for k, v in kinds.items()}

    sheet = book.add_worksheet("Report")
    sheet.write_string(0, 0, meta.title, title)
    sheet.write_string(1, 0, f"Period: {meta.period}", quiet)
    sheet.write_string(2, 0, "Filters: " + ("; ".join(meta.filters) or "none"), quiet)
    sheet.write_string(3, 0, "Scope: " + (", ".join(meta.scope) or "all practices you can see"), quiet)
    generated = local(meta.generated_at).strftime("%d %b %Y %H:%M")
    sheet.write_string(4, 0, f"Generated {generated} by {meta.generated_by}, {meta.reference}", quiet)
    if meta.contains_phi:
        sheet.write_string(5, 0, PHI_NOTICE, warn)
    header = 7
    for col, c in enumerate(result.columns):
        sheet.write_string(header, col, c.label, head)

    def put(r: int, col: int, c: Column, value: Any, style: dict) -> None:
        fmt = style[c.kind]
        if value is None or value == "":
            sheet.write_blank(r, col, None, fmt)
        elif c.kind == "date" and isinstance(value, date):
            sheet.write_datetime(r, col, datetime.combine(value, datetime.min.time()), fmt)
        elif c.kind == "datetime" and isinstance(value, datetime):
            sheet.write_datetime(r, col, local(value).replace(tzinfo=None), fmt)
        elif c.kind in ("money", "int", "percent"):
            sheet.write_number(r, col, float(value), fmt)
        else:
            sheet.write_string(r, col, str(value), fmt)

    row = header + 1
    first_data = row
    summed = {c.key: i for i, c in enumerate(result.columns) if c.key in result.sum_keys}
    for name, items in groups(result):
        start = row
        for item in items:
            for col, c in enumerate(result.columns):
                put(row, col, c, item.get(c.key), plain)
            row += 1
        if name is not None and result.sum_keys:
            sheet.write_string(row, 0, f"Subtotal: {name}", bold["text"])
            for col in range(1, len(result.columns)):
                sheet.write_blank(row, col, None, bold[result.columns[col].kind])
            for col in summed.values():
                cell = xlsxwriter.utility.xl_range(start, col, row - 1, col)
                sheet.write_formula(row, col, f"=SUBTOTAL(9,{cell})", bold[result.columns[col].kind])
            row += 1
    if result.sum_keys or result.extra_totals:
        sheet.write_string(row, 0, f"Total ({len(result.rows)} rows)", total["text"])
        for col in range(1, len(result.columns)):
            sheet.write_blank(row, col, None, total[result.columns[col].kind])
        for col in summed.values():
            cell = xlsxwriter.utility.xl_range(first_data, col, max(row - 1, first_data), col)
            sheet.write_formula(row, col, f"=SUBTOTAL(9,{cell})", total[result.columns[col].kind])
        for key, value in result.extra_totals.items():
            col = next((i for i, c in enumerate(result.columns) if c.key == key), None)
            if col is not None and value is not None:
                put(row, col, result.columns[col], value, total)
        row += 1
    for i, note in enumerate(result.notes):
        sheet.write_string(row + 1 + i, 0, note, quiet)
    if result.rows:
        sheet.autofilter(header, 0, header + len(result.rows) + len(groups(result)), len(result.columns) - 1)
    sheet.freeze_panes(header + 1, 1)
    for col, c in enumerate(result.columns):
        longest = max([len(c.label)] + [len(text_value(c, r.get(c.key))) for r in result.rows[:500]])
        sheet.set_column(col, col, min(max(longest + 2, 9), 48))

    about = book.add_worksheet("About this report")
    lines = [
        ("Report", meta.title),
        ("Reference", meta.reference),
        ("Generated", f"{generated} by {meta.generated_by}"),
        ("Period", meta.period),
        ("Filters", "; ".join(meta.filters) or "none"),
        ("Scope", ", ".join(meta.scope) or "all practices you can see"),
        ("Rows", str(len(result.rows))),
        *[("Note", n) for n in result.notes],
    ]
    if meta.contains_phi:
        lines.append(("Patient information", PHI_NOTICE))
    for i, (label, value) in enumerate(lines):
        about.write_string(i, 0, label, head)
        about.write_string(i, 1, value)
    about.set_column(0, 0, 20)
    about.set_column(1, 1, 100)
    book.close()
    return buffer.getvalue()


# ---- PDF ------------------------------------------------------------------------------------------------

# Fixed widths (points) for numbers and dates; text columns share what's left by weight.
FIXED = {"date": 47, "datetime": 64, "money": 52, "int": 34, "percent": 42}
TEXT_WEIGHTS = {
    "details": 4.0,
    "patient": 1.45,
    "subscriber_id": 1.4,
    "file": 2.0,
    "payer": 1.6,
    "flags": 2.0,
    "person": 1.4,
    "claim": 1.15,
    "claim_status": 0.95,
    "assigned_to": 0.95,
}
# Shorter headings where a PDF column is narrow (the CSV and Excel files keep the full labels).
PDF_LABELS = {
    "service_date": "Service",
    "patient_resp": "Pt resp.",
    "aging_days": "Days",
    "assigned_to": "Assigned",
    "subscriber_id": "Subscriber",
    "days_overdue": "Overdue",
    "share": "Share",
}


def _numbered_canvas(footer_left: str, phi: bool) -> type[canvas.Canvas]:
    """A canvas that draws "Page X of Y" and the footer once the page count is known."""

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict[str, Any]] = []

        def showPage(self) -> None:  # noqa: N802 - ReportLab's name
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            count = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                width, _ = self._pagesize
                self.setFont("Helvetica", 7)
                self.setFillColor(colors.HexColor("#727988"))
                self.drawString(12 * mm, 8 * mm, footer_left)
                self.drawRightString(width - 12 * mm, 8 * mm, f"Page {self._pageNumber} of {count}")
                if phi:
                    self.setFillColor(colors.HexColor("#D24D57"))
                    self.drawCentredString(width / 2, 12 * mm, "Confidential: contains patient information")
                super().showPage()
            super().save()

    return NumberedCanvas


def to_pdf(result: Result, meta: Meta) -> bytes:
    # With subtotal groups, the group column becomes a heading row instead of repeating on every line.
    columns = (
        [c for c in result.columns if c.key != result.group_by] if result.group_by else list(result.columns)
    )
    pagesize = landscape(A4) if len(columns) > 7 else A4
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=18 * mm,
        title=meta.title,
        author=ORGANISATION,
    )
    small = 6.8 if len(columns) > 12 else 7.6 if len(columns) > 8 else 8.4
    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=NAVY)
    meta_style = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=8, leading=10.5, textColor=colors.HexColor("#4B5260")
    )
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=small, leading=small + 2)
    cell_bold = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
    group_style = ParagraphStyle("group", parent=cell, fontName="Helvetica-Bold", textColor=NAVY)
    head_style = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    numeric = {"money", "int", "percent"}

    generated = local(meta.generated_at).strftime("%d %b %Y %H:%M")
    story: list[Any] = [
        Paragraph(f"{ORGANISATION}, AR Operations Portal", meta_style),
        Paragraph(_esc(meta.title), title_style),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Period:</b> {_esc(meta.period)}", meta_style),
        Paragraph("<b>Filters:</b> " + _esc("; ".join(meta.filters) or "none"), meta_style),
        Paragraph("<b>Scope:</b> " + _esc(", ".join(meta.scope) or "all practices you can see"), meta_style),
        Paragraph(
            f"<b>Generated:</b> {generated} by {_esc(meta.generated_by)} ({meta.reference})", meta_style
        ),
    ]
    if meta.contains_phi:
        story.append(Paragraph(f'<font color="#D24D57"><b>{PHI_NOTICE}</b></font>', meta_style))
    story.append(Spacer(1, 4 * mm))

    def para(c: Column, value: Any, style: ParagraphStyle) -> Any:
        text = _esc(text_value(c, value))
        if c.kind in numeric:
            return Paragraph(f'<para alignment="right">{text}</para>', style)
        return Paragraph(text, style)

    def heading(c: Column) -> Any:
        align = "right" if c.kind in numeric else "left"
        return Paragraph(
            f'<para alignment="{align}">{_esc(PDF_LABELS.get(c.key, c.label))}</para>', head_style
        )

    data: list[list[Any]] = [[heading(c) for c in columns]]
    styles: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    blank = [""] * (len(columns) - 1)
    for name, items in groups(result):
        if name is not None:
            data.append([Paragraph(_esc(str(name)), group_style), *blank])
            styles.append(("SPAN", (0, len(data) - 1), (-1, len(data) - 1)))
        for item in items:
            data.append([para(c, item.get(c.key), cell) for c in columns])
        if name is not None and result.sum_keys:
            sums = subtotal(result, items)
            row = [Paragraph(f"Subtotal ({len(items)})", cell_bold)]
            row += [para(c, sums.get(c.key), cell_bold) if c.key in sums else "" for c in columns[1:]]
            data.append(row)
            styles.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), SOFT))
    if result.sum_keys or result.extra_totals:
        totals = result.totals()
        row = [Paragraph(f"Total ({len(result.rows)})", cell_bold)]
        row += [para(c, totals.get(c.key), cell_bold) if c.key in totals else "" for c in columns[1:]]
        data.append(row)
        styles.append(("LINEABOVE", (0, len(data) - 1), (-1, len(data) - 1), 1, NAVY))
    if not result.rows:
        data.append([Paragraph("No rows match these filters.", cell), *blank])

    width = pagesize[0] - 24 * mm
    fixed = sum(FIXED.get(c.kind, 0) for c in columns)
    text_columns = [c for c in columns if c.kind not in FIXED]
    weights = {c.key: TEXT_WEIGHTS.get(c.key, 1.0) for c in text_columns}
    spare = max(width - fixed, 40 * len(text_columns))
    widths = [
        FIXED[c.kind] if c.kind in FIXED else spare * weights[c.key] / sum(weights.values()) for c in columns
    ]
    if sum(widths) > width:  # very wide reports: scale everything down evenly
        widths = [w * width / sum(widths) for w in widths]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(styles))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    for note in result.notes:
        story.append(Paragraph(_esc(note), meta_style))

    footer = f"{ORGANISATION}, {meta.title}, {meta.reference}, {generated}"
    doc.build(story, canvasmaker=_numbered_canvas(footer, meta.contains_phi))
    return buffer.getvalue()


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
