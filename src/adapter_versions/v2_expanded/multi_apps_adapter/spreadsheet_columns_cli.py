from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Sequence


def _read_csv_column(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(65536)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(stream, dialect))
    invalid = [index + 1 for index, row in enumerate(rows) if len(row) != 1]
    if invalid:
        raise ValueError(
            f"{path} contains more than one CSV column at rows {invalid[:20]}"
        )
    return [row[0] for row in rows]


def _convert_to_csv(source: Path, output_directory: Path) -> Path:
    if source.suffix.casefold() == ".csv":
        return source
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if executable is None:
        raise RuntimeError("LibreOffice command-line executable is unavailable")
    profile = output_directory / "profile"
    profile.mkdir()
    completed = subprocess.run(
        [
            executable,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--convert-to",
            "csv",
            "--outdir",
            str(output_directory),
            str(source),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=180,
    )
    converted = output_directory / f"{source.stem}.csv"
    if completed.returncode != 0 or not converted.is_file():
        raise RuntimeError(
            f"LibreOffice failed to convert {source}: {completed.stdout[-2000:]}"
        )
    return converted


def read_single_columns(input_paths: Sequence[Path]) -> list[list[str]]:
    columns: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix="osworld-spreadsheet-columns-") as temp:
        root = Path(temp)
        for index, source in enumerate(input_paths):
            if not source.is_file():
                raise FileNotFoundError(f"input spreadsheet does not exist: {source}")
            source_directory = root / f"source-{index:02d}"
            source_directory.mkdir()
            columns.append(_read_csv_column(_convert_to_csv(source, source_directory)))
    lengths = [len(column) for column in columns]
    if len(set(lengths)) != 1:
        raise ValueError(f"input columns have different row counts: {lengths}")
    return columns


def write_concatenated_csv(
    columns: Sequence[Sequence[str]],
    output_path: Path,
    separator: str,
    *,
    overwrite: bool,
) -> dict[str, object]:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        raise FileNotFoundError(f"output parent does not exist: {output_path.parent}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream, lineterminator="\n")
            for values in zip(*columns, strict=True):
                writer.writerow([separator.join(values)])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    data = output_path.read_bytes()
    return {
        "operation": "spreadsheet.concatenate_single_columns",
        "output_path": str(output_path),
        "source_count": len(columns),
        "row_count": len(columns[0]),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--separator-json", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if len(args.input) < 2:
        parser.error("at least two --input paths are required")
    separator = json.loads(args.separator_json)
    if not isinstance(separator, str) or "\r" in separator or "\n" in separator:
        parser.error("--separator-json must encode a string without line breaks")
    columns = read_single_columns([Path(value).expanduser() for value in args.input])
    summary = write_concatenated_csv(
        columns,
        Path(args.output).expanduser(),
        separator,
        overwrite=args.overwrite,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
