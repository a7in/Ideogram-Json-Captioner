from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


CAPTION_EXTENSIONS = (".json", ".txt", ".caption")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
ELEMENT_TYPES = ("obj", "text")
STYLE_MODES = ("photo", "art_style")
COMMON_MEDIA = (
    "photograph",
    "illustration",
    "3d_render",
    "painting",
    "graphic_design",
    "digital_art",
    "screen_print",
    "collage",
)

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def default_caption() -> dict[str, Any]:
    return {
        "high_level_description": "",
        "style_description": {
            "aesthetics": "",
            "lighting": "",
            "photo": "",
            "medium": "photograph",
        },
        "compositional_deconstruction": {
            "background": "",
            "elements": [],
        },
    }


def caption_from_plain_text(text: str) -> dict[str, Any]:
    caption = default_caption()
    caption["high_level_description"] = text.strip()
    return caption


def parse_palette_text(text: str, limit: int) -> tuple[list[str], list[str]]:
    values: list[str] = []
    invalid: list[str] = []
    for raw in re.split(r"[,\s]+", text.strip()):
        if not raw:
            continue
        item = raw.upper()
        if HEX_COLOR_RE.match(item):
            if len(values) < limit:
                values.append(item)
            else:
                invalid.append(raw)
        else:
            invalid.append(raw)
    return values, invalid


def normalize_palette(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        return parse_palette_text(value, limit)[0]
    if not isinstance(value, list):
        return []
    colors: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        color = item.strip().upper()
        if HEX_COLOR_RE.match(color):
            colors.append(color)
        if len(colors) >= limit:
            break
    return colors


def palette_to_text(value: Any) -> str:
    return ", ".join(normalize_palette(value, 99))


def normalize_bbox(value: Any) -> list[int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        y1, x1, y2, x2 = [int(round(float(v))) for v in value]
    except (TypeError, ValueError):
        return None

    y1 = max(0, min(1000, y1))
    x1 = max(0, min(1000, x1))
    y2 = max(0, min(1000, y2))
    x2 = max(0, min(1000, x2))

    top, bottom = sorted((y1, y2))
    left, right = sorted((x1, x2))
    if top == bottom or left == right:
        return None
    return [top, left, bottom, right]


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _style_mode(style: dict[str, Any]) -> str:
    mode = style.get("_mode")
    if mode in STYLE_MODES:
        return mode
    if "art_style" in style and "photo" not in style:
        return "art_style"
    return "photo"


def normalize_caption(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return default_caption()

    caption: dict[str, Any] = {}
    caption["high_level_description"] = _as_str(data.get("high_level_description", ""))

    style_in = data.get("style_description")
    if isinstance(style_in, dict):
        mode = _style_mode(style_in)
        style: dict[str, Any] = {
            "aesthetics": _as_str(style_in.get("aesthetics", "")),
            "lighting": _as_str(style_in.get("lighting", "")),
        }
        if mode == "photo":
            style["photo"] = _as_str(style_in.get("photo", ""))
            style["medium"] = _as_str(style_in.get("medium", "photograph")) or "photograph"
        else:
            style["medium"] = _as_str(style_in.get("medium", "illustration")) or "illustration"
            style["art_style"] = _as_str(style_in.get("art_style", ""))
        colors = normalize_palette(style_in.get("color_palette"), 16)
        if colors:
            style["color_palette"] = colors
        caption["style_description"] = style
    else:
        caption["style_description"] = deepcopy(default_caption()["style_description"])

    comp_in = data.get("compositional_deconstruction")
    comp_in = comp_in if isinstance(comp_in, dict) else {}
    elements_in = comp_in.get("elements", [])
    elements: list[dict[str, Any]] = []
    if isinstance(elements_in, list):
        for item in elements_in:
            if not isinstance(item, dict):
                continue
            element_type = item.get("type")
            if element_type not in ELEMENT_TYPES:
                element_type = "text" if "text" in item else "obj"
            element: dict[str, Any] = {"type": element_type}
            bbox = normalize_bbox(item.get("bbox"))
            if bbox:
                element["bbox"] = bbox
            if element_type == "text":
                element["text"] = _as_str(item.get("text", ""))
            element["desc"] = _as_str(item.get("desc", item.get("description", "")))
            colors = normalize_palette(item.get("color_palette"), 5)
            if colors:
                element["color_palette"] = colors
            elements.append(element)

    caption["compositional_deconstruction"] = {
        "background": _as_str(comp_in.get("background", "")),
        "elements": elements,
    }
    return caption


def serialize_caption(data: dict[str, Any]) -> str:
    caption = normalize_caption(data)
    return json.dumps(caption, separators=(",", ":"), ensure_ascii=False)


def parse_caption_text(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Caption JSON must be an object.")
    return normalize_caption(parsed)
