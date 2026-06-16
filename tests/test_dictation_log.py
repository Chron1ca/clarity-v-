"""
DictationLog tests — file-based append-only log with size rotation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


from clarity_v.dictation_log import DictationLog


class TestBasics:
    def test_first_file_is_001(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        assert log.current_path.name == "dictation_log_001.jsonl"

    def test_creates_log_dir(self, tmp_path):
        target = tmp_path / "nested" / "logs"
        log = DictationLog(log_dir=target)
        log.append("hello")
        assert target.exists()

    def test_append_writes_entry(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        log.append("hello world", language="en")
        path = log.current_path
        assert path.exists()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["text"] == "hello world"
        assert entry["lang"] == "en"
        assert "ts" in entry

    def test_multiple_appends_one_file(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        for i in range(5):
            log.append(f"entry {i}")
        lines = log.current_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        for i, line in enumerate(lines):
            entry = json.loads(line)
            assert entry["text"] == f"entry {i}"

    def test_empty_text_skipped(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        log.append("")
        # File not created at all (nothing to write).
        assert not log.current_path.exists()


class TestUnicode:
    def test_portuguese_round_trip(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        text = "Olá, como estás? Está tudo ótimo."
        log.append(text, language="pt")
        entries = list(log.iter_entries())
        assert len(entries) == 1
        assert entries[0]["text"] == text
        assert entries[0]["lang"] == "pt"

    def test_japanese(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        text = "こんにちは、元気ですか?"
        log.append(text, language="ja")
        entries = list(log.iter_entries())
        assert entries[0]["text"] == text

    def test_newlines_preserved(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        text = "line one\nline two\nline three"
        log.append(text)
        entries = list(log.iter_entries())
        assert entries[0]["text"] == text


class TestRotation:
    def test_rotates_at_max_bytes(self, tmp_path):
        # Tiny threshold so the test rotates in one or two appends.
        log = DictationLog(log_dir=tmp_path, max_bytes=200)
        # 250-character payload — JSON-encoded line is well over 200 B.
        big = "x" * 250
        log.append(big)
        first_path = log.current_path
        assert first_path.name == "dictation_log_001.jsonl"
        # Second append should rotate.
        log.append(big)
        assert log.current_path.name == "dictation_log_002.jsonl"
        # Two separate files exist.
        files = log.list_files()
        assert len(files) == 2

    def test_resumes_at_highest_existing(self, tmp_path):
        # Pre-create three log files; constructor should pick up at 003.
        for n in [1, 2, 3]:
            p = tmp_path / f"dictation_log_{n:03d}.jsonl"
            p.write_text('{"ts":"x","lang":"","text":"a"}\n', encoding="utf-8")
        log = DictationLog(log_dir=tmp_path, max_bytes=10_000)
        assert log.current_path.name == "dictation_log_003.jsonl"

    def test_ignores_non_matching_files(self, tmp_path):
        # Random other files in the directory should not confuse rotation.
        (tmp_path / "readme.txt").write_text("hi")
        (tmp_path / "dictation_log_garbage.jsonl").write_text("x")
        log = DictationLog(log_dir=tmp_path)
        assert log.current_path.name == "dictation_log_001.jsonl"


class TestIteration:
    def test_iter_entries_across_files(self, tmp_path):
        log = DictationLog(log_dir=tmp_path, max_bytes=80)
        # Each entry is ~60+ bytes JSON; we expect rotation between writes.
        log.append("entry-one")
        log.append("entry-two")
        log.append("entry-three")
        log.append("entry-four")
        all_entries = list(log.iter_entries())
        assert len(all_entries) == 4
        # Entries are in chronological (file-name) order.
        texts = [e["text"] for e in all_entries]
        assert texts == ["entry-one", "entry-two", "entry-three", "entry-four"]

    def test_skips_malformed_lines(self, tmp_path):
        log = DictationLog(log_dir=tmp_path)
        log.append("good")
        # Manually corrupt the log mid-file
        with open(log.current_path, "a", encoding="utf-8") as f:
            f.write("not valid json\n")
            f.write(json.dumps({"ts": "x", "lang": "", "text": "also good"}) + "\n")
        entries = list(log.iter_entries())
        # Two parseable entries; bad line silently skipped.
        assert len(entries) == 2
        assert entries[0]["text"] == "good"
        assert entries[1]["text"] == "also good"
