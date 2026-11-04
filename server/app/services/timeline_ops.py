"""FR-32/34 时间轴操作：纯函数、读时校验、相机/转场编辑。"""
from __future__ import annotations

from copy import deepcopy

from ..engine.scene.compiler import scene_text
from ..engine.scene.transitions import TRANSITIONS

READ_CPS = 5.2
MIN_SCENE = 0.5
PRESETS = ("lock", "push-in", "pull-out", "pan-right", "follow", "handheld", "impact")


class TimelineOpError(Exception):
    def __init__(self, code: str, message: str, status: int = 409,
                 details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def _fps(doc: dict) -> float:
    from ..engine.fpscalc import norm_fps
    return norm_fps(doc.get("fps") or 24)


def _required(text: str) -> float:
    return round(len((text or "").replace("\n", "")) / READ_CPS, 3)


def _scene_by_id(doc: dict, scene_id: str) -> tuple[int, dict]:
    for i, s in enumerate(doc.get("scenes") or []):
        if s.get("id") == scene_id:
            return i, s
    raise TimelineOpError("E_SCENE_NOT_FOUND", f"场景不存在：{scene_id}", 404)


def _new_id(existing: set[str], base: str) -> str:
    for suffix in "bcdefghijklmnopqrstuvwxyz":
        candidate = f"{base}{suffix}"
        if candidate not in existing:
            return candidate
    n = 2
    while f"{base}{n}" in existing:
        n += 1
    return f"{base}{n}"


def _image_layers(scene: dict) -> list[dict]:
    return [l for l in (scene.get("layers") or []) if isinstance(l, dict)]


def _clean_box(box) -> list[int]:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise TimelineOpError("E_ASSET_BOX", "图片 box 必须是 [x,y,w,h]", 409)
    vals = [int(round(float(v))) for v in box]
    if vals[2] <= 0 or vals[3] <= 0:
        raise TimelineOpError("E_ASSET_BOX", "图片宽高必须 >0", 409)
    return vals


def _clean_layer(layer: dict) -> dict:
    out = deepcopy(layer)
    if str(out.get("type") or "image") != "image":
        raise TimelineOpError("E_ASSET_LAYER_TYPE", "v1 只支持 image 图层", 409)
    out["type"] = "image"
    sha = str(out.get("assetSha") or "").strip()
    if not sha:
        raise TimelineOpError("E_ASSET_MISSING", "图片图层缺少 assetSha", 409)
    out["assetSha"] = sha
    out["box"] = _clean_box(out.get("box") or [480, 270, 960, 540])
    out["z"] = int(round(float(out.get("z") or 20)))
    fit = str(out.get("fit") or "cover")
    if fit not in ("cover", "contain"):
        raise TimelineOpError("E_ASSET_FIT", "fit 必须是 cover/contain", 409)
    out["fit"] = fit
    out["opacity"] = round(max(0.0, min(float(out.get("opacity", 1) or 0), 1.0)), 3)
    out["name"] = str(out.get("name") or "")[:60]
    return out


def _clean_layers(scene: dict, layers: list[dict]) -> list[dict]:
    if len(layers or []) > 20:
        raise TimelineOpError("E_ASSET_TOO_MANY", "单场景最多 20 个图片图层", 409)
    out, ids = [], set()
    for layer in layers or []:
        clean = _clean_layer(layer)
        lid = str(clean.get("id") or "")
        if not lid:
            for n in range(1, 100):
                lid = f"img{n:02d}"
                if lid not in ids:
                    break
            clean["id"] = lid
        if lid in ids:
            raise TimelineOpError("E_ASSET_LAYER_DUP", f"图层 id 重复：{lid}", 409)
        ids.add(lid)
        out.append(clean)
    return out


def _clean_audio_layers(scene: dict, layers: list[dict]) -> list[dict]:
    if len(layers or []) > 20:
        raise TimelineOpError("E_ASSET_TOO_MANY", "单场景最多 20 个 SFX", 409)
    duration = max(0.0, float(scene["end"]) - float(scene["start"]))
    out, ids = [], set()
    for layer in layers or []:
        sha = str(layer.get("assetSha") or "").strip()
        if not sha:
            raise TimelineOpError("E_ASSET_MISSING", "SFX 缺少 assetSha", 409)
        lid = str(layer.get("id") or "")
        if not lid:
            for n in range(1, 100):
                lid = f"sfx{n:02d}"
                if lid not in ids:
                    break
        if lid in ids:
            raise TimelineOpError("E_ASSET_LAYER_DUP", f"SFX id 重复：{lid}", 409)
        ids.add(lid)
        at = round(max(0.0, min(float(layer.get("at") or 0), duration)), 3)
        gain = round(float(layer.get("gainDb") or 0), 2)
        if not -60 <= gain <= 12:
            raise TimelineOpError("E_ASSET_GAIN", "SFX 增益必须在 -60..12dB", 409)
        fade_in = round(max(0.0, float(layer.get("fadeIn") or 0)), 3)
        fade_out = round(max(0.0, float(layer.get("fadeOut") or 0)), 3)
        out.append({"id": lid, "assetSha": sha, "at": at, "gainDb": gain,
                    "fadeIn": fade_in, "fadeOut": fade_out,
                    "name": str(layer.get("name") or "")[:60]})
    return out


def _recompute_scene(scene: dict, script: dict) -> None:
    start, end = float(scene["start"]), float(scene["end"])
    duration = max(0.0, end - start)
    text = scene_text(scene, script)
    required = _required(text)
    scene["read_seconds"] = round(min(duration, max(0.8, required)), 3)
    scene["last_text_at"] = round(max(start, end - scene["read_seconds"]), 3)


def normalize(doc: dict, script: dict | None = None) -> dict:
    """场景按顺序首尾相接；同步 duration/frames/events/V1 clips。"""
    script = script or {}
    scenes = list(doc.get("scenes") or [])
    t = 0.0
    for i, scene in enumerate(scenes):
        duration = round(max(MIN_SCENE, float(scene.get("end", 0)) - float(scene.get("start", 0))), 3)
        scene["start"] = round(t, 3)
        scene["end"] = round(t + duration, 3)
        _recompute_scene(scene, script)
        t = scene["end"]
    doc["scenes"] = scenes
    doc["duration"] = round(t, 3)
    doc["frames"] = round(t * _fps(doc))
    events = [e for e in (doc.get("events") or [])
              if e.get("role") != "scene_start" and e.get("scene_id") in {s["id"] for s in scenes}]
    starts = []
    next_event = 1
    used_ids = {e.get("id") for e in events}
    for scene in scenes:
        eid = f"E{next_event:02d}"
        while eid in used_ids:
            next_event += 1
            eid = f"E{next_event:02d}"
        next_event += 1
        used_ids.add(eid)
        starts.append({"id": eid, "scene_id": scene["id"], "at": scene["start"],
                       "time_basis": "planned", "role": "scene_start", "allow_snap": False})
    for e in events:
        e["at"] = round(max(0.0, min(float(e.get("at") or 0), doc["duration"])), 3)
    doc["events"] = starts + events
    tracks = [tr for tr in (doc.get("tracks") or []) if tr.get("id") != "V1"]
    tracks.insert(0, {"id": "V1", "type": "video",
                      "clips": [{"sceneId": s["id"], "start": s["start"], "end": s["end"]}
                                for s in scenes]})
    doc["tracks"] = tracks
    return doc


def validate(doc: dict, script: dict | None = None) -> dict:
    script = script or {}
    errors, warnings = [], []
    scenes = doc.get("scenes") or []
    if not scenes:
        errors.append({"code": "E_TIMELINE_EMPTY", "sceneId": None,
                       "message": "时间轴没有场景", "fix": "先导入文案或添加场景"})
    ids = [s.get("id") for s in scenes]
    if len(ids) != len(set(ids)):
        errors.append({"code": "E_SCENE_ID_DUP", "sceneId": None,
                       "message": "场景 id 重复", "fix": "重新编号"})
    for i, s in enumerate(scenes):
        sid = s.get("id")
        dur = float(s.get("end", 0)) - float(s.get("start", 0))
        if dur < MIN_SCENE - 1e-6:
            errors.append({"code": "E_SCENE_TOO_SHORT", "sceneId": sid,
                           "message": f"{sid} 时长 {dur:.2f}s < {MIN_SCENE}s",
                           "fix": "拉长到至少 0.5s"})
        text = scene_text(s, script)
        req = _required(text)
        if req > dur + 0.05:
            errors.append({"code": "E_SCENE_READ_OVERFLOW", "sceneId": sid,
                           "message": f"{sid} 需要 {req:.2f}s 读完，当前 {dur:.2f}s",
                           "fix": "拉长场景或删字", "required": req, "duration": round(dur, 3)})
        elif req > dur * 0.9:
            warnings.append({"code": "W_SCENE_READ_TIGHT", "sceneId": sid,
                             "message": f"{sid} 读时偏紧（{req:.2f}s / {dur:.2f}s）",
                             "fix": "可再留 0.2s 呼吸"})
        kfs = s.get("camera_keyframes") or []
        if not isinstance(kfs, list):
            errors.append({"code": "E_CAMERA_FORMAT", "sceneId": sid,
                           "message": f"{sid} camera_keyframes 必须是数组",
                           "fix": "重新选择相机预设"})
            kfs = []
        for kf in kfs:
            if not isinstance(kf, dict):
                errors.append({"code": "E_CAMERA_FORMAT", "sceneId": sid,
                               "message": f"{sid} 相机关键帧格式非法",
                               "fix": "重新选择相机预设"})
                break
            t = float(kf.get("t") or 0)
            if t < -1e-6 or t > dur + 1e-6:
                errors.append({"code": "E_CAMERA_TIME", "sceneId": sid,
                               "message": f"{sid} 相机关键帧 t={t}s 超出场景",
                               "fix": "把关键帧移回 0..场景时长"})
                break
        tr = s.get("transition")
        if tr and tr not in TRANSITIONS:
            warnings.append({"code": "W_TRANSITION_UNKNOWN", "sceneId": sid,
                             "message": f"{sid} 转场 {tr} 不在 8 类库内，将回退 match-shape",
                             "fix": "从 8 类转场中选择"})
        try:
            _clean_layers(s, s.get("layers") or [])
        except TimelineOpError as e:
            errors.append({"code": e.code, "sceneId": sid, "message": e.message,
                           "fix": "删除或修正异常图片图层"})
        try:
            _clean_audio_layers(s, s.get("audio_layers") or [])
        except TimelineOpError as e:
            errors.append({"code": e.code, "sceneId": sid, "message": e.message,
                           "fix": "删除或修正异常 SFX"})
        if s.get("fontSha") is not None and not isinstance(s.get("fontSha"), str):
            errors.append({"code": "E_ASSET_FONT", "sceneId": sid,
                           "message": f"{sid} fontSha 必须是字符串",
                           "fix": "重新选择字体资产"})
        try:
            scale = float(s.get("text_scale") or 1.0)
            if not 0.7 <= scale <= 1.3:
                errors.append({"code": "E_TEXT_SCALE", "sceneId": sid,
                               "message": f"{sid} text_scale 必须在 0.7..1.3",
                               "fix": "恢复到 100%"})
        except (TypeError, ValueError):
            errors.append({"code": "E_TEXT_SCALE", "sceneId": sid,
                           "message": f"{sid} text_scale 必须是数字",
                           "fix": "恢复到 100%"})
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "duration": doc.get("duration", 0), "frames": doc.get("frames", 0)}


