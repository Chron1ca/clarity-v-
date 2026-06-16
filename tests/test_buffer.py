"""
LastDictationBuffer tests — in-memory, thread-safe, no I/O.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clarity_v.buffer import LastDictationBuffer, get_default


class TestBasics:
    def test_empty_on_construction(self):
        b = LastDictationBuffer()
        assert b.is_empty()
        assert b.get() == ""
        assert b.get_info() is None

    def test_set_then_get(self):
        b = LastDictationBuffer()
        b.set("hello world", language="en")
        assert not b.is_empty()
        assert b.get() == "hello world"
        info = b.get_info()
        assert info is not None
        assert info.text == "hello world"
        assert info.language == "en"
        assert info.timestamp > 0

    def test_set_overwrites_previous(self):
        b = LastDictationBuffer()
        b.set("first")
        b.set("second")
        assert b.get() == "second"

    def test_clear(self):
        b = LastDictationBuffer()
        b.set("hello")
        b.clear()
        assert b.is_empty()
        assert b.get() == ""

    def test_get_info_returns_copy(self):
        """Mutating the returned DictationEntry must NOT alter the buffer."""
        b = LastDictationBuffer()
        b.set("original", language="en")
        info = b.get_info()
        info.text = "mutated"
        info.language = "xx"
        # Buffer unchanged
        again = b.get_info()
        assert again.text == "original"
        assert again.language == "en"


class TestTimestamp:
    def test_timestamp_recent(self):
        before = time.time()
        b = LastDictationBuffer()
        b.set("hi")
        after = time.time()
        info = b.get_info()
        assert before <= info.timestamp <= after

    def test_new_set_updates_timestamp(self):
        b = LastDictationBuffer()
        b.set("first")
        first_ts = b.get_info().timestamp
        time.sleep(0.01)
        b.set("second")
        second_ts = b.get_info().timestamp
        assert second_ts > first_ts


class TestConcurrency:
    def test_concurrent_sets_dont_race(self):
        """50 threads write different strings concurrently; the final
        buffer value should be one of the writes (no partial / corrupted)."""
        b = LastDictationBuffer()
        threads = []
        for i in range(50):
            t = threading.Thread(target=lambda i=i: b.set(f"thread_{i}"))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        final = b.get()
        assert final.startswith("thread_")
        # Parses as an integer
        n = int(final.removeprefix("thread_"))
        assert 0 <= n < 50

    def test_concurrent_read_during_write_does_not_crash(self):
        b = LastDictationBuffer()
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                b.set(f"x_{i}")
                i += 1

        def reader():
            while not stop.is_set():
                b.get()
                b.get_info()

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        time.sleep(0.2)
        stop.set()
        for t in threads:
            t.join(timeout=2)
            assert not t.is_alive()


class TestDefaultSingleton:
    def test_same_instance(self):
        a = get_default()
        b = get_default()
        assert a is b
