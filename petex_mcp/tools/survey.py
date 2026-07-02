"""Well survey/trajectory loader for PROSPER deviation tables.

Loads well trajectory data (MD, Inclination, Azimuth, TVD) from CSV/TXT files
and generates OpenServer commands to populate the PROSPER deviation survey table.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from petex_mcp.models.commands import OpenServerCommand
from petex_mcp.models.outputs import ExecutionMetadata
from petex_mcp.script.generator import ScriptGenerator
from petex_mcp.errors.exceptions import PetexValidationError


# Column patterns for survey data recognition
SURVEY_COLUMN_PATTERNS = {
    "md": ["md", "measured_depth", "prof_med", "profundidad_medida", "depth"],
    "inclination": ["incl", "inclination", "inc", "inclinacion", "angle", "dev"],
    "azimuth": ["azimuth", "azi", "az", "azimut", "direction"],
    "tvd": ["tvd", "true_vertical_depth", "prof_vert", "profundidad_vertical"],
    "dls": ["dls", "dogleg", "dog_leg", "dogleg_severity", "pata_de_perro"],
}


def _match_survey_column(header: str) -> Optional[str]:
    """Match a header to a known survey column field."""
    stripped = header.strip().lower()
    for field_name, patterns in SURVEY_COLUMN_PATTERNS.items():
        for pattern in patterns:
            if stripped == pattern.lower():
                return field_name
    return None


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


def _create_metadata(start_time: float, model_path: str) -> ExecutionMetadata:
    """Create execution metadata."""
    duration = time.perf_counter() - start_time
    return ExecutionMetadata(
        duration_seconds=round(duration, 6),
        petex_version=None,
        model_file_path=model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def load_well_survey(
    file_path: str,
    model_path: str = "well.Out",
    script_only: bool = True,
) -> dict:
    """Load well survey/trajectory data from CSV/TXT into PROSPER deviation table.

    Reads a survey file with MD, Inclination, Azimuth (and optionally TVD, DLS),
    auto-detects columns, and generates OpenServer commands to populate the
    PROSPER deviation survey table.

    Args:
        file_path: Path to the CSV/TXT survey file.
        model_path: Path to the PROSPER model file to load the survey into.
        script_only: If True, only generate the script without executing.

    Returns:
        Dictionary with survey_points loaded, column mapping, generated script,
        metadata, and warnings.
    """
    start_time = time.perf_counter()
    warnings: list[str] = []

    # Validate file exists
    path = Path(file_path)
    if not path.exists():
        raise PetexValidationError(
            error_message=f"Survey file not found: {file_path}",
            error_code="FILE_NOT_FOUND",
            suggested_action="Verify the file path is correct.",
            original_params={"file_path": file_path},
        )

    # Read file
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    if not content.strip():
        raise PetexValidationError(
            error_message="Survey file is empty.",
            error_code="EMPTY_FILE",
            suggested_action="Provide a file with survey data (MD, Inclination, Azimuth).",
            original_params={"file_path": file_path},
        )

    # Detect delimiter and parse
    delimiter = _detect_delimiter(content)
    lines = content.strip().split("\n")
    headers = [h.strip() for h in lines[0].split(delimiter)]

    # Map columns
    column_mapping: dict[str, int] = {}
    unrecognized: list[str] = []

    for idx, header in enumerate(headers):
        field = _match_survey_column(header)
        if field:
            column_mapping[field] = idx
        else:
            unrecognized.append(header)

    # Validate required columns
    if "md" not in column_mapping:
        raise PetexValidationError(
            error_message="Required column 'MD' (Measured Depth) not found in survey file.",
            error_code="MISSING_COLUMN",
            suggested_action="Ensure the file has a column named MD, measured_depth, or prof_med.",
            original_params={"file_path": file_path, "headers": headers},
        )

    if "inclination" not in column_mapping:
        raise PetexValidationError(
            error_message="Required column 'Inclination' not found in survey file.",
            error_code="MISSING_COLUMN",
            suggested_action="Ensure the file has a column named Incl, inclination, or inclinacion.",
            original_params={"file_path": file_path, "headers": headers},
        )

    if "azimuth" not in column_mapping:
        raise PetexValidationError(
            error_message="Required column 'Azimuth' not found in survey file.",
            error_code="MISSING_COLUMN",
            suggested_action="Ensure the file has a column named Azimuth, Azi, or azimut.",
            original_params={"file_path": file_path, "headers": headers},
        )

    if unrecognized:
        warnings.append(f"Unrecognized columns (ignored): {', '.join(unrecognized)}")

    # Parse data rows
    survey_points: list[dict] = []
    for i, line in enumerate(lines[1:], start=1):
        if not line.strip():
            continue
        values = [v.strip() for v in line.split(delimiter)]
        try:
            point = {
                "md": float(values[column_mapping["md"]]),
                "inclination": float(values[column_mapping["inclination"]]),
                "azimuth": float(values[column_mapping["azimuth"]]),
            }
            if "tvd" in column_mapping and column_mapping["tvd"] < len(values):
                point["tvd"] = float(values[column_mapping["tvd"]])
            if "dls" in column_mapping and column_mapping["dls"] < len(values):
                point["dls"] = float(values[column_mapping["dls"]])
            survey_points.append(point)
        except (ValueError, IndexError):
            warnings.append(f"Row {i+1}: could not parse, skipped")

    if not survey_points:
        raise PetexValidationError(
            error_message="No valid survey points found in file.",
            error_code="NO_DATA",
            suggested_action="Check that the file contains numeric MD, Inclination, and Azimuth values.",
            original_params={"file_path": file_path},
        )

    # Generate OpenServer commands
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})")
    )

    # Set number of survey points
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.DEV.NumPoints",
            value=str(len(survey_points)),
        )
    )

    # Populate deviation survey table
    for i, point in enumerate(survey_points):
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"PROSPER.SIN.DEV.Data[{i}].MD",
                value=str(point["md"]),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"PROSPER.SIN.DEV.Data[{i}].Incl",
                value=str(point["inclination"]),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"PROSPER.SIN.DEV.Data[{i}].Azim",
                value=str(point["azimuth"]),
            )
        )
        if "tvd" in point:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"PROSPER.SIN.DEV.Data[{i}].TVD",
                    value=str(point["tvd"]),
                )
            )

    # Save file
    commands.append(
        OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()")
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Load Well Survey into PROSPER",
        commands=commands,
        description=f"Load {len(survey_points)} survey points from {Path(file_path).name}",
    )

    metadata = _create_metadata(start_time, model_path)

    # Summary
    md_range = (survey_points[0]["md"], survey_points[-1]["md"])
    max_incl = max(p["inclination"] for p in survey_points)
    tvd_at_td = survey_points[-1].get("tvd", None)

    return {
        "survey_points_loaded": len(survey_points),
        "md_range": md_range,
        "max_inclination": max_incl,
        "tvd_at_td": tvd_at_td,
        "columns_detected": {field: headers[idx] for field, idx in column_mapping.items()},
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
        "warnings": warnings,
    }
