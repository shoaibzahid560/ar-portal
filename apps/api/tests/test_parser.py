"""The AR sheet reader, against the synthetic sample files (same layout as the real sheets, fake data)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.uploads.parser import SheetError, parse_sheet

FIXTURES = Path(__file__).parent / "fixtures"
WEEK_1 = FIXTURES / "Sample_Practice_AR-HBS_10-22-2026_sheet.xlsx"
TODAY = date(2026, 10, 30)


def csv_bytes(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


HEADER = (
    "SR#,Patient,Service Date,Subscriber ID,Patient DOB,Insurance Carrier,Subscriber,Subscriber DOB,Billed"
)


def test_reads_every_line_of_the_sample_sheet() -> None:
    result = parse_sheet(WEEK_1.read_bytes(), WEEK_1.name, today=TODAY)

    assert result.total_rows == 87
    assert len(result.rows) == 87 and not result.problems
    first = result.rows[0]
    assert first.row_number == 2
    assert isinstance(first.service_date, date) and isinstance(first.billed, Decimal)


def test_numeric_subscriber_ids_become_text() -> None:
    result = parse_sheet(WEEK_1.read_bytes(), WEEK_1.name, today=TODAY)

    assert all(isinstance(r.subscriber_id, str) and r.subscriber_id for r in result.rows)


def test_headers_are_matched_despite_spaces_case_and_typos_elsewhere() -> None:
    data = csv_bytes(
        "  sr# , PATIENT , service date , subscriber id , patient dob , insurance carrier , subscriber , "
        "subscriber dob , billed , Patient Responsiblity",
        ",Test Patient 01,10-15-26,0123,01-02-80,Aetna,Test Patient 01,01-02-80,$1,234.50,",
    )
    data = data.replace(b"$1,234.50", b'"$1,234.50"')

    [row] = parse_sheet(data, "sheet.csv", today=TODAY).rows

    assert row.subscriber_id == "0123"
    assert row.billed == Decimal("1234.50")
    assert row.service_date == date(2026, 10, 15)


def test_each_problem_is_reported_by_row_without_repeating_the_value() -> None:
    data = csv_bytes(
        HEADER,
        ",Test Patient 01,not-a-date,123,,Aetna,,,100",
        ",,10-15-26,123,,Aetna,,,abc",
        ",Test Patient 03,12-31-29,123,,Aetna,,,-5",
        ",Test Patient 04,10-15-26,123,,Aetna,,,99.5",
    )

    result = parse_sheet(data, "sheet.csv", today=TODAY)

    assert result.total_rows == 4 and len(result.rows) == 1
    messages = {(p.row_number, p.message) for p in result.problems}
    assert (2, "Service Date is not a valid date.") in messages
    assert (3, "Patient is missing.") in messages
    assert (3, "Billed is not a number.") in messages
    assert (4, "Service Date is in the future.") in messages
    assert (4, "Billed can't be negative.") in messages
    assert all("abc" not in p.message and "not-a-date" not in p.message for p in result.problems)


def test_blank_lines_are_ignored() -> None:
    data = csv_bytes(HEADER, ",,,,,,,,", ",Test Patient 01,10-15-26,123,,Aetna,,,100", ",,,,,,,,")

    result = parse_sheet(data, "sheet.csv", today=TODAY)

    assert result.total_rows == 1 and len(result.rows) == 1


@pytest.mark.parametrize(
    ("content", "name", "message"),
    [
        (b"not a spreadsheet", "sheet.xlsx", "couldn't be opened"),
        (b"a,b,c\n1,2,3\n", "sheet.csv", "No header row found"),
        (
            csv_bytes("Patient,Service Date,Insurance Carrier,Subscriber,Patient DOB", "x,10-15-26,y,z,"),
            "s.csv",
            "Subscriber ID, Billed",
        ),
        (csv_bytes(HEADER), "sheet.csv", "no data rows"),
        (b"anything", "sheet.pdf", "Upload an .xlsx or .csv file"),
    ],
)
def test_unusable_files_are_rejected_with_a_clear_reason(content: bytes, name: str, message: str) -> None:
    with pytest.raises(SheetError, match=message):
        parse_sheet(content, name, today=TODAY)
