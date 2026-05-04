from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

from app.core.config import settings
from app.models.annotation import Annotation
from app.models.asset import Asset


def _write_generated_bytes(relative_path: str, content: bytes) -> tuple[str, str]:
    dest = settings.media_root_path / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return relative_path, f"/media/{relative_path}"


def _write_generated_image(relative_path: str, image: Image.Image) -> tuple[str, str]:
    dest = settings.media_root_path / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG")
    return relative_path, f"/media/{relative_path}"


def _get_media_path(asset: Asset) -> Path | None:
    if asset.storage_path:
        candidate = settings.media_root_path / asset.storage_path
        if candidate.is_file():
            return candidate
    return None


def _load_font(size: int) -> ImageFont.ImageFont:
    font_candidates = [
        "PingFang SC.ttc",
        "PingFang.ttc",
        "Hiragino Sans GB.ttc",
        "STHeiti Medium.ttc",
        "Arial Unicode.ttf",
        "Arial Unicode MS.ttf",
        "NotoSansCJK-Regular.ttc",
        "NotoSansSC-Regular.otf",
        "Arial.ttf",
    ]
    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _parse_color(value: str | None, default: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if not value:
        return default
    try:
        rgb = ImageColor.getrgb(value)
        return rgb[0], rgb[1], rgb[2], default[3]
    except ValueError:
        return default


def _image_size_from_asset(asset: Asset) -> tuple[int, int]:
    meta = asset.metadata_json or {}
    width = int(meta.get("width") or 1280)
    height = int(meta.get("height") or 720)
    return max(width, 1), max(height, 1)


def _blank_canvas(size: tuple[int, int], color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", size, color)


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], color: tuple[int, int, int, int], width: int) -> None:
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head_len = max(12, width * 3)
    left = (
        end[0] - head_len * math.cos(angle - math.pi / 6),
        end[1] - head_len * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - head_len * math.cos(angle + math.pi / 6),
        end[1] - head_len * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=color)


