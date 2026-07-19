"""Browser models: signature stability, snapshot hashing, bundle filters."""

from __future__ import annotations

from datetime import UTC, datetime

from website_agent.browser.models import (
    ConsoleEvent,
    ElementRecord,
    NetworkEvent,
    ObservationBundle,
    PageSnapshot,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _element(element_id: str = "e1", **overrides: object) -> ElementRecord:
    defaults: dict[str, object] = {
        "element_id": element_id,
        "tag": "button",
        "role": "button",
        "name": "Sign up",
        "selectors": ['[data-testid="signup"]'],
    }
    defaults.update(overrides)
    return ElementRecord(**defaults)  # type: ignore[arg-type]


def _snapshot(elements: list[ElementRecord], url: str = "https://ex.com/a") -> PageSnapshot:
    return PageSnapshot(url=url, title="t", captured_at=NOW, elements=elements)


def test_signature_ignores_ephemeral_id_and_case_whitespace() -> None:
    a = _element("e1", name="  Sign Up ")
    b = _element("e42", name="sign up")
    assert a.signature == b.signature


def test_signature_distinguishes_role_name_and_author_ids() -> None:
    base = _element()
    assert base.signature != _element(role="link").signature
    assert base.signature != _element(name="Log in").signature
    assert base.signature != _element(testid="other").signature
    assert base.signature != _element(dom_id="other").signature


def test_snapshot_hash_stable_under_element_reordering() -> None:
    e1, e2 = _element("e1", name="A"), _element("e2", name="B")
    assert _snapshot([e1, e2]).snapshot_hash == _snapshot([e2, e1]).snapshot_hash


def test_snapshot_hash_ignores_url_fragment_but_not_path() -> None:
    elements = [_element()]
    assert (
        _snapshot(elements, "https://ex.com/a#section").snapshot_hash
        == _snapshot(elements, "https://ex.com/a").snapshot_hash
    )
    assert (
        _snapshot(elements, "https://ex.com/b").snapshot_hash
        != _snapshot(elements, "https://ex.com/a").snapshot_hash
    )


def test_snapshot_hash_changes_when_interactive_surface_changes() -> None:
    one = _snapshot([_element("e1", name="A")])
    two = _snapshot([_element("e1", name="A"), _element("e2", name="B")])
    assert one.snapshot_hash != two.snapshot_hash


def test_element_lookup_by_id() -> None:
    snap = _snapshot([_element("e1"), _element("e2", name="Other")])
    assert snap.element("e2") is snap.elements[1]
    assert snap.element("e99") is None


def test_bundle_error_and_failure_filters() -> None:
    bundle = ObservationBundle(
        step_id="step_0001",
        console=[
            ConsoleEvent(level="log", text="fine", at=NOW),
            ConsoleEvent(level="error", text="boom", at=NOW),
            ConsoleEvent(level="pageerror", text="uncaught", at=NOW),
        ],
        network=[
            NetworkEvent(method="GET", url="/ok", status=200, ok=True, at=NOW),
            NetworkEvent(method="GET", url="/missing", status=404, ok=False, at=NOW),
            NetworkEvent(
                method="GET", url="/dead", status=None, ok=False, failure="net::ERR", at=NOW
            ),
        ],
    )
    assert [e.text for e in bundle.console_errors] == ["boom", "uncaught"]
    assert [e.url for e in bundle.failed_requests] == ["/missing", "/dead"]
