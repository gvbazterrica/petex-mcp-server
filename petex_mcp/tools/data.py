"""Data import tool for production data files."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from petex_mcp.errors.exceptions import PetexValidationError


# Column patterns for production data recognition
COLUMN_PATTERNS = {
    "date": ["date", "fecha", "time", "timestamp"],
    "oil_rate": ["oil_rate", "qo", "oil_prod", "tasa_aceite"],
    "gas_rate": ["gas_rate", "qg", "gas_prod", "tasa_gas"],
    "water_rate": ["water_rate", "qw", "water_prod", "tasa_agua"],
    "gor": ["gor", "rga"],
    "water_cut": ["water_cut", "bsw", "fw", "corte_agua"],
    "bhp": ["bhp", "pwf", "fbhp", "presion_fondo"],
    "whp": ["whp", "pwh", "thp", "presion_cabezal"],
    "reservoir_pressure": ["reservoir_pressure", "pr", "pres", "presion_yacimiento"],
    "cumulative_oil": ["cumulative_oil", "np", "cum_oil", "acumulado_aceite"],
    "cumulative_gas": ["cumulative_gas", "gp", "cum_gas", "acumulado_gas"],
    "cumulative_water": ["cumulative_water", "wp", "cum_water", "acumulado_agua"],
}


def _detect_delimiter(content: str) -> str:
    """Auto-detect delimiter from file content."""
    lines = content.strip().split("\n")[:5]
    if not lines:
        return ","

    candidates = [",", "\t", ";", " "]
    best = ","
    best_score = 0

    for delim in candidates:
        counts = [line.count(delim) for line in lines]
        if counts and min(counts) > 0 and max(counts) == min(counts):
            if min(counts) > best_score:
                best_score = min(counts)
                best = delim
    return best


def _match_column(header: str) -> Optional[str]:
    """Match a header to a known column field."""
    stripped = header.strip().lower()
    # Remove unit annotations like (bbl/d) or [psia]
    import re
    stripped = re.sub(r"\s*[\(\[].*?[\)\]]", "", stripped).strip()

    for field_name, patterns in COLUMN_PATTERNS.items():
        for pattern in patterns:
            if stripped == pattern.lower():
                return field_name
    return None


def _detect_units(headers: list[str]) -> dict[str, str]:
    """Detect units from header annotations."""
    import re
    units: dict[str, str] = {}
    for header in headers:
        match = re.search(r"[\(\[](.*?)[\)\]]", header)
        if match:
            field = _match_column(header)
            if field:
                units[field] = match.group(1)
    return units


@dataclass
class ImportResult:
    """Result from importing production data."""

    records_loaded: int
    date_range: tuple[str, str] | None
    columns_mapped: dict[str, str]
    rows_skipped: int
    quality_issues: list[str]
    units_applied: dict[str, str]


async def import_data(
    file_path: str,
    target_tool: str = "mbal",
    session=None,
) -> ImportResult:
    """Import production data from CSV/TXT file."""
    path = Path(file_path)

    if not path.exists():
        raise PetexValidationError(
            error_message=f"File not found: {file_path}",
            error_code="FILE_NOT_FOUND",
            suggested_action="Verify the file path is correct.",
            original_params={"file_path": file_path},
        )

    if path.is_dir():
        raise PetexValidationError(
            error_message=f"Path is a directory, not a file: {file_path}",
            error_code="NOT_A_FILE",
            suggested_action="Provide a path to a CSV or TXT file.",
            original_params={"file_path": file_path},
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    if not content.strip():
        raise PetexValidationError(
            error_message="File is empty.",
            error_code="EMPTY_FILE",
            suggested_action="Provide a file with production data.",
            original_params={"file_path": file_path},
        )

    delimiter = _detect_delimiter(content)
    lines = content.strip().split("\n")
    headers = [h.strip() for h in lines[0].split(delimiter)]

    # Map columns
    column_mapping: dict[int, str] = {}
    unrecognized: list[str] = []
    quality_issues: list[str] = []

    for idx, header in enumerate(headers):
        field = _match_column(header)
        if field:
            column_mapping[idx] = field
        else:
            unrecognized.append(header)

    if unrecognized:
        quality_issues.append(f"Unrecognized columns: {', '.join(unrecognized)}")

    # Detect units
    units = _detect_units(headers)

    # Parse data rows
    records: list[dict] = []
    rows_skipped = 0
    has_gaps = False

    for i, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        values = [v.strip() for v in line.split(delimiter)]
        record: dict = {}
        for idx, field_name in column_mapping.items():
            if idx < len(values):
                val = values[idx]
                if val == "" or val is None:
                    has_gaps = True
                    record[field_name] = None
                else:
                    record[field_name] = val
            else:
                has_gaps = True
                record[field_name] = None
        records.append(record)

    if has_gaps:
        quality_issues.append("Data gaps detected in some rows")

    # Determine date range
    date_range = None
    if "date" in [column_mapping.get(i) for i in column_mapping]:
        date_col_idx = next(i for i, f in column_mapping.items() if f == "date")
        dates = [r.get("date") for r in records if r.get("date")]
        if dates:
            date_range = (dates[0], dates[-1])

    # Reverse mapping for output: field_name -> original_header
    columns_mapped_output: dict[str, str] = {}
    for idx, field_name in column_mapping.items():
        columns_mapped_output[headers[idx]] = field_name

    # Update session if provided
    if session is not None:
        session.operation_history.append({
            "tool_name": "import_data",
            "params": {"file_path": file_path, "target_tool": target_tool},
        })

    return ImportResult(
        records_loaded=len(records),
        date_range=date_range,
        columns_mapped=columns_mapped_output,
        rows_skipped=rows_skipped,
        quality_issues=quality_issues,
        units_applied=units,
    )
