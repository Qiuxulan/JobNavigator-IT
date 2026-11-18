"""score_calibration 单元测试:单调性、截断、缺文件降级、置信度三档边界。"""

import json

import pytest

from app.services import score_calibration as sc


@pytest.fixture()
def params_file(tmp_path, monkeypatch):
    """把参数文件指向 tmp_path 下的可控副本,每个用例独立。"""

    def _write(payload):
        path = tmp_path / "score_calibration.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(sc, "CALIBRATION_PATH", path)
        sc._params_cache["mtime"] = None
        sc._params_cache["data"] = None
        return path

    return _write


VALID = {"p_low": 0.5, "p_high": 0.7}


def test_monotonic_non_decreasing(params_file):
    params_file(VALID)
    xs = [i / 100 for i in range(0, 101, 1)]
    ys = [sc.calibrate_semantic(x) for x in xs]
    assert all(a <= b for a, b in zip(ys, ys[1:]))


def test_strictly_increasing_inside_linear_region(params_file):
    params_file(VALID)
    assert sc.calibrate_semantic(0.5) < sc.calibrate_semantic(0.6) < sc.calibrate_semantic(0.7)


def test_clip_at_anchors(params_file):
    params_file(VALID)
    assert sc.calibrate_semantic(0.5) == pytest.approx(0.0)
    assert sc.calibrate_semantic(0.7) == pytest.approx(1.0)
    # 锚点外侧饱和
    assert sc.calibrate_semantic(0.0) == 0.0
    assert sc.calibrate_semantic(0.49) == 0.0
    assert sc.calibrate_semantic(0.9) == 1.0
    assert sc.calibrate_semantic(1.0) == 1.0
    # 线性段中点
    assert sc.calibrate_semantic(0.6) == pytest.approx(0.5)


def test_missing_file_degrades_to_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "CALIBRATION_PATH", tmp_path / "not_exists.json")
    sc._params_cache["mtime"] = None
    sc._params_cache["data"] = None
    assert sc.calibrate_semantic(0.55) == 0.55


def test_malformed_file_degrades_to_identity(params_file):
    path = params_file({"p_low": "oops"})  # 锚点非法
    assert sc.calibrate_semantic(0.55) == 0.55
    path.write_text("not json", encoding="utf-8")
    sc._params_cache["mtime"] = None
    sc._params_cache["data"] = None
    assert sc.calibrate_semantic(0.55) == 0.55


def test_degenerate_span_degrades_to_identity(params_file):
    params_file({"p_low": 0.6, "p_high": 0.6})
    assert sc.calibrate_semantic(0.55) == 0.55


def test_mtime_reload(params_file):
    path = params_file(VALID)
    assert sc.calibrate_semantic(0.6) == pytest.approx(0.5)
    # 重写文件(mtime 变化)后无需手动清缓存
    import os
    import time

    time.sleep(0.01)
    path.write_text(json.dumps({"p_low": 0.0, "p_high": 1.0}), encoding="utf-8")
    os.utime(path, None)
    assert sc.calibrate_semantic(0.6) == pytest.approx(0.6)


def test_confidence_label_high_requires_all_three():
    assert sc.confidence_label(0.5, 0.6, 3) == "high"
    # 任一不达标即降级
    assert sc.confidence_label(0.49, 0.6, 3) != "high"
    assert sc.confidence_label(0.5, 0.59, 3) != "high"
    assert sc.confidence_label(0.5, 0.6, 2) != "high"


def test_confidence_label_medium_boundary():
    assert sc.confidence_label(0.25, 0.4, 0) == "medium"
    assert sc.confidence_label(1.0, 1.0, 10) == "high"  # 满足 high 先匹配 high
    # 低于任一边界 → low
    assert sc.confidence_label(0.24, 0.4, 0) == "low"
    assert sc.confidence_label(0.25, 0.39, 0) == "low"
    assert sc.confidence_label(0.0, 0.0, 0) == "low"
