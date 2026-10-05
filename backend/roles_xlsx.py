"""Write the scraper's findings to an Excel workbook.

Four sheets, in the order you read them:

* **Roles** — one row per open role that matched your filters, with a clickable
  apply link.
* **Filtered search links** — one row per company: the results page the scraper
  opened *after* applying your filters. This is emitted even when extraction
  failed, so every company on the run still hands you a usable link.
* **Needs attention** — the companies the scraper could not read, with the
  snapshot directory to look at.
* **Summary** — what filters were used and what the run found.

Pure function over plain dicts, like docx_export.py: nothing here touches the
network, the browser or data/, so selftest.py can exercise it against a temp
directory.

Scraped text is untrusted. openpyxl turns any string beginning with "=" into a
formula, so every cell goes through `_text`, which pins it to a string — a job
titled "=HYPERLINK(...)" must stay a title.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROLES_SHEET = "Roles"
LINKS_SHEET = "Filtered search links"
FAILURES_SHEET = "Needs attention"
HELP_SHEET = "Needs your help"
SUMMARY_SHEET = "Summary"

ROLE_COLUMNS = (
    ("Company", 22), ("Tier", 9), ("Title", 52), ("Location", 28),
    ("Posted", 12), ("Seniority", 11), ("Experience", 11), ("Apply link", 60), ("Source", 9),
    ("New", 6),
)
LINK_COLUMNS = (
    ("Company", 22), ("Tier", 9), ("Filtered results page", 80),
    ("Roles found", 12), ("Status", 28), ("Reviewed", 20),
)
FAILURE_COLUMNS = (
    ("Company", 22), ("Problem", 22), ("Detail", 70), ("Snapshot", 60),
)
HELP_COLUMNS = (
    ("Company", 22), ("Tier", 9), ("Careers page", 60), ("Why it needs you", 80), ("Since", 12),
)

_HEADER_FILL = PatternFill("solid", fgColor="E7ECF3")


def _text(ws, row: int, column: int, value: Any):
    cell = ws.cell(row=row, column=column)
    cell.value = "" if value is None else value
    if isinstance(cell.value, str):
        cell.data_type = "s"
    return cell


def _link(ws, row: int, column: int, url: str | None):
    cell = _text(ws, row, column, url or "")
    if url and url.lower().startswith(("http://", "https://")):
        cell.hyperlink = url
        cell.font = Font(color="0563C1", underline="single")
    return cell


def _header(ws, columns: Iterable[tuple[str, int]]) -> None:
    for index, (title, width) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=index, value=title)
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A2"


def _finish(ws, columns: tuple, rows: int) -> None:
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(rows, 1) + 1}"


def write(
    path: Path,
    roles: list[dict[str, Any]],
    links: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    summary: list[tuple[str, Any]],
    help_rows: Iterable[dict[str, Any]] = (),
) -> Path:
    """Build the workbook and save it atomically-enough (single save call)."""
    wb = Workbook()

    ws = wb.active
    ws.title = ROLES_SHEET
    _header(ws, ROLE_COLUMNS)
    for row, role in enumerate(roles, start=2):
        _text(ws, row, 1, role.get("company"))
        _text(ws, row, 2, role.get("tier"))
        _text(ws, row, 3, role.get("title"))
        _text(ws, row, 4, role.get("location"))
        _text(ws, row, 5, role.get("posted"))
        _text(ws, row, 6, role.get("seniority"))
        _text(ws, row, 7, role.get("experience"))
        _link(ws, row, 8, role.get("url"))
        _text(ws, row, 9, role.get("strategy"))
        _text(ws, row, 10, "new" if role.get("is_new") else "")
    _finish(ws, ROLE_COLUMNS, len(roles))

    ws = wb.create_sheet(LINKS_SHEET)
    _header(ws, LINK_COLUMNS)
    for row, entry in enumerate(links, start=2):
        _text(ws, row, 1, entry.get("company"))
        _text(ws, row, 2, entry.get("tier"))
        _link(ws, row, 3, entry.get("url"))
        _text(ws, row, 4, entry.get("found"))
        _text(ws, row, 5, entry.get("status"))
        _text(ws, row, 6, entry.get("reviewed"))
    _finish(ws, LINK_COLUMNS, len(links))

    ws = wb.create_sheet(FAILURES_SHEET)
    _header(ws, FAILURE_COLUMNS)
    for row, failure in enumerate(failures, start=2):
        _text(ws, row, 1, failure.get("company"))
        _text(ws, row, 2, failure.get("problem"))
        _text(ws, row, 3, failure.get("detail"))
        _text(ws, row, 4, failure.get("snapshot"))
    _finish(ws, FAILURE_COLUMNS, len(failures))

    ws = wb.create_sheet(HELP_SHEET)
    _header(ws, HELP_COLUMNS)
    help_list = list(help_rows)
    for row, entry in enumerate(help_list, start=2):
        _text(ws, row, 1, entry.get("company"))
        _text(ws, row, 2, entry.get("tier"))
        _link(ws, row, 3, entry.get("url"))
        _text(ws, row, 4, entry.get("why"))
        _text(ws, row, 5, entry.get("since"))
    _finish(ws, HELP_COLUMNS, len(help_list))

    ws = wb.create_sheet(SUMMARY_SHEET)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 90
    for row, (label, value) in enumerate(summary, start=1):
        _text(ws, row, 1, label).font = Font(bold=True)
        _text(ws, row, 2, value)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


_EXPORT_NAME = re.compile(r"^open-roles-(\d{4}-\d{2}-\d{2})(-.+)?\.xlsx$")


def latest_before(directory: Path, current: Path) -> Path | None:
    """The newest earlier export *of the same selection* — the "new since last run" baseline.

    A `--tier faang` run is named `open-roles-<date>-faang.xlsx`. Measured against
    yesterday's full run, every role it found outside FAANG would read as gone and
    every one inside as old news; like has to be compared with like.
    """
    wanted = _EXPORT_NAME.match(current.name)
    if not wanted:
        return None
    candidates = []
    for path in directory.glob("open-roles-*.xlsx"):
        match = _EXPORT_NAME.match(path.name)
        if match and match.group(2) == wanted.group(2) and match.group(1) < wanted.group(1):
            candidates.append((match.group(1), path))
    return max(candidates)[1] if candidates else None


def read_previous_urls(path: Path | None) -> set[str]:
    """Apply links from an earlier export's Roles sheet; empty if unreadable."""
    if not path or not path.exists():
        return set()
    try:
        wb = load_workbook(path, read_only=True)
        ws = wb[ROLES_SHEET]
        # Found by header, not position: the Experience column moved it from 7 to 8,
        # and a workbook from before then must still count as "seen".
        header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        column = list(header).index("Apply link") + 1 if "Apply link" in header else 7
        return {
            str(row[0]).strip()
            for row in ws.iter_rows(min_row=2, min_col=column, max_col=column, values_only=True)
            if row and row[0]
        }
    except Exception:  # a corrupt or half-open previous export must not stop a run
        return set()