def _ensure_valid(doc: dict, script: dict, force: bool = False,
                  allow_read_overflow: bool = False) -> dict:
    validation = validate(doc, script)
    blocking = [e for e in validation["errors"]
                if not ((force or allow_read_overflow) and e["code"] == "E_SCENE_READ_OVERFLOW")]
    if blocking:
        first = blocking[0]
        raise TimelineOpError(first["code"], first["message"], 409,
                              {"validation": validation, "fix": first.get("fix")})
    return validation


def _split_text(text: str, ratio: float) -> tuple[str, str]:
    if not text:
        return "", ""
    idx = max(1, min(len(text) - 1, round(len(text) * ratio)))
    for delta in range(8):
        for cand in (idx + delta, idx - delta):
            if 0 < cand < len(text) and text[cand - 1] in "。！？；，,;!?":
                idx = cand
                return text[:idx].strip(), text[idx:].strip()
    return text[:idx].strip(), text[idx:].strip()


def _split_scene_text(scene: dict, script: dict, ratio: float) -> tuple[str, list[int], str, list[int]]:
    text = scene_text(scene, script)
    span = list(scene.get("source_span") or [])
    sentences = script.get("sentences") or []
    if not scene.get("text") and len(span) > 1:
        weights = [len(sentences[i].get("text", "")) for i in span if 0 <= i < len(sentences)]
        total = sum(weights) or 1
        acc, cut = 0, 1
        for j, w in enumerate(weights[:-1], 1):
            acc += w
            if acc / total >= ratio:
                cut = max(1, min(len(span) - 1, j))
                break
        else:
            cut = max(1, len(span) - 1)
        left_span, right_span = span[:cut], span[cut:]
        left_text = "".join(sentences[i].get("text", "") for i in left_span)
        right_text = "".join(sentences[i].get("text", "") for i in right_span)
        if left_text.strip() and right_text.strip():
            return left_text, left_span, right_text, right_span
    left, right = _split_text(text, ratio)
    return left, [], right, []


