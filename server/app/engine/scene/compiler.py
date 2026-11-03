"""Scene DSL 编译器：timeline/scene + script + tokens + profile → scene.program（纯函数）。"""
from __future__ import annotations

from copy import deepcopy

from ..fpscalc import norm_fps
from .canonical import content_hash
from .schema import SCENE_SCHEMA, validate_program

DEFAULT_PALETTE = ["#F4EEE2", "#3D5588", "#FF665E", "#FFB511"]


def scene_text(scene: dict, script: dict) -> str:
    override = str(scene.get("text") or "").strip()
    if override:
        return override
    sentences = script.get("sentences") or []
    span = scene.get("source_span") or []
    text = "".join(sentences[i].get("text", "") for i in span
                   if isinstance(i, int) and 0 <= i < len(sentences))
    return text or scene.get("meaning") or ""


def _palette(tokens: dict) -> list[str]:
    visual = tokens.get("visual") or {}
    pal = [p for p in (visual.get("palette") or DEFAULT_PALETTE) if isinstance(p, str)]
    return (pal + DEFAULT_PALETTE)[:4]


def _screen(tokens: dict) -> tuple[list[float], list[float]]:
    visual = tokens.get("visual") or {}
    screen = visual.get("screen") or {}
    angle = float(screen.get("angle", 15) or 15)
    period = float(screen.get("period", 7) or 7)
    return [angle, angle + 60, 0], [period, period, max(1.0, period - 0.5)]


def _interp(pairs: list, t: float) -> float:
    if not pairs:
        return 0.0
    if t <= pairs[0][0]:
        return float(pairs[0][1])
    for (t0, v0), (t1, v1) in zip(pairs, pairs[1:]):
        if t <= t1:
            p = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return float(v0) + (float(v1) - float(v0)) * p
    return float(pairs[-1][1])


def camera_from_e02(camera: dict | None, duration: float, w: int, h: int) -> dict:
    if not camera:
        return {"anchor": [w / 2, h / 2], "keyframes": [
            {"t": 0.0, "zoom": 1.0, "x": 0, "y": 0, "rotate": 0, "ease": "linear"},
            {"t": round(duration, 3), "zoom": 1.03, "x": 0, "y": 0, "rotate": 0, "ease": "linear"}]}
    anchor = camera.get("anchor") or [w / 2, h / 2]
    if camera.get("keyframes"):
        kfs = []
        for k in sorted(camera["keyframes"], key=lambda x: float(x.get("t") or 0)):
            kfs.append({
                "t": round(max(0.0, min(float(k.get("t") or 0), duration)), 3),
                "zoom": round(float(k.get("zoom") or 1.0), 4),
                "x": round(float(k.get("x") or 0), 2),
                "y": round(float(k.get("y") or 0), 2),
                "rotate": round(float(k.get("rotate") or 0), 3),
                "ease": str(k.get("ease") or "linear"),
            })
        if kfs:
            return {"anchor": anchor, "keyframes": kfs}
    zoom = camera.get("zoom") or [[0, 1.0], [duration, 1.03]]
    pan = camera.get("pan") or [[0, 0], [duration, 0]]
    times = sorted({0.0, round(duration, 3)} | {round(float(t), 3) for t, _ in zoom + pan})
    kfs = [{"t": t, "zoom": round(_interp(zoom, t), 4), "x": round(_interp(pan, t), 2),
            "y": 0, "rotate": 0, "ease": "linear"} for t in times]
    return {"anchor": anchor, "keyframes": kfs}


def _font_family(value) -> str:
    import re
    s = re.sub(r"\s+\d{3}(?:/\d{3})?.*$", "", str(value or "")).strip()
    return s or "Noto Sans SC"


