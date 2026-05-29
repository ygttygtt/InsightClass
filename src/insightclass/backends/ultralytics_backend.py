from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from insightclass.backends.base import DetectorBackend
from insightclass.evaluation.experiments import save_experiment_record
from insightclass.exceptions import DependencyMissingError
from insightclass.optional import has_package, require_package
from insightclass.schemas import DetectionRecord, ExperimentRecord, FramePrediction, InferenceConfig, TrainingConfig
from insightclass.utils.paths import ensure_dir
from insightclass.utils.serialization import save_json


class UltralyticsBackend(DetectorBackend):
    name = "ultralytics"

    def _get_model(self, weights_path: str):
        require_package("ultralytics", "Ultralytics backend")
        from ultralytics import YOLO

        return YOLO(weights_path)

    def train(self, config: TrainingConfig) -> ExperimentRecord:
        model = self._get_model(config.model_weights)
        project_dir = ensure_dir(config.resolved_project_dir())
        train_args = {
            "data": config.data_config_path,
            "imgsz": config.image_size,
            "epochs": config.epochs,
            "batch": config.batch_size,
            "device": config.device,
            "project": str(project_dir),
            "name": config.run_name,
            "seed": config.seed,
            "patience": config.patience,
            "workers": config.workers,
        }
        train_args.update(config.extra_args)
        result = model.train(**train_args)

        # ultralytics >= 8.2: model.train() returns None; find run_dir from disk
        if result is not None and hasattr(result, "save_dir"):
            run_dir = Path(result.save_dir)
            metrics = self._extract_metrics(result)
        else:
            run_dir = self._find_run_dir(project_dir, config.run_name)
            metrics = self._extract_metrics_from_csv(run_dir / "results.csv")

        artifacts = self.export_artifacts(str(run_dir))
        record = ExperimentRecord(
            experiment_id=run_dir.name,
            backend=self.name,
            model_weights=config.model_weights,
            data_version=Path(config.data_config_path).stem,
            class_names=self._read_class_names(config.data_config_path),
            hyperparameters=config.to_dict(),
            metrics=metrics,
            artifacts=artifacts,
        )
        save_experiment_record(run_dir / "experiment_record.json", record)
        save_json(run_dir / "train_args_snapshot.json", train_args)
        return record

    def validate(self, config: TrainingConfig) -> dict[str, Any]:
        model = self._get_model(config.model_weights)
        val_args = {
            "data": config.data_config_path,
            "imgsz": config.image_size,
            "batch": config.batch_size,
            "device": config.device,
            "project": str(config.resolved_project_dir()),
            "name": f"{config.run_name}_val",
        }
        val_args.update(config.extra_args)
        result = model.val(**val_args)

        if result is not None and hasattr(result, "save_dir"):
            run_dir = Path(result.save_dir)
            metrics = self._extract_metrics(result)
        else:
            run_dir = self._find_run_dir(config.resolved_project_dir(), f"{config.run_name}_val")
            metrics = self._extract_metrics_from_csv(run_dir / "results.csv")

        metrics["save_dir"] = str(run_dir.resolve())
        save_json(run_dir / "validation_metrics.json", metrics)
        return metrics

    def predict_images_or_video(self, config: InferenceConfig) -> str:
        model = self._get_model(config.weights_path)
        output_dir = ensure_dir(config.output_dir)
        predict_args = {
            "source": config.source,
            "conf": config.confidence,
            "iou": config.iou,
            "imgsz": config.image_size,
            "device": config.device,
            "project": str(output_dir.parent.resolve()),
            "name": output_dir.name,
            "save": True,
            "save_txt": False,
            "save_conf": True,
        }
        predict_args.update(config.extra_args)
        result = model.predict(**predict_args)
        save_dir = result[0].save_dir if result else output_dir
        save_json(Path(save_dir) / "inference_config_snapshot.json", config.to_dict())
        return str(Path(save_dir).resolve())

    def load_predictions_as_sv_detections(self, config: InferenceConfig) -> list[FramePrediction]:
        model = self._get_model(config.weights_path)
        start = time.time()
        results = model.predict(
            source=config.source,
            conf=config.confidence,
            iou=config.iou,
            imgsz=config.image_size,
            device=config.device,
            stream=False,
            verbose=False,
            save=False,
        )
        elapsed = time.time() - start
        predictions: list[FramePrediction] = []
        for frame_index, result in enumerate(results):
            names = result.names
            detections: list[DetectionRecord] = []
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy().astype(int)
                for xyxy, confidence, class_id in zip(boxes, confidences, class_ids, strict=False):
                    detections.append(
                        DetectionRecord(
                            xyxy=np.asarray(xyxy).tolist(),
                            confidence=float(confidence),
                            class_id=int(class_id),
                            class_name=str(names[int(class_id)]),
                        )
                    )
            predictions.append(
                FramePrediction(
                    frame_index=frame_index,
                    source_path=str(getattr(result, "path", config.source)),
                    detections=detections,
                )
            )
        inference_meta = {
            "latency_sec_total": round(elapsed, 4),
            "frame_count": len(predictions),
            "latency_sec_per_frame": round(elapsed / len(predictions), 4) if predictions else None,
        }
        ensure_dir(config.output_dir)
        save_json(Path(config.output_dir) / "inference_latency.json", inference_meta)
        return predictions

    def export_artifacts(self, experiment_dir: str) -> dict[str, str]:
        run_dir = Path(experiment_dir)
        artifact_map = {
            "run_dir": str(run_dir.resolve()),
            "results_csv": str((run_dir / "results.csv").resolve()) if (run_dir / "results.csv").exists() else "",
            "best_weights": str((run_dir / "weights" / "best.pt").resolve())
            if (run_dir / "weights" / "best.pt").exists()
            else "",
            "last_weights": str((run_dir / "weights" / "last.pt").resolve())
            if (run_dir / "weights" / "last.pt").exists()
            else "",
            "confusion_matrix": str((run_dir / "confusion_matrix.png").resolve())
            if (run_dir / "confusion_matrix.png").exists()
            else "",
            "results_plot": str((run_dir / "results.png").resolve()) if (run_dir / "results.png").exists() else "",
        }
        return artifact_map

    def to_supervision_detections(self, frame_prediction: FramePrediction):
        if not has_package("supervision"):
            raise DependencyMissingError(
                "Converting predictions to sv.Detections requires the optional dependency 'supervision'."
            )
        import supervision as sv

        if not frame_prediction.detections:
            return sv.Detections.empty()
        xyxy = np.array([detection.xyxy for detection in frame_prediction.detections], dtype=float)
        confidence = np.array([detection.confidence for detection in frame_prediction.detections], dtype=float)
        class_id = np.array([detection.class_id for detection in frame_prediction.detections], dtype=int)
        labels = [detection.class_name for detection in frame_prediction.detections]
        return sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id,
            data={"class_name": np.array(labels, dtype=object)},
        )

    @staticmethod
    def _extract_metrics(result: Any) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for attr_name in ("fitness", "speed"):
            if hasattr(result, attr_name):
                metrics[attr_name] = getattr(result, attr_name)
        box_metrics = getattr(getattr(result, "box", None), "mean_results", None)
        if callable(box_metrics):
            values = box_metrics()
            metric_names = ["precision", "recall", "mAP50", "mAP50_95"]
            metrics.update({name: float(value) for name, value in zip(metric_names, values, strict=False)})
        results_dict = getattr(result, "results_dict", None)
        if isinstance(results_dict, dict):
            for key, value in results_dict.items():
                if isinstance(value, (int, float, str)):
                    metrics[key] = value
        return metrics

    @staticmethod
    def _find_run_dir(project_dir: Path, run_name: str) -> Path:
        """Find the actual run directory, handling ultralytics suffix like 'run_name-2'."""
        exact = project_dir / run_name
        if exact.exists():
            return exact
        # ultralytics appends -N suffix when directory already exists
        candidates = sorted(project_dir.glob(f"{run_name}-*"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return candidates[-1]
        raise FileNotFoundError(f"Training run directory not found under {project_dir} for '{run_name}'")

    @staticmethod
    def _extract_metrics_from_csv(csv_path: Path) -> dict[str, Any]:
        """Read final epoch metrics from ultralytics results.csv."""
        import csv as csv_mod

        metrics: dict[str, Any] = {}
        if not csv_path.exists():
            return metrics
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            rows = list(reader)
        if not rows:
            return metrics
        last = rows[-1]
        for key, value in last.items():
            key = key.strip()
            try:
                metrics[key] = float(value)
            except (ValueError, TypeError):
                metrics[key] = value.strip() if isinstance(value, str) else value
        return metrics

    @staticmethod
    def _read_class_names(data_config_path: str) -> list[str]:
        from insightclass.utils.serialization import load_yaml

        data = load_yaml(data_config_path)
        names = data.get("names", {})
        if isinstance(names, list):
            return [str(item) for item in names]
        if isinstance(names, dict):
            return [str(names[index]) for index in sorted(names)]
        return []