def _require_text_pair(left: str, right: str) -> None:
    if not left.strip() or not right.strip():
        raise TimelineOpError("E_SPLIT_TEXT", "这一场只有一个短句，无法在中间分割",
                              409, {"fix": "先补一句文案，或拉长场景后移到句间"})


def resize(doc: dict, script: dict, scene_id: str, end: float, force: bool = False) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    end = round(float(end), 3)
    start = float(scene["start"])
    if end - start < MIN_SCENE:
        raise TimelineOpError("E_SCENE_TOO_SHORT",
                              f"{scene_id} 最短 {MIN_SCENE}s，当前 {end - start:.2f}s", 409)
    scene["end"] = end
    normalize(doc, script)
    _ensure_valid(doc, script, force)
    return doc


def move(doc: dict, script: dict, scene_id: str, to_index: int) -> dict:
    i, scene = _scene_by_id(doc, scene_id)
    scenes = doc["scenes"]
    scenes.pop(i)
    to_index = max(0, min(int(to_index), len(scenes)))
    scenes.insert(to_index, scene)
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def split(doc: dict, script: dict, scene_id: str, at: float, force: bool = False) -> dict:
    i, scene = _scene_by_id(doc, scene_id)
    start, end = float(scene["start"]), float(scene["end"])
    at = round(max(start + MIN_SCENE, min(float(at), end - MIN_SCENE)), 3)
    left_dur, right_dur = at - start, end - at
    left_text, left_span, right_text, right_span = _split_scene_text(
        scene, script, left_dur / max(0.001, end - start))
    _require_text_pair(left_text, right_text)
    if not force:
        if _required(left_text) > left_dur + 0.05:
            raise TimelineOpError("E_SCENE_READ_OVERFLOW",
                                  f"{scene_id} 前半需要 {_required(left_text)}s，当前 {left_dur:.2f}s",
                                  409, {"fix": "把分割点向右拖或删字"})
        if _required(right_text) > right_dur + 0.05:
            raise TimelineOpError("E_SCENE_READ_OVERFLOW",
                                  f"{scene_id} 后半需要 {_required(right_text)}s，当前 {right_dur:.2f}s",
                                  409, {"fix": "把分割点向左拖或删字"})
    existing = {s["id"] for s in doc["scenes"]}
    new_id = _new_id(existing, scene_id)
    right = deepcopy(scene)
    right.update({"id": new_id, "start": at, "end": end, "source_span": right_span,
                  "text": right_text, "transition": "cut"})
    scene.update({"end": at, "source_span": left_span, "text": left_text})
    doc["scenes"].insert(i + 1, right)
    normalize(doc, script)
    _ensure_valid(doc, script, force)
    return doc


