from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from insightclass.schemas import ExperimentRecord
from insightclass.utils.paths import ensure_dir
from insightclass.utils.serialization import load_json, save_json


def save_experiment_record(path: str | Path, record: ExperimentRecord) -> Path:
    ensure_dir(Path(path).parent)
    save_json(path, record.to_dict())
    return Path(path)


def load_experiment_record(path: str | Path) -> ExperimentRecord:
    data = load_json(path)
    return ExperimentRecord(**data)


def collect_experiment_records(experiments_root: str | Path) -> list[dict[str, Any]]:
    root = Path(experiments_root)
    rows: list[dict[str, Any]] = []
    for record_path in sorted(root.rglob("experiment_record.json")):
        record = load_json(record_path)
        row = {
            "experiment_id": record["experiment_id"],
            "backend": record["backend"],
            "model_weights": record["model_weights"],
            "data_version": record["data_version"],
            "class_names": ",".join(record.get("class_names", [])),
        }
        for metric_name, metric_value in record.get("metrics", {}).items():
            row[metric_name] = metric_value
        rows.append(row)
    return rows


def export_experiment_summary(experiments_root: str | Path, output_csv: str | Path) -> Path:
    rows = collect_experiment_records(experiments_root)
    if not rows:
        raise FileNotFoundError(f"No experiment_record.json files found under {experiments_root}")
    fieldnames = sorted({key for row in rows for key in row.keys()})
    ensure_dir(Path(output_csv).parent)
    with Path(output_csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return Path(output_csv)
