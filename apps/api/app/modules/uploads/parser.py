"""
Reads an AR sheet (.xlsx or .csv) into clean rows, and lists every problem by row number.
Problems are described without repeating the cell's value, so error reports never contain patient data.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

MAX_ROWS = 20_000


@dataclass(frozen=True)
class Column:
    field: str
    label: str
    required: bool
    aliases: tuple[str, ...]


# The AR sheet's data columns. The work columns (Claim Status, Notes, ...) are filled in the portal instead.
COLUMNS = (
    Column("patient_name", "Patient", True, ("patient", "patientname")),
    Column("service_date", "Service Date", True, ("servicedate", "dateofservice", "dos")),
    Column("subscriber_id", "Subscriber ID", True, ("subscriberid", "memberid")),
    Column("patient_dob", "Patient DOB", False, ("patientdob", "patientdateofbirth")),
    Column(
        "insurance_carrier", "Insurance Carrier", True, ("insurancecarrier", "insurance", "carrier", "payer")
    ),
    Column("subscriber_name", "Subscriber", False, ("subscriber", "subscribername")),
    Column("subscriber_dob", "Subscriber DOB", False, ("subscriberdob", "subscriberdateofbirth")),
    Column("billed", "Billed", True, ("billed", "billedamount")),
)

DATE_FORMATS = ("%m-%d-%y", "%m/%d/%y", "%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d")


class SheetError(Exception):
    """The whole file can't be used (unreadable, missing columns, no rows). The message is shown as-is."""


@dataclass
class ParsedRow:
    row_number: int
    patient_name: str
    service_date: date
    subscriber_id: str
    patient_dob: date | None
    insurance_carrier: str
    subscriber_name: str | None
    subscriber_dob: date | None
    billed: Decimal


@dataclass
class RowProblem:
    row_number: int
    column: str
    message: str


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    total_rows: int = 0


def _key(header: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header or "").lower())


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("not a date")


def _money(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, int | float | Decimal):
        amount = Decimal(str(value))
    else:
        text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            amount = Decimal(text)
        except InvalidOperation as error:
            raise ValueError("not a number") from error
    return amount.quantize(Decimal("0.01"))


def _read_rows(data: bytes, file_name: str) -> list[list[object]]:
    name = file_name.lower()
    if name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        return [list(row) for row in csv.reader(io.StringIO(text))]
    if name.endswith(".xlsx"):
        try:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as error:  # noqa: BLE001 - any failure means the file can't be read
            raise SheetError("The file couldn't be opened as an Excel workbook.") from error
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    raise SheetError("Upload an .xlsx or .csv file.")


def _find_header(rows: list[list[object]]) -> tuple[int, dict[str, int]]:
    """The header is the first row (within the first 10) that names most of the expected columns."""
    for index, row in enumerate(rows[:10]):
        positions: dict[str, int] = {}
        for position, header in enumerate(row):
            key = _key(header)
            for column in COLUMNS:
                if key in column.aliases and column.field not in positions:
                    positions[column.field] = position
        if len(positions) >= 4:
            return index, positions
    raise SheetError(
        "No header row found. The first rows must contain the column names (Patient, Service Date, …)."
    )


def _parse_row(
    cells: dict[str, object], row_number: int, today: date
) -> tuple[ParsedRow | None, list[RowProblem]]:
    problems: list[RowProblem] = []

    def problem(label: str, message: str) -> None:
        problems.append(RowProblem(row_number, label, message))

    def required_text(field_name: str, label: str) -> str:
        value = _text(cells[field_name])
        if value is None:
            problem(label, f"{label} is missing.")
            return ""
        if len(value) > 200:
            problem(label, f"{label} is longer than 200 characters.")
        return value

    def checked_date(field_name: str, label: str, *, required: bool = False) -> date | None:
        try:
            value = _date(cells[field_name])
        except ValueError:
            problem(label, f"{label} is not a valid date.")
            return None
        if value is None:
            if required:
                problem(label, f"{label} is missing.")
            return None
        if value > today:
            problem(label, f"{label} is in the future.")
        elif value.year < 1900:
            problem(label, f"{label} is before 1900.")
        return value

    patient = required_text("patient_name", "Patient")
    service_date = checked_date("service_date", "Service Date", required=True)
    subscriber_id = required_text("subscriber_id", "Subscriber ID").upper().replace(" ", "")
    patient_dob = checked_date("patient_dob", "Patient DOB")
    carrier = required_text("insurance_carrier", "Insurance Carrier")
    subscriber = _text(cells["subscriber_name"])
    subscriber_dob = checked_date("subscriber_dob", "Subscriber DOB")
    try:
        billed = _money(cells["billed"])
    except ValueError:
        billed = None
        problem("Billed", "Billed is not a number.")
    else:
        if billed is None:
            problem("Billed", "Billed is missing.")
        elif billed < 0:
            problem("Billed", "Billed can't be negative.")
        elif billed > Decimal("9999999.99"):
            problem("Billed", "Billed is too large.")

    if problems or service_date is None or billed is None:
        return None, problems
    return (
        ParsedRow(
            row_number=row_number,
            patient_name=patient,
            service_date=service_date,
            subscriber_id=subscriber_id,
            patient_dob=patient_dob,
            insurance_carrier=carrier,
            subscriber_name=subscriber,
            subscriber_dob=subscriber_dob,
            billed=billed,
        ),
        problems,
    )


def parse_sheet(data: bytes, file_name: str, *, today: date) -> ParseResult:
    rows = _read_rows(data, file_name)
    header_index, positions = _find_header(rows)
    missing = [c.label for c in COLUMNS if c.required and c.field not in positions]
    if missing:
        raise SheetError(f"Required columns are missing: {', '.join(missing)}.")

    result = ParseResult()
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        cells = {
            c.field: row[positions[c.field]] if positions.get(c.field, len(row)) < len(row) else None
            for c in COLUMNS
        }
        if all(_text(v) is None for v in cells.values()):
            continue  # blank line
        result.total_rows += 1
        if result.total_rows > MAX_ROWS:
            raise SheetError(f"The file has more than {MAX_ROWS:,} rows. Split it into smaller files.")
        parsed, problems = _parse_row(cells, row_number, today)
        result.problems.extend(problems)
        if parsed is not None:
            result.rows.append(parsed)

    if result.total_rows == 0:
        raise SheetError("The file has a header row but no data rows.")
    return result