def merge(doc: dict, script: dict, scene_id: str, next_id: str | None = None) -> dict:
    i, scene = _scene_by_id(doc, scene_id)
    if i + 1 >= len(doc["scenes"]):
        raise TimelineOpError("E_MERGE_LAST", "最后一场没有下一场可合并", 409)
    nxt = doc["scenes"][i + 1]
    if next_id and nxt["id"] != next_id:
        raise TimelineOpError("E_MERGE_NOT_ADJACENT", "只能合并相邻场景", 409)
    left_text = scene_text(scene, script)
    right_text = scene_text(nxt, script)
    scene["text"] = left_text + right_text
    scene["source_span"] = list(scene.get("source_span") or []) + list(nxt.get("source_span") or [])
    scene["end"] = nxt["end"]
    doc["scenes"].pop(i + 1)
    normalize(doc, script)
    _ensure_valid(doc, script)
    return doc


def duplicate(doc: dict, script: dict, scene_id: str) -> dict:
    i, scene = _scene_by_id(doc, scene_id)
    existing = {s["id"] for s in doc["scenes"]}
    copy = deepcopy(scene)
    copy["id"] = _new_id(existing, scene_id)
    copy["transition"] = "cut"
    doc["scenes"].insert(i + 1, copy)
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def set_text(doc: dict, script: dict, scene_id: str, text: str, force: bool = False) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    text = str(text or "").strip()
    if not text:
        raise TimelineOpError("E_SCENE_TEXT_EMPTY", "场景文案不能为空", 409)
    scene["text"] = text
    normalize(doc, script)
    _ensure_valid(doc, script, force)
    return doc


