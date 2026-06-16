"""
State manager tests.

Pure in-memory; the concurrency test fires 100 state changes from a worker
thread and asserts all subscribers received all events in order.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


from clarity_v.state import State, StateManager, get_default


class TestStateEnum:
    def test_values(self):
        assert State.IDLE.value == "idle"
        assert State.RECORDING.value == "recording"
        assert State.PROCESSING.value == "processing"
        assert State.COMMIT_WAITING.value == "commit_waiting"
        assert State.ERROR.value == "error"

    def test_distinct(self):
        # Make sure no two states share a value.
        values = [s.value for s in State]
        assert len(values) == len(set(values))

    def test_five_states_total(self):
        # Lock the count — the bar's mental model is exactly five.
        # Any addition needs deliberate design, not accident.
        assert len(list(State)) == 5


class TestStateManagerBasics:
    def test_default_initial_idle(self):
        m = StateManager()
        assert m.state == State.IDLE

    def test_set_state(self):
        m = StateManager()
        m.set_state(State.RECORDING)
        assert m.state == State.RECORDING

    def test_info_dict(self):
        m = StateManager()
        m.set_state(State.RECORDING, {"mode": "dictation"})
        assert m.info == {"mode": "dictation"}

    def test_info_isolated(self):
        # Mutating the returned info dict should NOT affect internal state.
        m = StateManager()
        m.set_state(State.RECORDING, {"mode": "dictation"})
        returned = m.info
        returned["mode"] = "command"
        assert m.info == {"mode": "dictation"}

    def test_set_error(self):
        m = StateManager()
        m.set_error("boom")
        assert m.state == State.ERROR
        assert m.info == {"message": "boom"}


class TestSubscribers:
    def test_subscriber_called(self):
        m = StateManager()
        received = []
        m.subscribe(lambda s, i: received.append((s, i)))
        m.set_state(State.RECORDING, {"k": "v"})
        assert received == [(State.RECORDING, {"k": "v"})]

    def test_multiple_subscribers_all_called(self):
        m = StateManager()
        received_a = []
        received_b = []
        m.subscribe(lambda s, i: received_a.append(s))
        m.subscribe(lambda s, i: received_b.append(s))
        m.set_state(State.RECORDING)
        m.set_state(State.PROCESSING)
        assert received_a == [State.RECORDING, State.PROCESSING]
        assert received_b == [State.RECORDING, State.PROCESSING]

    def test_subscriber_exception_isolated(self):
        m = StateManager()
        received = []
        m.subscribe(lambda s, i: (_ for _ in ()).throw(RuntimeError("boom")))
        m.subscribe(lambda s, i: received.append(s))
        # First subscriber raises; second must still fire.
        m.set_state(State.RECORDING)
        assert received == [State.RECORDING]
        assert m.state == State.RECORDING  # state still set

    def test_unsubscribe(self):
        m = StateManager()
        received = []

        def cb(s, i):
            received.append(s)

        m.subscribe(cb)
        m.set_state(State.RECORDING)
        m.unsubscribe(cb)
        m.set_state(State.PROCESSING)
        assert received == [State.RECORDING]

    def test_unsubscribe_missing_is_noop(self):
        m = StateManager()
        m.unsubscribe(lambda s, i: None)  # not previously subscribed
        # No exception = success.

    def test_clear_subscribers(self):
        m = StateManager()
        received = []
        m.subscribe(lambda s, i: received.append(s))
        m.subscribe(lambda s, i: received.append(s))
        m.clear_subscribers()
        m.set_state(State.RECORDING)
        assert received == []


class TestConcurrency:
    def test_100_state_changes_from_worker_thread(self):
        """Worker thread fires 100 state changes; 3 subscribers must
        receive all 100 each, in order, with no lost or duplicated events."""
        m = StateManager()
        received: list[list[State]] = [[], [], []]

        def make_cb(idx):
            def cb(s, i):
                received[idx].append(s)

            return cb

        for i in range(3):
            m.subscribe(make_cb(i))

        # Alternate IDLE / RECORDING 50 times each = 100 transitions.
        states_in_order = []

        def worker():
            for i in range(100):
                s = State.RECORDING if (i % 2 == 0) else State.IDLE
                states_in_order.append(s)
                m.set_state(s)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)
        assert not t.is_alive(), "Worker hung"

        for idx in range(3):
            assert received[idx] == states_in_order, (
                f"Subscriber {idx} got {len(received[idx])} of 100; "
                f"order match: {received[idx] == states_in_order}"
            )

    def test_subscribe_during_set_state_does_not_deadlock(self):
        """A subscriber that subscribes another callback during dispatch
        must not deadlock. The new callback fires on the NEXT set_state."""
        m = StateManager()
        new_received = []

        def existing_cb(s, i):
            m.subscribe(lambda ns, ni: new_received.append(ns))

        m.subscribe(existing_cb)
        m.set_state(State.RECORDING)
        # 'new_received' should be empty (new sub registered after dispatch).
        assert new_received == []
        m.set_state(State.RECORDING)
        assert new_received == [State.RECORDING]


class TestDefaultSingleton:
    def test_get_default_returns_same_instance(self):
        a = get_default()
        b = get_default()
        assert a is b