def _sample_quadratic_bezier(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    steps: int = 24,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for idx in range(steps + 1):
        t = idx / steps
        x = ((1 - t) ** 2) * start[0] + (2 * (1 - t) * t * control[0]) + (t ** 2) * end[0]
        y = ((1 - t) ** 2) * start[1] + (2 * (1 - t) * t * control[1]) + (t ** 2) * end[1]
        points.append((x, y))
    return points


def _sample_cubic_bezier(
    start: tuple[float, float],
    control1: tuple[float, float],
    control2: tuple[float, float],
    end: tuple[float, float],
    steps: int = 24,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for idx in range(steps + 1):
        t = idx / steps
        x = (
            ((1 - t) ** 3) * start[0]
            + 3 * ((1 - t) ** 2) * t * control1[0]
            + 3 * (1 - t) * (t ** 2) * control2[0]
            + (t ** 3) * end[0]
        )
        y = (
            ((1 - t) ** 3) * start[1]
            + 3 * ((1 - t) ** 2) * t * control1[1]
            + 3 * (1 - t) * (t ** 2) * control2[1]
            + (t ** 3) * end[1]
        )
        points.append((x, y))
    return points


def _draw_fabric_path(
    draw: ImageDraw.ImageDraw,
    path_commands: list[list[float | str]],
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    if not path_commands:
        return

    current: tuple[float, float] | None = None
    subpath_start: tuple[float, float] | None = None
    sampled_points: list[tuple[float, float]] = []

    for command in path_commands:
        if not command:
            continue
        code = str(command[0]).upper()
        values = [float(item) for item in command[1:]]

        if code == "M" and len(values) >= 2:
            current = (values[0], values[1])
            subpath_start = current
            sampled_points.append(current)
        elif code == "L" and current is not None and len(values) >= 2:
            current = (values[0], values[1])
            sampled_points.append(current)
        elif code == "Q" and current is not None and len(values) >= 4:
            control = (values[0], values[1])
            end = (values[2], values[3])
            sampled_points.extend(_sample_quadratic_bezier(current, control, end)[1:])
            current = end
        elif code == "C" and current is not None and len(values) >= 6:
            control1 = (values[0], values[1])
            control2 = (values[2], values[3])
            end = (values[4], values[5])
            sampled_points.extend(_sample_cubic_bezier(current, control1, control2, end)[1:])
            current = end
        elif code == "Z" and current is not None and subpath_start is not None:
            sampled_points.append(subpath_start)
            current = subpath_start

    if len(sampled_points) >= 2:
        draw.line(sampled_points, fill=color, width=width, joint="curve")


def _draw_canvas_objects(image: Image.Image, canvas_json: dict[str, Any] | None) -> None:
    draw = ImageDraw.Draw(image)
    objects = (canvas_json or {}).get("objects") or []
    font = _load_font(24)
    for obj in objects:
        obj_type = (obj.get("type") or "").lower()
        stroke = _parse_color(obj.get("stroke"), (255, 80, 80, 255))
        fill = _parse_color(obj.get("fill"), (255, 80, 80, 64))
        width = int(obj.get("strokeWidth") or 4)
        left = float(obj.get("left") or obj.get("x") or 0)
        top = float(obj.get("top") or obj.get("y") or 0)
        obj_width = float(obj.get("width") or obj.get("rx") or obj.get("radius") or 120)
        obj_height = float(obj.get("height") or obj.get("ry") or obj.get("radius") or 80)

        if obj_type in {"rect", "rectangle"}:
            draw.rectangle([left, top, left + obj_width, top + obj_height], outline=stroke, fill=fill, width=width)
        elif obj_type in {"ellipse", "circle"}:
            radius = float(obj.get("radius") or min(obj_width, obj_height) / 2)
            draw.ellipse([left, top, left + radius * 2, top + radius * 2], outline=stroke, fill=fill, width=width)
        elif obj_type in {"line"}:
            x1 = float(obj.get("x1", left))
            y1 = float(obj.get("y1", top))
            x2 = float(obj.get("x2", left + obj_width))
            y2 = float(obj.get("y2", top + obj_height))
            draw.line([x1, y1, x2, y2], fill=stroke, width=width)
        elif obj_type in {"path"}:
            _draw_fabric_path(draw, obj.get("path") or [], stroke, width)
        elif obj_type in {"arrow"}:
            x1 = float(obj.get("x1", left))
            y1 = float(obj.get("y1", top))
            x2 = float(obj.get("x2", left + obj_width))
            y2 = float(obj.get("y2", top + obj_height))
            _draw_arrow(draw, (x1, y1), (x2, y2), stroke, width)
        elif obj_type in {"text", "textbox", "i-text"}:
            text = str(obj.get("text") or obj.get("value") or "")
            draw.text((left, top), text, font=font, fill=stroke)
        else:
            draw.rectangle([left, top, left + obj_width, top + obj_height], outline=stroke, width=width)


def _extract_video_frame(asset: Asset, frame_number: int | None = None, timestamp_seconds: float | None = None) -> Image.Image | None:
    media_path = _get_media_path(asset)
    if media_path is None:
        return None
    cap = cv2.VideoCapture(str(media_path))
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if frame_number and frame_number > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(frame_number - 1, 0))
        elif timestamp_seconds is not None and fps > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(timestamp_seconds, 0) * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb).convert("RGBA")
    finally:
        cap.release()


def _load_base_image(asset: Asset, annotation: Annotation | None = None) -> Image.Image:
    media_path = _get_media_path(asset)
    if asset.media_type == "image" and media_path and media_path.is_file():
        return Image.open(media_path).convert("RGBA")
    if asset.media_type == "video":
        frame = _extract_video_frame(asset, annotation.frame_number if annotation else None, float(annotation.timestamp_seconds) if annotation and annotation.timestamp_seconds is not None else None)
        if frame is not None:
            return frame
    return _blank_canvas(_image_size_from_asset(asset), (18, 24, 38, 255))


def _save_overlay_and_merged(base_dir: Path, overlay: Image.Image, merged: Image.Image) -> dict[str, str]:
    overlay_path, overlay_url = _write_generated_image(str(base_dir / "overlay.png"), overlay)
    merged_path, merged_url = _write_generated_image(str(base_dir / "merged.png"), merged)
    return {
        "overlay_path": overlay_path,
        "overlay_url": overlay_url,
        "merged_path": merged_path,
        "merged_url": merged_url,
    }


def generate_annotation_artifacts(annotation: Annotation, asset: Asset) -> dict[str, str]:
    base_dir = Path("generated") / "annotations" / str(annotation.id)
    base_image = _load_base_image(asset, annotation)
    overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    _draw_canvas_objects(overlay, annotation.canvas_json)

    merged = Image.alpha_composite(base_image, overlay)
    return _save_overlay_and_merged(base_dir, overlay, merged)


def _placeholder_thumbnail(asset: Asset) -> Image.Image:
    image = Image.new("RGBA", (960, 540), (18, 32, 50, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 936, 516), radius=24, outline=(90, 209, 255, 255), width=4)
    draw.polygon([(410, 190), (410, 350), (570, 270)], fill=(90, 209, 255, 255))
    font_big = _load_font(28)
    font_small = _load_font(18)
    meta = asset.metadata_json or {}
    draw.text((36, 80), asset.original_name, font=font_big, fill=(229, 238, 247, 255))
    draw.text((36, 120), f"Duration: {meta.get('durationSeconds', 'unknown')}s", font=font_small, fill=(168, 187, 207, 255))
    draw.text((36, 150), f"Resolution: {meta.get('width', '?')}x{meta.get('height', '?')}", font=font_small, fill=(168, 187, 207, 255))
    draw.text((36, 180), f"Stage: {asset.stage_key}", font=font_small, fill=(168, 187, 207, 255))
    return image


def extract_video_metadata(asset: Asset) -> dict[str, Any]:
    media_path = _get_media_path(asset)
    current = dict(asset.metadata_json or {})
    if media_path is None:
        return current
    cap = cv2.VideoCapture(str(media_path))
    try:
        if not cap.isOpened():
            return current
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (frame_count / fps) if fps > 0 and frame_count > 0 else 0
        current.update(
            {
                "width": width,
                "height": height,
                "fps": round(fps, 3) if fps else None,
                "frameCount": frame_count,
                "durationSeconds": round(duration, 3) if duration else None,
            }
        )
        return current
    finally:
        cap.release()


def extract_image_metadata(asset: Asset) -> dict[str, Any]:
    media_path = _get_media_path(asset)
    current = dict(asset.metadata_json or {})
    if media_path is None:
        return current
    with Image.open(media_path) as image:
        current.update({"width": image.width, "height": image.height})
    return current


def generate_video_thumbnail(asset: Asset) -> dict[str, str]:
    frame = _extract_video_frame(asset, frame_number=1)
    image = frame if frame is not None else _placeholder_thumbnail(asset)
    base_dir = Path("generated") / "thumbnails" / str(asset.project_id)
    thumbnail_path, thumbnail_url = _write_generated_image(str(base_dir / f"asset_{asset.id}.png"), image)
    return {"thumbnail_path": thumbnail_path, "thumbnail_url": thumbnail_url}