def _clean_keyframes(scene: dict, keyframes: list[dict]) -> list[dict]:
    start, end = float(scene["start"]), float(scene["end"])
    duration = end - start
    clean, seen = [], set()
    for k in sorted(keyframes or [], key=lambda x: float(x.get("t") or 0)):
        t = round(max(0.0, min(float(k.get("t") or 0), duration)), 3)
        if t in seen:
            continue
        seen.add(t)
        zoom = float(k.get("zoom") or 1.0)
        x, y = float(k.get("x") or 0), float(k.get("y") or 0)
        rot = float(k.get("rotate") or 0)
        if not 0.5 <= zoom <= 3.0:
            raise TimelineOpError("E_CAMERA_ZOOM", f"zoom {zoom} 超出 0.5..3.0", 409)
        if abs(x) > 5000 or abs(y) > 5000:
            raise TimelineOpError("E_CAMERA_PAN", "pan 超出 ±5000px", 409)
        if abs(rot) > 30:
            raise TimelineOpError("E_CAMERA_ROTATE", "rotate 超出 ±30°", 409)
        clean.append({"t": t, "zoom": round(zoom, 4), "x": round(x, 2), "y": round(y, 2),
                      "rotate": round(rot, 3), "ease": str(k.get("ease") or "linear")})
    if not clean:
        raise TimelineOpError("E_CAMERA_EMPTY", "至少保留 1 个相机关键帧", 409)
    if len(clean) > 20:
        raise TimelineOpError("E_CAMERA_TOO_MANY", "相机关键帧最多 20 个", 409)
    return clean


