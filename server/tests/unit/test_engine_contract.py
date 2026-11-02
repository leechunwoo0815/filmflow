"""Contract v2：riso film_spec / legacy_entry / 12 组件 fixture。"""
from pathlib import Path

import pytest

from app.errors import ApiError
from app.services.engines import compute_pack_sha, load_contract, validate_contract


def test_riso_contract_v2_entries_and_components():
    c = load_contract("riso")
    assert str(c["api_version"]).startswith("2")
    assert c["scene_schema"] == "filmflow.scene/1"
    assert c["entry"]["still_spec"] and c["entry"]["film_spec"]
    assert c["legacy_entry"]["still"] and c["legacy_entry"]["film"]
    assert len(c["capabilities"]["components"]) == 12
    kit = Path(__file__).resolve().parents[3] / "engines/riso/fixture/scene-kit.json"
    import json
    names = [x["name"] for x in json.loads(kit.read_text())["components"]]
    assert len(names) == 12
    assert set(names) == set(c["capabilities"]["components"])


def test_contract_v2_requires_film_spec():
    c = load_contract("riso")
    broken = {**c, "entry": {k: v for k, v in c["entry"].items() if k != "film_spec"}}
    pack = Path(__file__).resolve().parents[3] / "engines/riso"
    with pytest.raises(ApiError):
        validate_contract(broken, pack)


def test_engine_pack_sha_is_stable():
    assert compute_pack_sha("riso") == compute_pack_sha("riso")
    assert len(compute_pack_sha("riso")) == 64
