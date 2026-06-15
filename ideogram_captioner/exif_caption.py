"""Import Ideogram caption JSON embedded in image EXIF / PNG metadata.

When a sidecar caption file is missing, ComfyUI workflow metadata may contain
the caption JSON in one of its text nodes. Text candidates are collected the
same way as image_caption_utility: per-node strings from the workflow, sorted
by length (largest first), top 5 tried in order.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.ExifTags import IFD, TAGS

from .schema import has_obj_bbox_annotation, normalize_caption, parse_caption_text

# Input keys that almost always carry actual prompt text.
_CONTENT_KEYS = {
    "text",
    "prompt",
    "value",
    "string",
    "positive",
    "text_g",
    "text_l",
    "wildcard_text",
    "populated_text",
}

_MIN_TEXT_LEN = 20

_UTILITY_CLASSES = {
    "jsonextractstring",
    "jsonextract",
    "stringreplace",
    "previewany",
    "previewtext",
    "showtext",
    "string",
    "stringconcatenate",
    "note",
    "markdownnote",
    "comfymathexpression",
    "customcombo",
}

_SKIP_NAME_HINTS = ("system", "negative")

_EXIF_CANDIDATE_LIMIT = 5


def _decode_user_comment(raw) -> str:
    if isinstance(raw, str):
        return raw
    if raw[:8] == b"UNICODE\x00":
        body = raw[8:]
        for enc in ("utf-16-be", "utf-16", "utf-16-le"):
            try:
                return body.decode(enc).rstrip("\x00")
            except UnicodeDecodeError:
                continue
    if raw[:8] == b"ASCII\x00\x00\x00":
        return raw[8:].decode("ascii", "replace").rstrip("\x00")
    return raw.decode("utf-8", "replace").rstrip("\x00")


def _collect_raw_fields(path: str | Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    img = Image.open(path)

    for key, val in img.info.items():
        if isinstance(val, str) and val.strip():
            fields[f"info:{key}"] = val

    exif = img.getexif()
    for tag, val in exif.items():
        name = TAGS.get(tag, str(tag))
        if isinstance(val, (str, bytes)) and val:
            fields[f"exif:{name}"] = val.decode("utf-8", "replace") if isinstance(val, bytes) else val

    try:
        sub = exif.get_ifd(IFD.Exif)
    except Exception:
        sub = {}
    for tag, val in sub.items():
        name = TAGS.get(tag, str(tag))
        if name == "UserComment" and val:
            fields["exif:UserComment"] = _decode_user_comment(val)
        elif isinstance(val, str) and val.strip():
            fields[f"exif:{name}"] = val

    return fields


def _load_comfy_prompt(raw: str) -> dict | None:
    text = raw.strip()
    for prefix in ("Prompt:", "Workflow:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict) and any(
        isinstance(value, dict) and "class_type" in value and "inputs" in value for value in data.values()
    ):
        return data
    return None


def _extract_comfy_nodes(prompt: dict) -> list[tuple[str, str]]:
    nodes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        if cls.lower() in _UTILITY_CLASSES:
            continue
        title = (node.get("_meta") or {}).get("title", "")
        name = f"{cls} {title}".lower()
        if "text" not in name and "prompt" not in name:
            continue
        if any(hint in name for hint in _SKIP_NAME_HINTS):
            continue
        display_name = title or cls or "node"
        for key, val in (node.get("inputs") or {}).items():
            if not isinstance(val, str):
                continue
            stripped = val.strip()
            if not stripped or stripped in seen:
                continue
            is_content = key.lower() in _CONTENT_KEYS or "\n" in stripped or len(stripped) >= _MIN_TEXT_LEN
            if is_content:
                seen.add(stripped)
                nodes.append((display_name, stripped))
    return nodes


def extract_workflow_text_nodes(path: str | Path) -> list[tuple[str, str]]:
    """Return (node_name, text) pairs discovered in ComfyUI workflow metadata."""
    try:
        fields = _collect_raw_fields(path)
    except Exception:
        return []

    nodes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in fields.values():
        prompt = _load_comfy_prompt(value)
        if not prompt:
            continue
        for name, text in _extract_comfy_nodes(prompt):
            if text not in seen:
                seen.add(text)
                nodes.append((name, text))
    return nodes


def workflow_text_candidates(path: str | Path, *, limit: int = _EXIF_CANDIDATE_LIMIT) -> list[str]:
    """Return the longest unique workflow text strings, up to ``limit``."""
    nodes = extract_workflow_text_nodes(path)
    ordered = sorted(nodes, key=lambda item: len(item[1]), reverse=True)
    return [text for _name, text in ordered[:limit]]


def _try_parse_caption_json(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return normalize_caption(parse_caption_text(raw[start : end + 1]))
    except (json.JSONDecodeError, ValueError):
        return None


def try_import_caption_from_exif(path: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """Try to import a caption with at least one obj bbox from image metadata."""
    for text in workflow_text_candidates(path):
        caption = _try_parse_caption_json(text)
        if caption is not None and has_obj_bbox_annotation(caption):
            return caption, "Imported caption with bbox annotations from EXIF workflow; click Save to persist."
    return None, None