def set_camera(doc: dict, script: dict, scene_id: str, keyframes: list[dict],
               anchor: list | None = None, note: str = "") -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    scene["camera_keyframes"] = _clean_keyframes(scene, keyframes)
    if anchor:
        if len(anchor) != 2:
            raise TimelineOpError("E_CAMERA_ANCHOR", "anchor 必须是 [x,y]", 409)
        scene["camera_anchor"] = [round(float(anchor[0]), 1), round(float(anchor[1]), 1)]
    if note:
        scene["camera"] = str(note)[:80]
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def set_text_scale(doc: dict, script: dict, scene_id: str, scale: float) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    try:
        value = round(float(scale), 3)
    except (TypeError, ValueError):
        raise TimelineOpError("E_TEXT_SCALE", "text_scale 必须是数字", 409)
    if not 0.7 <= value <= 1.3:
        raise TimelineOpError("E_TEXT_SCALE", "text_scale 必须在 0.7..1.3", 409)
    scene["text_scale"] = value
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def set_transition(doc: dict, script: dict, scene_id: str, transition: str,
                   duration: float | None = None) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    if transition not in TRANSITIONS:
        raise TimelineOpError("E_TRANSITION_UNKNOWN", f"未知转场：{transition}", 409)
    scene["transition"] = transition
    if duration is not None:
        d = round(float(duration), 3)
        if not 0.1 <= d <= 2.0:
            raise TimelineOpError("E_TRANSITION_DURATION", "转场时长必须在 0.1..2.0s", 409)
        scene["transition_duration"] = d
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def add_scene(doc: dict, script: dict, scene: dict, index: int | None = None) -> dict:
    """插入一个场景（场景模板/系列）；保留模板视觉字段，文本交给 script/text。"""
    new = deepcopy(scene or {})
    scenes = doc.get("scenes") or []
    used = {str(s.get("id")) for s in scenes}
    sid = str(new.get("id") or "")
    if not sid or sid in used:
        n = len(scenes) + 1
        while f"S{n:02d}" in used:
            n += 1
        sid = f"S{n:02d}"
    new["id"] = sid
    dur = float(new.get("duration") or (float(new.get("end", 0)) - float(new.get("start", 0))))
    if dur < MIN_SCENE:
        raise TimelineOpError("E_SCENE_TOO_SHORT", f"{sid} 场景模板时长必须 >= {MIN_SCENE}s", 409)
    new.pop("duration", None)
    new.setdefault("time_basis", "planned")
    new.setdefault("source_span", [])
    new.setdefault("meaning", "")
    new.setdefault("operation", "")
    new.setdefault("camera", "")
    new.setdefault("transition", "")
    new["start"] = 0.0
    new["end"] = round(dur, 3)
    pos = len(scenes) if index is None else max(0, min(int(index), len(scenes)))
    scenes.insert(pos, new)
    doc["scenes"] = scenes
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def add_image(doc: dict, script: dict, scene_id: str, payload: dict) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    layers = _image_layers(scene)
    layer = {"type": "image", "assetSha": str(payload.get("assetSha") or ""),
             "box": payload.get("box") or [480, 270, 960, 540],
             "z": payload.get("z", 20), "fit": payload.get("fit") or "cover",
             "opacity": payload.get("opacity", 1), "name": payload.get("name") or ""}
    if payload.get("layerId"):
        layer["id"] = str(payload.get("layerId"))
    scene["layers"] = _clean_layers(scene, layers + [layer])
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def update_image(doc: dict, script: dict, scene_id: str, layer_id: str,
                 patch: dict) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    layers = _image_layers(scene)
    idx = next((i for i, l in enumerate(layers) if l.get("id") == layer_id), -1)
    if idx < 0:
        raise TimelineOpError("E_ASSET_LAYER_NOT_FOUND", f"图片图层不存在：{layer_id}", 404)
    merged = {**layers[idx], **{k: v for k, v in (patch or {}).items()
                                if k in ("box", "z", "fit", "opacity", "name")}}
    layers[idx] = merged
    scene["layers"] = _clean_layers(scene, layers)
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def remove_layer(doc: dict, script: dict, scene_id: str, layer_id: str) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    layers = _image_layers(scene)
    kept = [l for l in layers if l.get("id") != layer_id]
    if len(kept) == len(layers):
        raise TimelineOpError("E_ASSET_LAYER_NOT_FOUND", f"图片图层不存在：{layer_id}", 404)
    scene["layers"] = _clean_layers(scene, kept)
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def set_font(doc: dict, script: dict, scene_id: str, asset_sha: str) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    sha = str(asset_sha or "").strip()
    if sha:
        scene["fontSha"] = sha
    else:
        scene.pop("fontSha", None)
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def add_sfx(doc: dict, script: dict, scene_id: str, payload: dict) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    layers = list(scene.get("audio_layers") or [])
    layer = {"assetSha": str(payload.get("assetSha") or ""),
             "at": payload.get("at", 0), "gainDb": payload.get("gainDb", 0),
             "fadeIn": payload.get("fadeIn", 0), "fadeOut": payload.get("fadeOut", 0),
             "name": payload.get("name") or ""}
    if payload.get("layerId"):
        layer["id"] = str(payload.get("layerId"))
    scene["audio_layers"] = _clean_audio_layers(scene, layers + [layer])
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def remove_sfx(doc: dict, script: dict, scene_id: str, layer_id: str) -> dict:
    _, scene = _scene_by_id(doc, scene_id)
    layers = list(scene.get("audio_layers") or [])
    kept = [l for l in layers if l.get("id") != layer_id]
    if len(kept) == len(layers):
        raise TimelineOpError("E_ASSET_LAYER_NOT_FOUND", f"SFX 不存在：{layer_id}", 404)
    scene["audio_layers"] = _clean_audio_layers(scene, kept)
    normalize(doc, script)
    _ensure_valid(doc, script, allow_read_overflow=True)
    return doc


