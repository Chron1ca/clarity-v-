"""
deploy() in tools/training/validate.py — wake_config.json merge tests.

The defect this guards against: the prior implementation overwrote
``wake_config.json`` with a single-entry config, erasing cv_go +
cv_over. The fixed deploy() must:

  * Bootstrap a fresh config when the file is missing or malformed
  * Preserve every existing entry except the one being updated
  * Update an entry with the same name in place — never duplicate
  * Infer ``role`` from name suffix (over/stop/end → stop, else start)
  * Use the validated threshold passed in, not a hard-coded default
  * Preserve ``cooldown_seconds`` from the existing config

Every test runs against tmp_path; the repo's real wake_config.json is
never touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make tools/training/ importable so we can `from validate import ...`.
# Also add src/ because validate.py inserts it at module import time.
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "training"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from validate import _infer_role_from_name, deploy  # noqa: E402


def _make_repo(tmp_path: Path, initial_config: dict | None = None) -> Path:
    """Create a fake repo root with optional wake_config.json."""
    rr = tmp_path / "fake_repo"
    (rr / "models" / "wake_words").mkdir(parents=True)
    if initial_config is not None:
        (rr / "wake_config.json").write_text(
            json.dumps(initial_config, indent=2),
            encoding="utf-8",
        )
    return rr


def _make_stub(tmp_path: Path, name: str = "stub.onnx") -> Path:
    p = tmp_path / name
    p.write_bytes(b"stub-onnx-contents")
    return p


# ─── Role inference ───────────────────────────────────────────────────


class TestInferRole:
    def test_cv_go_is_start(self):
        assert _infer_role_from_name("cv_go") == "start"

    def test_cv_over_is_stop(self):
        assert _infer_role_from_name("cv_over") == "stop"

    def test_hey_jarvis_is_start(self):
        assert _infer_role_from_name("hey_jarvis") == "start"

    def test_alpha_stop_is_stop(self):
        assert _infer_role_from_name("alpha_stop") == "stop"

    def test_message_end_is_stop(self):
        assert _infer_role_from_name("message_end") == "stop"

    def test_case_insensitive_stop(self):
        assert _infer_role_from_name("CV_OVER") == "stop"

    def test_case_insensitive_start(self):
        assert _infer_role_from_name("Hey_Jarvis") == "start"


# ─── deploy() merge semantics ─────────────────────────────────────────


class TestDeployBootstrap:
    """When wake_config.json doesn't exist, deploy() creates one."""

    def test_deploys_into_empty_repo(self, tmp_path):
        rr = _make_repo(tmp_path, initial_config=None)
        stub = _make_stub(tmp_path)

        deploy(
            stub,
            phrase="hey clarity-v",
            threshold=0.6,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert data["cooldown_seconds"] == 0.5
        assert len(data["models"]) == 1
        m = data["models"][0]
        assert m["name"] == "stub"
        assert m["threshold"] == 0.6
        assert m["role"] == "start"
        assert m["model_path"] == "models/wake_words/stub.onnx"


class TestDeployMergesNotNukes:
    """The original defect — cv_go + cv_over must survive a deploy."""

    def test_preserves_existing_entries(self, tmp_path):
        existing = {
            "models": [
                {
                    "name": "cv_go",
                    "model_path": "models/wake_words/cv_go.onnx",
                    "threshold": 0.472,
                    "role": "start",
                },
                {
                    "name": "cv_over",
                    "model_path": "models/wake_words/cv_over.onnx",
                    "threshold": 0.483,
                    "role": "stop",
                },
            ],
            "cooldown_seconds": 0.5,
        }
        rr = _make_repo(tmp_path, initial_config=existing)
        stub = _make_stub(tmp_path, name="custom.onnx")

        deploy(
            stub,
            phrase="custom",
            threshold=0.6,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        names = [m["name"] for m in data["models"]]
        assert "cv_go" in names
        assert "cv_over" in names
        assert "custom" in names
        assert len(names) == 3

        cv_go = next(m for m in data["models"] if m["name"] == "cv_go")
        cv_over = next(m for m in data["models"] if m["name"] == "cv_over")
        assert cv_go["threshold"] == 0.472
        assert cv_go["role"] == "start"
        assert cv_over["threshold"] == 0.483
        assert cv_over["role"] == "stop"

    def test_updates_existing_entry_in_place_no_duplicate(self, tmp_path):
        """Re-deploying a model with the SAME name updates the existing
        entry; it does not append a duplicate."""
        existing = {
            "models": [
                {
                    "name": "cv_over",
                    "model_path": "models/wake_words/cv_over.onnx",
                    "threshold": 0.483,
                    "role": "stop",
                },
            ],
            "cooldown_seconds": 0.5,
        }
        rr = _make_repo(tmp_path, initial_config=existing)
        # Source named cv_over.onnx — retraining the existing stop-wake.
        retrain = _make_stub(tmp_path, name="cv_over.onnx")

        deploy(
            retrain,
            phrase="cv over",
            threshold=0.55,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        # Exactly one entry — no duplicate.
        assert len(data["models"]) == 1
        m = data["models"][0]
        assert m["name"] == "cv_over"
        assert m["threshold"] == 0.55  # updated
        assert m["role"] == "stop"  # re-inferred from name

    def test_role_inferred_from_name(self, tmp_path):
        """A model whose name ends in 'over' deploys as a stop-wake even
        if there's no existing entry to copy the role from."""
        rr = _make_repo(tmp_path, initial_config=None)
        stop_model = _make_stub(tmp_path, name="my_over.onnx")

        deploy(
            stop_model,
            phrase="my over",
            threshold=0.5,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert data["models"][0]["role"] == "stop"

    def test_threshold_from_args_not_hardcoded(self, tmp_path):
        """The validated threshold passed in is what gets written."""
        rr = _make_repo(tmp_path, initial_config=None)
        stub = _make_stub(tmp_path)

        deploy(
            stub,
            phrase="x",
            threshold=0.789,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert data["models"][0]["threshold"] == 0.789


class TestDeployPreservesCooldown:
    def test_preserves_custom_cooldown(self, tmp_path):
        existing = {
            "models": [],
            "cooldown_seconds": 0.3,
        }
        rr = _make_repo(tmp_path, initial_config=existing)
        stub = _make_stub(tmp_path)

        deploy(
            stub,
            phrase="x",
            threshold=0.5,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert data["cooldown_seconds"] == 0.3

    def test_defaults_cooldown_when_missing(self, tmp_path):
        rr = _make_repo(tmp_path, initial_config=None)
        stub = _make_stub(tmp_path)

        deploy(
            stub,
            phrase="x",
            threshold=0.5,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert data["cooldown_seconds"] == 0.5


class TestDeployHandlesBadConfig:
    """A corrupt existing config is recovered into a fresh one; never
    crashes the deploy."""

    def test_malformed_json_recovers(self, tmp_path):
        rr = tmp_path / "fake_repo"
        (rr / "models" / "wake_words").mkdir(parents=True)
        (rr / "wake_config.json").write_text(
            "{not valid json",
            encoding="utf-8",
        )
        stub = _make_stub(tmp_path)

        ok = deploy(
            stub,
            phrase="x",
            threshold=0.5,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )
        assert ok is True

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert len(data["models"]) == 1
        assert data["models"][0]["name"] == "stub"

    def test_non_dict_top_level_recovers(self, tmp_path):
        rr = tmp_path / "fake_repo"
        (rr / "models" / "wake_words").mkdir(parents=True)
        # Valid JSON but not a dict at the top level.
        (rr / "wake_config.json").write_text("[]", encoding="utf-8")
        stub = _make_stub(tmp_path)

        ok = deploy(
            stub,
            phrase="x",
            threshold=0.5,
            repo_root=rr,
            config_path=rr / "wake_config.json",
        )
        assert ok is True

        data = json.loads(
            (rr / "wake_config.json").read_text(encoding="utf-8"),
        )
        assert isinstance(data, dict)
        assert len(data["models"]) == 1
