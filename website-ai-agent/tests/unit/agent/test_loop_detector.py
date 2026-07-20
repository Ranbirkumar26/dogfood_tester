"""Loop detector: signature stability, repeat counting, poisoning."""

from __future__ import annotations

from website_agent.agent.loop_detector import (
    is_poisoned,
    observe_signature,
    poison_branch,
    state_signature,
)
from website_agent.state.models import LoopSignal


def test_signature_stable_for_equivalent_state() -> None:
    a = state_signature(url="https://ex.com/p/1", content_hash="h", last_action_signature="s")
    b = state_signature(url="https://ex.com/p/2", content_hash="h", last_action_signature="s")
    assert a == b  # template-collapsed URLs


def test_signature_varies_with_content_and_action() -> None:
    base = state_signature(url="https://ex.com/", content_hash="h1", last_action_signature="s1")
    assert base != state_signature(
        url="https://ex.com/", content_hash="h2", last_action_signature="s1"
    )
    assert base != state_signature(
        url="https://ex.com/", content_hash="h1", last_action_signature="s2"
    )


def test_repeat_count_grows_with_recurrence() -> None:
    signal = LoopSignal()
    signal, r0 = observe_signature(signal, "sig")
    assert r0 == 0  # brand new
    signal, r1 = observe_signature(signal, "sig")
    assert r1 == 1  # seen once before
    signal, r2 = observe_signature(signal, "sig")
    assert r2 == 2


def test_distinct_signatures_do_not_count_as_repeats() -> None:
    signal = LoopSignal()
    signal, _ = observe_signature(signal, "a")
    signal, repeats = observe_signature(signal, "b")
    assert repeats == 0


def test_ring_buffer_is_bounded() -> None:
    signal = LoopSignal()
    for i in range(50):
        signal, _ = observe_signature(signal, f"sig{i}")
    assert len(signal.recent) <= 12


def test_poisoning() -> None:
    signal = LoopSignal()
    assert not is_poisoned(signal, "sig")
    signal = poison_branch(signal, "sig")
    assert is_poisoned(signal, "sig")
    assert not is_poisoned(signal, "other")
