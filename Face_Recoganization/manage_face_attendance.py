from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from face_attendance import (
    FaceAttendanceService,
    FaceModuleConfig,
    LiveCameraEnrollment,
    LiveCameraRecognition,
    OpenCVFaceEngine,
    SQLiteFaceAttendanceRepository,
)


def build_service(database_path: str) -> FaceAttendanceService:
    config = FaceModuleConfig(database_path=Path(database_path))
    repository = SQLiteFaceAttendanceRepository(config)
    engine = OpenCVFaceEngine(config)
    return FaceAttendanceService(repository=repository, engine=engine, config=config)


def to_json(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_json(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Face attendance module utility")
    parser.add_argument(
        "--database",
        default="attendance_face.db",
        help="SQLite database path for attendance and embeddings.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the required attendance tables.")

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an image before enrollment or recognition.",
    )
    validate_parser.add_argument("--image", required=True)

    camera_enroll_parser = subparsers.add_parser(
        "camera-enroll",
        help="Open the webcam and capture 5 approved enrollment samples.",
    )
    camera_enroll_parser.add_argument("--employee-id", required=True)
    camera_enroll_parser.add_argument("--full-name", required=True)
    camera_enroll_parser.add_argument("--employee-code")
    camera_enroll_parser.add_argument("--camera-index", type=int, default=0)

    enroll_parser = subparsers.add_parser("enroll", help="Enroll 5 face samples for an employee.")
    enroll_parser.add_argument("--employee-id", required=True)
    enroll_parser.add_argument("--full-name", required=True)
    enroll_parser.add_argument("--employee-code")
    enroll_parser.add_argument(
        "--sample",
        action="append",
        required=True,
        help="Path to a face sample image. Provide exactly 5 values.",
    )

    recognize_parser = subparsers.add_parser(
        "recognize",
        help="Recognize an employee from an image and optionally mark attendance.",
    )
    recognize_parser.add_argument("--image", required=True)
    recognize_parser.add_argument("--source", default="camera")
    recognize_parser.add_argument(
        "--no-mark",
        action="store_true",
        help="Run recognition without marking attendance.",
    )

    camera_recognize_parser = subparsers.add_parser(
        "camera-recognize",
        help="Open the webcam and run live recognition for attendance.",
    )
    camera_recognize_parser.add_argument("--camera-index", type=int, default=0)
    camera_recognize_parser.add_argument("--source", default="live_camera")

    settings_parser = subparsers.add_parser(
        "update-settings",
        help="Update duplicate-window, checkout-gap, or match threshold values.",
    )
    settings_parser.add_argument("--duplicate-window", type=int)
    settings_parser.add_argument("--min-checkout-gap", type=int)
    settings_parser.add_argument("--match-threshold", type=float)

    args = parser.parse_args()
    service = build_service(args.database)

    if args.command == "init-db":
        service.initialize()
        result = {"status": "ok", "database": args.database}
    elif args.command == "validate":
        result = service.validate_image(args.image)
    elif args.command == "camera-enroll":
        result = LiveCameraEnrollment(service).run(
            employee_id=args.employee_id,
            full_name=args.full_name,
            employee_code=args.employee_code,
            camera_index=args.camera_index,
        )
    elif args.command == "enroll":
        result = service.enroll_employee(
            employee_id=args.employee_id,
            full_name=args.full_name,
            employee_code=args.employee_code,
            sample_images=args.sample,
        )
    elif args.command == "camera-recognize":
        result = LiveCameraRecognition(service).run(
            camera_index=args.camera_index,
            source=args.source,
        )
    elif args.command == "recognize":
        result = service.recognize(
            image_input=args.image,
            source=args.source,
            mark_attendance=not args.no_mark,
        )
    else:
        service.update_settings(
            duplicate_window_minutes=args.duplicate_window,
            min_checkout_gap_minutes=args.min_checkout_gap,
            match_threshold=args.match_threshold,
        )
        result = {"status": "ok", "message": "Settings updated."}

    print(json.dumps(to_json(result), indent=2))


if __name__ == "__main__":
    main()
