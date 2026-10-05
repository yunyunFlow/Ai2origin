"""Strict display-only configuration; no data transforms or private paths."""
from copy import deepcopy
from pathlib import Path
import math
import re

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "assets" / "default.json"
LINE_IDS = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}


def merge(base, update, path="style"):
    if not isinstance(update, dict):
        raise ValueError(path + " must be an object")
    result = deepcopy(base)
    for key, value in update.items():
        if key not in base and not path.startswith("style.series_overrides"):
            raise ValueError("Unknown key: " + path + "." + key)
        if value is None:
            raise ValueError("Null is unsupported: " + path + "." + key)
        if key in base and isinstance(base[key], dict):
            result[key] = merge(base[key], value, path + "." + key)
        else:
            result[key] = deepcopy(value)
    return result


def positive(value, path, limit=1000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= limit:
        raise ValueError(path + " must be finite and positive, at most " + str(limit))


def color(value, path):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(path + " requires a six-digit hex color")


def validate(style):
    if type(style["schema_version"]) is not int or style["schema_version"] != 1:
        raise ValueError("Style schema_version must be 1")
    for key in ("width_mm", "height_mm"):
        positive(style["figure"][key], "figure." + key)
    color(style["figure"]["background_color"], "figure.background_color")
    font = style["font"]
    names = [font["family"]] + font["fallback_families"] if isinstance(font["fallback_families"], list) else []
    if not names or any(not isinstance(n, str) or not n.strip() or any(c in n for c in '\\";$%\r\n') for n in names):
        raise ValueError("Font names must be nonempty plain text; fallbacks must be a list")
    for key in ("tick_size_pt", "axis_title_size_pt", "legend_size_pt", "title_size_pt", "annotation_size_pt"):
        positive(font[key], "font." + key, 72)
    positive(style["line"]["width_pt"], "line.width_pt", 20)
    if style["line"]["default_style"] not in LINE_IDS:
        raise ValueError("line.default_style: solid, dash, dot or dash_dot")
    positive(style["marker"]["size_pt"], "marker.size_pt", 40)
    color(style["axes"]["color"], "axes.color")
    positive(style["axes"]["width_pt"], "axes.width_pt", 10)
    if style["axes"]["tick_direction"] not in ("in", "out") or style["axes"]["frame"] not in ("full", "left"):
        raise ValueError("axes: tick_direction in/out and frame full/left")
    for section, key in (("axes", "major_grid"), ("axes", "minor_grid"), ("legend", "frame"), ("export", "transparent_background")):
        if type(style[section][key]) is not bool:
            raise ValueError(section + "." + key + " must be boolean")
    if style["axes"]["minor_grid"] or style["legend"]["frame"] or style["export"]["transparent_background"]:
        raise ValueError("v0.1 does not implement minor grids, framed legends or transparent export in both backends")
    palette = style["colors"]["palette"]
    if not isinstance(palette, list) or not palette:
        raise ValueError("colors.palette must be a nonempty list")
    for item in palette:
        color(item, "colors.palette")
    dpi = style["export"]["raster_dpi"]
    if type(dpi) is not int or dpi not in (72, 100, 150, 300, 600, 1200):
        raise ValueError("export.raster_dpi must be 72, 100, 150, 300, 600 or 1200 for the native PNG exporter")
    for identifier, override in style["series_overrides"].items():
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Series override requires a stable nonempty identifier")
        if not isinstance(override, dict) or any(k not in ("color", "width_pt", "line_style", "marker_size_pt") for k in override):
            raise ValueError("Invalid series override: " + identifier)
        for k, v in override.items():
            if k == "color":
                color(v, identifier + ".color")
            elif k == "line_style":
                if v not in LINE_IDS:
                    raise ValueError("Invalid series line_style")
            else:
                positive(v, identifier + "." + k, 40)
    return style


def resolve(load_json, user=None, project_file=None, project=None, task=None):
    style = load_json(DEFAULT_PATH)
    layers = ["built-in"]
    for name, update in (("user", load_json(user) if user else None),
                         ("project-file", load_json(project_file) if project_file else None),
                         ("project", project), ("task", load_json(task) if task else None)):
        if update is not None:
            style = merge(style, update)
            layers.append(name)
    return validate(style), layers


def series(style, identifier, index, explicit_color=None):
    result = {"color": style["colors"]["palette"][index % len(style["colors"]["palette"])],
              "width_pt": style["line"]["width_pt"], "line_style": style["line"]["default_style"],
              "marker_size_pt": style["marker"]["size_pt"]}
    result.update(style["series_overrides"].get(identifier, {}))
    if explicit_color is not None:
        color(explicit_color, identifier + ".explicit_color")
        result["color"] = explicit_color
    return result
