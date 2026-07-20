"""QA engine over real snapshots extracted from the fixture site."""

from __future__ import annotations

import pytest

from website_agent.browser.session import BrowserSession
from website_agent.qa.engine import QaEngine
from website_agent.qa.models import QaContext

pytestmark = pytest.mark.integration


async def test_qa_flags_missing_label_from_real_snapshot(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/contact.html")
    snapshot = await session.snapshot()

    report = QaEngine().analyze(QaContext(run_id="run_qa", snapshots=(snapshot,)))

    # The contact form has one input with no label, aria-label, or accessible text.
    missing = [f for f in report.findings if f.kind == "missing_label"]
    assert missing, f"expected a missing_label finding, got {[f.kind for f in report.findings]}"
    assert missing[0].url.endswith("/contact.html")


async def test_qa_report_is_clean_for_well_formed_page(
    session: BrowserSession, static_basic_url: str
) -> None:
    await session.goto(f"{static_basic_url}/about.html")
    snapshot = await session.snapshot()
    report = QaEngine().analyze(QaContext(run_id="run_qa", snapshots=(snapshot,)))
    # about.html is a simple, labelled, non-empty page: no accessibility findings.
    assert not report.has_blocking_issues
    assert all(f.kind != "missing_label" for f in report.findings)
