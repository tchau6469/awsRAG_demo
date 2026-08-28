#!/usr/bin/env python3
"""Validate a parks CSV and upsert it into the Compose PostgreSQL service."""

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIELDS = ("park_code", "name", "state_code", "established_year")
PARK_CODE_PATTERN = re.compile(r"^[a-z0-9]{4}$")
STATE_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and import park records into the Compose PostgreSQL database."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=PROJECT_ROOT / "data" / "parks.csv",
        help="CSV file to import (default: data/parks.csv)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=PROJECT_ROOT / "db" / "schema.sql",
        help="SQL schema file to apply before importing (default: db/schema.sql)",
    )
    return parser.parse_args()


def read_and_validate(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if tuple(reader.fieldnames or ()) != EXPECTED_FIELDS:
            raise ValueError(
                f"expected CSV headers {EXPECTED_FIELDS}, got {tuple(reader.fieldnames or ())}"
            )

        rows: list[dict[str, str]] = []
        seen_codes: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            park_code = row["park_code"].strip()
            name = row["name"].strip()
            state_code = row["state_code"].strip()
            year_text = row["established_year"].strip()

            if not PARK_CODE_PATTERN.fullmatch(park_code):
                raise ValueError(f"line {line_number}: invalid park_code {park_code!r}")
            if park_code in seen_codes:
                raise ValueError(f"line {line_number}: duplicate park_code {park_code!r}")
            if not name:
                raise ValueError(f"line {line_number}: name cannot be empty")
            if not STATE_CODE_PATTERN.fullmatch(state_code):
                raise ValueError(f"line {line_number}: invalid state_code {state_code!r}")
            try:
                established_year = int(year_text)
            except ValueError as error:
                raise ValueError(
                    f"line {line_number}: established_year must be an integer"
                ) from error
            if not 1872 <= established_year <= 2100:
                raise ValueError(
                    f"line {line_number}: established_year must be between 1872 and 2100"
                )

            seen_codes.add(park_code)
            rows.append(
                {
                    "park_code": park_code,
                    "name": name,
                    "state_code": state_code,
                    "established_year": str(established_year),
                }
            )

    if not rows:
        raise ValueError("CSV contains no park records")
    return rows


def render_csv(rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPECTED_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def import_rows(schema_path: Path, rows: list[dict[str, str]]) -> None:
    schema = schema_path.read_text(encoding="utf-8").rstrip()
    csv_payload = render_csv(rows).rstrip("\n")
    sql = f"""\\set ON_ERROR_STOP on
BEGIN;
{schema}

CREATE TEMP TABLE parks_import (LIKE public.parks INCLUDING DEFAULTS);
\\copy parks_import (park_code, name, state_code, established_year) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
{csv_payload}
\\.

INSERT INTO public.parks (park_code, name, state_code, established_year)
SELECT park_code, name, state_code, established_year
FROM parks_import
ON CONFLICT (park_code) DO UPDATE SET
    name = EXCLUDED.name,
    state_code = EXCLUDED.state_code,
    established_year = EXCLUDED.established_year;
COMMIT;
"""

    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"',
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, input=sql, text=True, check=True)


def main() -> int:
    args = parse_args()
    try:
        rows = read_and_validate(args.csv)
        import_rows(args.schema, rows)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1

    print(f"Imported {len(rows)} parks into public.parks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
