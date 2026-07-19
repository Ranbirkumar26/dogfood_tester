"""Extraction: selector synthesis priority, inventory building, truncation salience."""

from __future__ import annotations

from typing import Any

from website_agent.browser.extraction import (
    EXTRACTION_JS,
    build_inventory,
    extract_snapshot,
    synthesize_selectors,
)
from website_agent.core.clock import FixedClock


def _raw(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tag": "button",
        "role": "button",
        "name": "Get Started",
        "testid": None,
        "dom_id": None,
        "input_type": None,
        "href": None,
        "disabled": False,
        "visible": True,
        "in_viewport": True,
        "editable": False,
        "css_path": "main > button:nth-of-type(1)",
        "rect": [10, 20, 100, 30],
    }
    base.update(overrides)
    return base


def test_selector_priority_testid_then_id_then_role_then_css() -> None:
    selectors = synthesize_selectors(_raw(testid="cta", dom_id="main-cta"))
    assert selectors == [
        '[data-testid="cta"]',
        '[id="main-cta"]',
        'role=button[name="Get Started"]',
        "css=main > button:nth-of-type(1)",
    ]


def test_role_selector_skipped_for_grammar_breaking_names() -> None:
    quoted = synthesize_selectors(_raw(name='Say "hi"'))
    assert not any(s.startswith("role=") for s in quoted)
    long = synthesize_selectors(_raw(name="x" * 61))
    assert not any(s.startswith("role=") for s in long)
    multiline = synthesize_selectors(_raw(name="a\nb"))
    assert not any(s.startswith("role=") for s in multiline)


def test_css_path_always_present_as_fallback() -> None:
    assert synthesize_selectors(_raw())[-1] == "css=main > button:nth-of-type(1)"
    # Degenerate record with nothing usable still yields one selector.
    assert synthesize_selectors({"tag": "button"}) == ["css=button"]


def test_build_inventory_assigns_sequential_ids() -> None:
    records, truncated = build_inventory([_raw(), _raw(name="Second"), _raw(name="Third")])
    assert [r.element_id for r in records] == ["e1", "e2", "e3"]
    assert truncated is False


def test_build_inventory_truncates_by_salience() -> None:
    hidden = _raw(name="hidden", visible=False, in_viewport=False)
    below_fold = _raw(name="below", visible=True, in_viewport=False)
    on_screen = _raw(name="onscreen", visible=True, in_viewport=True)
    records, truncated = build_inventory([hidden, below_fold, on_screen], max_elements=2)
    assert truncated is True
    assert [r.name for r in records] == ["onscreen", "below"]  # hidden dropped first


def test_build_inventory_preserves_dom_order_within_bands() -> None:
    records, _ = build_inventory([_raw(name=f"n{i}") for i in range(5)], max_elements=3)
    assert [r.name for r in records] == ["n0", "n1", "n2"]


class FakePage:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.evaluated_with: str | None = None

    async def evaluate(self, expression: str) -> dict[str, Any]:
        self.evaluated_with = expression
        return self.payload


async def test_extract_snapshot_builds_typed_snapshot(fixed_clock: FixedClock) -> None:
    page = FakePage(
        {
            "url": "https://ex.com/",
            "title": "Example",
            "viewport": [1280, 900],
            "elements": [_raw(testid="cta")],
        }
    )
    snapshot = await extract_snapshot(page, fixed_clock)
    assert page.evaluated_with == EXTRACTION_JS
    assert snapshot.url == "https://ex.com/"
    assert snapshot.title == "Example"
    assert snapshot.viewport == (1280, 900)
    assert snapshot.captured_at == fixed_clock.now()
    assert snapshot.elements[0].element_id == "e1"
    assert snapshot.elements[0].selectors[0] == '[data-testid="cta"]'