def camera_preset(name: str, duration: float, anchor: list | None = None) -> dict:
    if name not in PRESETS:
        raise TimelineOpError("E_CAMERA_PRESET", f"未知相机预设：{name}", 404)
    d = round(max(MIN_SCENE, float(duration or 1)), 3)
    mid = round(d / 2, 3)
    kfs = {
        "lock": [(0, 1.0, 0, 0, 0), (d, 1.0, 0, 0, 0)],
        "push-in": [(0, 1.0, 0, 0, 0), (d, 1.08, 0, 0, 0)],
        "pull-out": [(0, 1.08, 0, 0, 0), (d, 1.0, 0, 0, 0)],
        "pan-right": [(0, 1.03, 0, 0, 0), (d, 1.03, 70, 0, 0)],
        "follow": [(0, 1.04, -45, 0, 0), (d, 1.04, 45, 0, 0)],
        "handheld": [(0, 1.02, 0, 0, 0), (mid, 1.025, 6, -4, 0.4),
                     (d, 1.02, -5, 3, -0.3)],
        "impact": [(0, 1.0, 0, 0, 0), (min(0.25, d * 0.2), 1.14, 0, 0, 0),
                   (d, 1.05, 0, 0, 0)],
    }[name]
    return {"anchor": anchor or [960, 540],
            "keyframes": [{"t": round(t, 3), "zoom": z, "x": x, "y": y, "rotate": r,
                           "ease": "linear"} for t, z, x, y, r in kfs]}


def apply(doc: dict, script: dict, op: str, payload: dict) -> tuple[dict, dict]:
    new = deepcopy(doc)
    force = bool(payload.get("force"))
    scene_id = str(payload.get("sceneId") or "")
    if op == "camera_preset":
        _, scene = _scene_by_id(new, scene_id)
        preset = camera_preset(str(payload.get("preset") or "lock"),
                               float(scene["end"]) - float(scene["start"]),
                               payload.get("anchor") or scene.get("camera_anchor"))
        set_camera(new, script, scene_id, preset["keyframes"], preset["anchor"],
                   str(payload.get("note") or ""))
    elif op == "resize":
        resize(new, script, scene_id, float(payload.get("end")), force)
    elif op == "move":
        move(new, script, scene_id, int(payload.get("toIndex") or 0))
    elif op == "split":
        split(new, script, scene_id, float(payload.get("at")), force)
    elif op == "merge":
        merge(new, script, scene_id, payload.get("nextId"))
    elif op == "duplicate":
        duplicate(new, script, scene_id)
    elif op == "set_text":
        set_text(new, script, scene_id, str(payload.get("text") or ""), force)
    elif op == "set_camera":
        set_camera(new, script, scene_id, payload.get("keyframes") or [],
                   payload.get("anchor"), str(payload.get("note") or ""))
    elif op == "set_text_scale":
        set_text_scale(new, script, scene_id, float(payload.get("scale") or 1.0))
    elif op == "set_transition":
        set_transition(new, script, scene_id, str(payload.get("transition") or ""),
                       payload.get("duration"))
    elif op == "add_scene":
        add_scene(new, script, payload.get("scene") or {}, payload.get("index"))
    elif op == "add_image":
        add_image(new, script, scene_id, payload)
    elif op == "update_image":
        update_image(new, script, scene_id, str(payload.get("layerId") or ""),
                     payload.get("patch") or {})
    elif op == "remove_layer":
        remove_layer(new, script, scene_id, str(payload.get("layerId") or ""))
    elif op == "set_font":
        set_font(new, script, scene_id, str(payload.get("assetSha") or ""))
    elif op == "add_sfx":
        add_sfx(new, script, scene_id, payload)
    elif op == "remove_sfx":
        remove_sfx(new, script, scene_id, str(payload.get("layerId") or ""))
    else:
        raise TimelineOpError("E_TIMELINE_OP", f"未知时间轴操作：{op}", 400)
    validation = validate(new, script)
    return new, {"validation": validation,
                 "impact": {"scenes": [scene_id] if scene_id else [],
                            "nodes": ["D01", "D02", "E03", "E04", "F02"],
                            "dirty": "scene_hash"}}
