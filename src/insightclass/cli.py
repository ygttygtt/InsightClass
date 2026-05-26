from __future__ import annotations

import argparse
from pathlib import Path

from insightclass.backends.factory import build_backend
from insightclass.data.manifest import create_manifest, load_manifest, save_manifest
from insightclass.data.video_ops import extract_frames_from_manifest
from insightclass.data.yolo import inspect_yolo_dataset, save_inspection_report, write_yolo_dataset_yaml
from insightclass.evaluation.experiments import export_experiment_summary
from insightclass.schemas import InferenceConfig, TrainingConfig
from insightclass.utils.paths import ensure_dir
from insightclass.utils.serialization import load_yaml
from insightclass.visualization.pipeline import VisualizationPipeline


def _load_training_config(path: str) -> TrainingConfig:
    return TrainingConfig(**load_yaml(path))


def _load_inference_config(path: str) -> InferenceConfig:
    return InferenceConfig(**load_yaml(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="insightclass", description="InsightClass baseline toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    split_parser = subparsers.add_parser("create-manifest", help="Create a video-level dataset manifest")
    split_parser.add_argument("--config", required=True, help="Path to dataset manifest config template")
    split_parser.add_argument("--output", required=True, help="Where to save the generated manifest YAML")

    extract_parser = subparsers.add_parser("extract-frames", help="Extract frames according to a dataset manifest")
    extract_parser.add_argument("--manifest", required=True)
    extract_parser.add_argument("--fps", type=float, default=1.0)
    extract_parser.add_argument("--max-frames-per-video", type=int, default=None)

    inspect_parser = subparsers.add_parser("inspect-yolo", help="Inspect YOLO dataset labels")
    inspect_parser.add_argument("--dataset-root", required=True)
    inspect_parser.add_argument("--class-config", required=True)
    inspect_parser.add_argument("--output", required=True)
    inspect_parser.add_argument("--min-box-area", type=float, default=0.0005)

    yaml_parser = subparsers.add_parser("write-yolo-yaml", help="Generate Ultralytics dataset YAML")
    yaml_parser.add_argument("--dataset-root", required=True)
    yaml_parser.add_argument("--class-config", required=True)
    yaml_parser.add_argument("--output", required=True)

    train_parser = subparsers.add_parser("train", help="Run model training")
    train_parser.add_argument("--config", required=True)

    val_parser = subparsers.add_parser("validate", help="Run model validation")
    val_parser.add_argument("--config", required=True)

    predict_parser = subparsers.add_parser("predict", help="Run inference on images or video")
    predict_parser.add_argument("--config", required=True)

    render_parser = subparsers.add_parser("render-first-frame", help="Render the first frame prediction with supervision")
    render_parser.add_argument("--config", required=True)

    compare_parser = subparsers.add_parser("compare-experiments", help="Export experiment summary CSV")
    compare_parser.add_argument("--experiments-root", required=True)
    compare_parser.add_argument("--output", required=True)

    return parser


def _load_class_names(path: str) -> tuple[list[str], dict[str, str]]:
    data = load_yaml(path)
    classes = data.get("classes", [])
    display_names = data.get("display_names", {})
    if not isinstance(classes, list):
        raise ValueError("class config 'classes' must be a list")
    return [str(item) for item in classes], {str(key): str(value) for key, value in display_names.items()}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "create-manifest":
        config = load_yaml(args.config)
        classes, display_names = _load_class_names(config["class_config"])
        manifest = create_manifest(
            dataset_name=config["dataset_name"],
            dataset_version=config["dataset_version"],
            raw_videos_dir=config["raw_videos_dir"],
            processed_dir=config["processed_dir"],
            classes=classes,
            display_names=display_names,
            seed=int(config.get("seed", 42)),
            train_ratio=float(config.get("train_ratio", 0.7)),
            val_ratio=float(config.get("val_ratio", 0.2)),
            notes=str(config.get("notes", "")),
        )
        save_manifest(args.output, manifest)
        print(f"Saved manifest to {Path(args.output).resolve()}")
        return 0

    if args.command == "extract-frames":
        manifest = load_manifest(args.manifest)
        metadata_path = extract_frames_from_manifest(
            manifest=manifest,
            fps=args.fps,
            max_frames_per_video=args.max_frames_per_video,
        )
        print(f"Saved frame index to {metadata_path.resolve()}")
        return 0

    if args.command == "inspect-yolo":
        class_names, _ = _load_class_names(args.class_config)
        report = inspect_yolo_dataset(args.dataset_root, class_names, min_box_area=args.min_box_area)
        report_path = save_inspection_report(args.output, report)
        print(f"Saved inspection report to {report_path.resolve()}")
        return 0

    if args.command == "write-yolo-yaml":
        class_names, _ = _load_class_names(args.class_config)
        yaml_path = write_yolo_dataset_yaml(args.dataset_root, class_names, args.output)
        print(f"Saved dataset yaml to {yaml_path.resolve()}")
        return 0

    if args.command == "train":
        config = _load_training_config(args.config)
        backend = build_backend(config.backend)
        record = backend.train(config)
        print(f"Training complete: {record.experiment_id}")
        return 0

    if args.command == "validate":
        config = _load_training_config(args.config)
        backend = build_backend(config.backend)
        metrics = backend.validate(config)
        print(metrics)
        return 0

    if args.command == "predict":
        config = _load_inference_config(args.config)
        backend = build_backend(config.backend)
        output_dir = backend.predict_images_or_video(config)
        print(f"Prediction outputs saved to {output_dir}")
        return 0

    if args.command == "render-first-frame":
        config = _load_inference_config(args.config)
        backend = build_backend(config.backend)
        predictions = backend.load_predictions_as_sv_detections(config)
        if not predictions:
            raise RuntimeError("No predictions were produced.")
        first = predictions[0]
        source_path = Path(first.source_path)
        output_dir = ensure_dir(config.output_dir)
        pipeline = VisualizationPipeline()
        if source_path.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}:
            rendered_path = pipeline.render_video_first_frame(
                video_path=str(source_path),
                frame_prediction=first,
                output_path=str(output_dir / f"{source_path.stem}_first_frame_annotated.jpg"),
            )
        elif source_path.is_dir():
            raise RuntimeError("render-first-frame expects an image file or a video source.")
        else:
            rendered_path = pipeline.render_image(
                image_path=str(source_path),
                frame_prediction=first,
                output_path=str(output_dir / f"{source_path.stem}_annotated.jpg"),
            )
        print(f"Saved preview to {rendered_path.resolve()}")
        return 0

    if args.command == "compare-experiments":
        csv_path = export_experiment_summary(args.experiments_root, args.output)
        print(f"Saved summary to {csv_path.resolve()}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 1
