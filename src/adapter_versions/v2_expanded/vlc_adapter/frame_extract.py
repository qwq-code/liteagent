from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


def frame_index_for_time(time_seconds: float, fps: float, frame_count: int) -> int:
    if time_seconds < 0:
        raise RuntimeError("time seconds must be non-negative")
    if fps <= 0:
        raise RuntimeError("video FPS is unavailable")
    frame_index = round(time_seconds * fps)
    if frame_count > 0:
        frame_index = min(frame_index, frame_count - 1)
    return frame_index


def extract_frame(
    input_path: Path, output_path: Path, frame_index: int
) -> dict[str, object]:
    capture = cv2.VideoCapture(str(input_path))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open video: {input_path}")
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count > 0 and frame_index >= frame_count:
            raise RuntimeError(
                f"frame index {frame_index} is outside the video frame count {frame_count}"
            )
        if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            raise RuntimeError(f"OpenCV could not seek to frame {frame_index}")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"OpenCV could not decode frame {frame_index}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), frame):
            raise RuntimeError(f"OpenCV could not write image: {output_path}")
        return {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "frame_index": frame_index,
            "frame_count": frame_count,
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "opencv_version": cv2.__version__,
        }
    finally:
        capture.release()


def extract_frame_at_time(
    input_path: Path,
    output_path: Path,
    time_seconds: float,
) -> dict[str, object]:
    capture = cv2.VideoCapture(str(input_path))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open video: {input_path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
    frame_index = frame_index_for_time(time_seconds, fps, frame_count)
    return {
        **extract_frame(input_path, output_path, frame_index),
        "fps": fps,
        "time_seconds": time_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--frame-index", type=int)
    selector.add_argument("--time-seconds", type=float)
    args = parser.parse_args()
    if args.frame_index is not None and args.frame_index < 0:
        raise SystemExit("frame index must be non-negative")
    if args.time_seconds is not None:
        result = extract_frame_at_time(args.input, args.output, args.time_seconds)
    else:
        result = extract_frame(args.input, args.output, args.frame_index)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