def compile_scene(scene: dict, script: dict, tokens: dict, profile: dict,
                  camera: dict | None = None, motion: bool = False,
                  layout: str = "16x9", asset_resolver=None) -> dict:
    w = int(profile.get("width") or 1920)
    h = int(profile.get("height") or 1080)
    fps = norm_fps(profile.get("fps") or 24)  # P1-12：非整数 fps 不截断
    duration = round(float(scene.get("end", 0)) - float(scene.get("start", 0)), 3)
    if duration <= 0:
        raise ValueError(f"场景 {scene.get('id')} duration <=0")
    text = scene_text(scene, script)
    pal = _palette(tokens)
    angles, periods = _screen(tokens)
    type_spec = tokens.get("type_spec") or {}
    family = _font_family(type_spec.get("family") or "Noto Sans SC")
    font_url = ""
    font_sha = str(scene.get("fontSha") or "")
    if font_sha:
        font_asset = asset_resolver(font_sha) if asset_resolver else None
        if not font_asset:
            raise ValueError(f"E_ASSET_MISSING: 字体 {font_sha} 缺失，请重新链接")
        if font_asset.get("kind") not in (None, "font"):
            raise ValueError(f"E_ASSET_KIND: {font_sha} 不是字体资产")
        family = font_asset.get("family") or f"FFAsset-{font_sha[:8]}"
        font_url = font_asset.get("url") or ""
    title_range = type_spec.get("title_range") or [72, 120]
    base_size = 132 if len(text) <= 10 else 112 if len(text) <= 18 else 92
    size = max(int(title_range[0]), min(int(title_range[1]), base_size))
    line_height = type_spec.get("line_height", 1.35)
    spacing = type_spec.get("letter_spacing", 0)
    span = scene.get("source_span") or []
    if layout == "9x16":
        card = {"x": 50, "y": 120, "w": w - 100, "h": h - 240}
        rule = [100, h - 520, 620, 10]
        title_box = [100, 560, w - 200, h - 1000]
        title_size = max(int(title_range[0]), int(size * 0.85))
        title_max = w - 200
        cross = {"x": w - 140, "y": 100}
    else:
        card = {"x": 60, "y": 80, "w": w - 120, "h": h - 160}
        rule = [160, 700, 520, 10]
        title_box = [160, 320, w - 320, 360]
        title_size = size
        title_max = w - 320
        cross = {"x": w - 152, "y": 128}
    scale = float(scene.get("text_scale") or 1.0)
    if 0.7 <= scale <= 1.3:
        title_size = max(48, int(round(title_size * scale)))
    layers = [
        {"id": "L_card", "type": "component", "z": 0,
         "component": "paper-card",
         "props": {**card, "radius": 8, "paper": pal[0], "ink": pal[1], "grain": 0.08}},
        {"id": "L_rule", "type": "shape", "z": 8,
         "shape": "rect", "box": rule, "fill": pal[2], "alpha": 0.9},
        {"id": "L_title", "type": "text", "z": 10, "content": text,
         "box": title_box,
         "style": {"font": family, "weight": 900, "size": title_size,
                   "lineHeight": line_height, "letterSpacing": spacing,
                   "color": pal[0], "align": "left", "maxWidth": title_max,
                   **({"fontUrl": font_url} if font_url else {})},
         "reveal": {"type": "mask-reveal", "at": 0.15, "duration": 0.6, "ease": "easeOut"},
         "in": {"at": 0.0, "type": "cut"},
         "out": {"at": round(max(0.0, duration - 0.4), 3), "type": "fade", "duration": 0.4}},
        {"id": "L_cross", "type": "component", "z": 50,
         "component": "registration-cross",
         "props": {**cross, "size": 1.0, "color": pal[1]}},
    ]
    asset_meta = []
    if font_sha:
        asset_meta.append({"sha": font_sha, "kind": "font", "url": font_url, "family": family})
    for i, layer in enumerate(scene.get("layers") or []):
        if layer.get("type", "image") != "image":
            raise ValueError(f"E_PROGRAM_INVALID: scene.layers[{i}] 只支持 image")
        sha = str(layer.get("assetSha") or "").strip()
        if not sha:
            raise ValueError(f"E_ASSET_MISSING: scene.layers[{i}] 缺少 assetSha")
        info = asset_resolver(sha) if asset_resolver else None
        if not info:
            raise ValueError(f"E_ASSET_MISSING: 图片 {sha} 缺失，请重新链接")
        if info.get("kind") not in (None, "image"):
            raise ValueError(f"E_ASSET_KIND: {sha} 不是图片资产")
        box = layer.get("box") or [480, 270, 960, 540]
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError(f"E_PROGRAM_INVALID: scene.layers[{i}].box 必须是 [x,y,w,h]")
        fit = str(layer.get("fit") or "cover")
        if fit not in ("cover", "contain"):
            raise ValueError(f"E_PROGRAM_INVALID: scene.layers[{i}].fit 非法")
        src = info.get("url") or ""
        if not src:
            raise ValueError(f"E_ASSET_MISSING: 图片 {sha} 没有可渲染 URL")
        layers.append({
            "id": str(layer.get("id") or f"L_img{i + 1:02d}"),
            "type": "image", "z": int(layer.get("z", 20)), "src": src,
            "assetSha": sha, "name": str(layer.get("name") or "")[:60],
            "box": [int(round(float(v))) for v in box],
            "fit": fit, "opacity": round(float(layer.get("opacity", 1)), 3),
        })
        asset_meta.append({"sha": sha, "kind": "image", "url": src})
    program = {
        "schema": SCENE_SCHEMA,
        "id": scene.get("id"),
        "duration": duration,
        "canvas": {"w": w, "h": h, "fps": fps, "background": "paper",
                    "paper": pal[0], "inks": pal[1:4], "angles": angles, "periods": periods},
        "layers": layers,
        "audioCues": [],
        "meta": {"operation": scene.get("operation", ""), "source_span": span, "layout": layout,
                 "text": text, "compiler_version": "1.0.0", "assets": asset_meta},
    }
    if motion:
        program["camera"] = camera_from_e02(camera, duration, w, h)
    errors = validate_program(program)
    if errors:
        raise ValueError("E_PROGRAM_INVALID: " + "; ".join(errors))
    program["program_sha"] = content_hash(program)
    return program


def static_program(program: dict) -> dict:
    """去掉 camera/transitions 后的静态部分（base/motion 一致性测试用）。"""
    p = deepcopy(program)
    p.pop("camera", None)
    p.pop("transitions", None)
    p.pop("program_sha", None)
    return p
