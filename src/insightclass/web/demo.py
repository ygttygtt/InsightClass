"""Unified InsightClass demo app: inference + training results viewer."""

from __future__ import annotations

import base64
import csv
import io
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from insightclass.evaluation.experiments import collect_experiment_records
from insightclass.utils.serialization import load_json, load_yaml
from insightclass.web.model_cache import clear_cache, get_model, preload_model

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

def _load_display_names(class_config: Path) -> dict[str, str]:
    if not class_config.exists():
        return {}
    data = load_yaml(str(class_config))
    raw = data.get("display_names", {})
    return {str(k): str(v) for k, v in raw.items()}


def _get_all_experiments(experiments_root: Path) -> list[dict]:
    """List all experiments with weights."""
    if not experiments_root.exists():
        return []
    records = collect_experiment_records(str(experiments_root))
    result = []
    for rec in records:
        exp_id = rec["experiment_id"]
        exp_dir = experiments_root / exp_id
        weights_path = exp_dir / "weights" / "best.pt"
        record_path = exp_dir / "experiment_record.json"
        full_record = load_json(record_path) if record_path.exists() else {}
        result.append({
            "experiment_id": exp_id,
            "weights_path": str(weights_path.resolve()) if weights_path.exists() else "",
            "model_weights": rec.get("model_weights", ""),
            "class_names": full_record.get("class_names", []),
            "hyperparameters": full_record.get("hyperparameters", {}),
            "metrics": full_record.get("metrics", {}),
            "has_results_csv": (exp_dir / "results.csv").exists(),
            "has_confusion_matrix": (exp_dir / "confusion_matrix.png").exists(),
            "has_results_png": (exp_dir / "results.png").exists(),
        })
    return result


def _get_font(size: int = 18) -> ImageFont.FreeTypeFont:
    """Get a font that supports Chinese characters."""
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑 Windows
        "C:/Windows/Fonts/simhei.ttf",      # 黑体 Windows
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Noto Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # 文泉驿 Linux
        "/System/Library/Fonts/PingFang.ttc",  # macOS
    ]
    for p in font_paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_detections(image: np.ndarray, results, display_names: dict[str, str]) -> np.ndarray:
    """Draw bounding boxes and labels on image using PIL (supports Chinese)."""
    if results is None or len(results) == 0:
        return image
    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return image

    boxes = result.boxes.xyxy.cpu().numpy()
    confs = result.boxes.conf.cpu().numpy()
    cls_ids = result.boxes.cls.cpu().numpy().astype(int)
    names = result.names if result.names else {}

    colors = [
        (56, 189, 248),   # blue
        (244, 114, 182),  # pink
        (52, 211, 153),   # green
        (251, 191, 36),   # yellow
        (167, 139, 250),  # purple
    ]

    # Convert cv2 image (BGR) to PIL image (RGB)
    img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)
    font = _get_font(18)

    for i in range(len(boxes)):
        cls_id = cls_ids[i]
        conf = confs[i]
        x1, y1, x2, y2 = boxes[i].astype(int)
        color = colors[cls_id % len(colors)]
        class_name = names.get(cls_id, str(cls_id))
        display = display_names.get(class_name, class_name)
        label = f"{display} {conf:.2f}"

        # Draw box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

        # Draw label background
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([x1, y1 - th - 8, x1 + tw + 8, y1], fill=color)
        draw.text((x1 + 4, y1 - th - 4), label, fill=(0, 0, 0), font=font)

    # Convert back to cv2 (BGR)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def create_app(experiments_root: Path, class_config: Path) -> FastAPI:
    app = FastAPI(title="InsightClass Demo")
    display_names = _load_display_names(class_config)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request=request, name="demo.html")

    @app.get("/api/experiments")
    async def list_experiments():
        return JSONResponse(_get_all_experiments(experiments_root))

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
            raise HTTPException(404, "Not found")
        return FileResponse(img_path, media_type="image/png")

    @app.get("/api/experiments/{exp_id}/results.png")
    async def get_results_png(exp_id: str):
        img_path = experiments_root / exp_id / "results.png"
        if not img_path.exists():
            raise HTTPException(404, "Not found")
        return FileResponse(img_path, media_type="image/png")

    @app.post("/api/detect/image")
    async def detect_image(
        image: UploadFile = File(...),
        model: str = Form(default=""),
        confidence: float = Form(default=0.25),
        iou: float = Form(default=0.45),
    ):
        if not model:
            raise HTTPException(400, "请选择一个模型")

        t0 = time.time()
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "无法解析图片")

        # Save to temp file for YOLO
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            cv2.imwrite(tmp.name, img)
            tmp_path = tmp.name

        try:
            yolo = get_model(model)
            results = yolo.predict(source=tmp_path, conf=confidence, iou=iou, verbose=False, save=False)

            # Draw detections
            annotated = _draw_detections(img, results, display_names)

            # Encode to base64
            _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 92])
            img_b64 = base64.b64encode(buf).decode('utf-8')

            # Extract detection info
            detections = []
            if results and results[0].boxes is not None:
                result = results[0]
                boxes = result.boxes.xyxy.cpu().numpy()
                confs = result.boxes.conf.cpu().numpy()
                cls_ids = result.boxes.cls.cpu().numpy().astype(int)
                names = result.names if result.names else {}
                for j in range(len(boxes)):
                    cn = names.get(int(cls_ids[j]), str(int(cls_ids[j])))
                    detections.append({
                        "class_name": cn,
                        "display_name": display_names.get(cn, cn),
                        "confidence": round(float(confs[j]), 4),
                        "xyxy": boxes[j].tolist(),
                    })
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        latency = round((time.time() - t0) * 1000, 1)
        return JSONResponse({
            "image": f"data:image/jpeg;base64,{img_b64}",
            "detections": detections,
            "latency_ms": latency,
        })

    return app
