"""FastAPI app for viewing training experiment results locally."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from insightclass.evaluation.experiments import collect_experiment_records
from insightclass.utils.serialization import load_json

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def create_app(experiments_root: Path) -> FastAPI:
    app = FastAPI(title="InsightClass Experiment Viewer")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="experiments.html",
        )

    @app.get("/api/experiments")
    async def list_experiments():
        root = experiments_root
        if not root.exists():
            return JSONResponse([])
        records = collect_experiment_records(root)
        result = []
        for rec in records:
            exp_id = rec["experiment_id"]
            exp_dir = root / exp_id
            record_path = exp_dir / "experiment_record.json"
            full_record = load_json(record_path) if record_path.exists() else {}
            result.append({
                "experiment_id": exp_id,
                "backend": rec.get("backend", ""),
                "model_weights": rec.get("model_weights", ""),
                "data_version": rec.get("data_version", ""),
                "class_names": full_record.get("class_names", []),
                "hyperparameters": full_record.get("hyperparameters", {}),
                "metrics": full_record.get("metrics", {}),
                "has_results_csv": (exp_dir / "results.csv").exists(),
                "has_confusion_matrix": (exp_dir / "confusion_matrix.png").exists(),
                "has_results_png": (exp_dir / "results.png").exists(),
            })
        return JSONResponse(result)

    @app.get("/api/experiments/{exp_id}/results.csv")
    async def get_results_csv(exp_id: str):
        csv_path = experiments_root / exp_id / "results.csv"
        if not csv_path.exists():
            raise HTTPException(404, "results.csv not found")
        text = csv_path.read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        return JSONResponse({"columns": reader.fieldnames or [], "rows": rows})

    @app.get("/api/experiments/{exp_id}/confusion_matrix")
    async def get_confusion_matrix(exp_id: str):
        img_path = experiments_root / exp_id / "confusion_matrix.png"
        if not img_path.exists():
            raise HTTPException(404, "confusion_matrix.png not found")
        return FileResponse(img_path, media_type="image/png")

    @app.get("/api/experiments/{exp_id}/results.png")
    async def get_results_png(exp_id: str):
        img_path = experiments_root / exp_id / "results.png"
        if not img_path.exists():
            raise HTTPException(404, "results.png not found")
        return FileResponse(img_path, media_type="image/png")

    return app
