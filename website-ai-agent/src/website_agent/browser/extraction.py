"""Page snapshot extraction: DOM walk, accessibility attributes, selector synthesis.

Design rationale (design D6): one in-page JS pass collects raw facts about interactive
elements (tag, role, accessible name, author-assigned identifiers, geometry); Python then
assigns stable inventory IDs and synthesizes an ordered list of candidate selectors per
element, priority data-testid > id > role+name > structural CSS path. The LLM never sees
or invents selectors; it references inventory IDs only. The structural CSS path is always
present as the guaranteed-resolvable fallback (built from nth-of-type chains, unique by
construction). Accessible-name computation is a pragmatic subset of the ARIA algorithm:
aria-label, aria-labelledby, associated <label>, visible text, then placeholder/title/alt;
full spec fidelity is not worth the complexity for planning and QA purposes.
"""

from __future__ import annotations

from typing import Any, Protocol

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.clock import Clock

# Cap keeps prompts and state bounded on pathological pages; snapshot marks truncation.
DEFAULT_MAX_ELEMENTS = 300

EXTRACTION_JS = r"""
() => {
  const IMPLICIT_ROLES = {
    a: (el) => el.hasAttribute('href') ? 'link' : null,
    button: () => 'button',
    select: () => 'combobox',
    textarea: () => 'textbox',
    summary: () => 'button',
    input: (el) => {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      const map = {
        button: 'button', submit: 'button', reset: 'button', image: 'button',
        checkbox: 'checkbox', radio: 'radio', range: 'slider',
        number: 'spinbutton', search: 'searchbox',
      };
      if (t === 'hidden') return null;
      return map[t] || 'textbox';
    },
  };

  const INTERACTIVE_SELECTOR = [
    'a[href]', 'button', 'input', 'select', 'textarea', 'summary',
    '[role=button]', '[role=link]', '[role=checkbox]', '[role=radio]',
    '[role=combobox]', '[role=listbox]', '[role=menuitem]', '[role=tab]',
    '[role=switch]', '[role=textbox]', '[role=searchbox]',
    '[onclick]', '[contenteditable=true]', '[contenteditable=""]',
  ].join(',');

  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  const accessibleName = (el) => {
    const ariaLabel = clean(el.getAttribute('aria-label'));
    if (ariaLabel) return ariaLabel;

    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.split(/\s+/)
        .map((id) => {
          const ref = document.getElementById(id);
          return ref ? clean(ref.textContent) : '';
        })
        .filter(Boolean);
      if (parts.length) return parts.join(' ').slice(0, 120);
    }

    if (el.labels && el.labels.length) {
      const text = clean(Array.from(el.labels).map((l) => l.textContent).join(' '));
      if (text) return text.slice(0, 120);
    }

    const text = clean(el.textContent);
    if (text) return text.slice(0, 120);

    for (const attr of ['placeholder', 'title', 'alt', 'value']) {
      const v = clean(el.getAttribute(attr));
      if (v) return v.slice(0, 120);
    }
    return '';
  };

  const cssPath = (el) => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.documentElement) {
      if (node.id) { parts.unshift('#' + CSS.escape(node.id)); break; }
      const tag = node.tagName.toLowerCase();
      let index = 1;
      let sibling = node.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === node.tagName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };

  const results = [];
  const seen = new Set();
  for (const el of document.querySelectorAll(INTERACTIVE_SELECTOR)) {
    if (seen.has(el)) continue;
    seen.add(el);

    const tag = el.tagName.toLowerCase();
    const explicitRole = clean(el.getAttribute('role')).toLowerCase() || null;
    const implicit = IMPLICIT_ROLES[tag] ? IMPLICIT_ROLES[tag](el) : null;
    const clickable = el.hasAttribute('onclick') || el.isContentEditable;
    const role = explicitRole || implicit || (clickable ? 'button' : null);
    if (!role) continue;

    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const visible = style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;

    results.push({
      tag,
      role,
      name: accessibleName(el),
      testid: el.getAttribute('data-testid'),
      dom_id: el.id || null,
      input_type: tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : null,
      href: tag === 'a' && el.href ? el.href : null,
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      visible,
      in_viewport: visible && rect.bottom > 0 && rect.right > 0
        && rect.top < window.innerHeight && rect.left < window.innerWidth,
      editable: el.isContentEditable || ['input', 'textarea', 'select'].includes(tag),
      css_path: cssPath(el),
      rect: [rect.x, rect.y, rect.width, rect.height],
    });
  }

  return {
    url: window.location.href,
    title: document.title,
    viewport: [window.innerWidth, window.innerHeight],
    elements: results,
  };
}
"""


class EvaluatesJs(Protocol):
    """The one page capability extraction needs; real pages and test fakes both satisfy it."""

    async def evaluate(self, expression: str) -> Any:  # pragma: no cover - protocol
        ...


def synthesize_selectors(raw: dict[str, Any]) -> list[str]:
    """Ordered candidate selectors for one raw element record.

    Priority: data-testid, then id, then role+name, then the structural CSS path.
    Attribute-value selectors are used for testid and id (immune to CSS identifier
    escaping issues); the role selector is skipped for names that would break the
    Playwright selector grammar.
    """
    selectors: list[str] = []
    if (testid := raw.get("testid")) and '"' not in testid:
        selectors.append(f'[data-testid="{testid}"]')
    if (dom_id := raw.get("dom_id")) and '"' not in dom_id:
        selectors.append(f'[id="{dom_id}"]')
    name = raw.get("name") or ""
    if raw.get("role") and name and len(name) <= 60 and '"' not in name and "\n" not in name:
        selectors.append(f'role={raw["role"]}[name="{name}"]')
    if css_path := raw.get("css_path"):
        selectors.append(f"css={css_path}")
    if not selectors:
        # Guaranteed fallback so ElementRecord's min-one-selector invariant holds.
        selectors.append(f"css={raw.get('tag', '*')}")
    return selectors


def build_inventory(
    raw_elements: list[dict[str, Any]], *, max_elements: int = DEFAULT_MAX_ELEMENTS
) -> tuple[list[ElementRecord], bool]:
    """Assign stable IDs and selectors; truncate by salience when over the cap.

    Salience order when truncating: in-viewport visible first, then visible,
    then hidden; original DOM order within each band (matches reading order).
    """
    truncated = len(raw_elements) > max_elements
    if truncated:
        bands = (
            [e for e in raw_elements if e.get("visible") and e.get("in_viewport")],
            [e for e in raw_elements if e.get("visible") and not e.get("in_viewport")],
            [e for e in raw_elements if not e.get("visible")],
        )
        raw_elements = [e for band in bands for e in band][:max_elements]

    records = []
    for index, raw in enumerate(raw_elements, start=1):
        records.append(
            ElementRecord(
                element_id=f"e{index}",
                tag=raw.get("tag", ""),
                role=raw.get("role", ""),
                name=raw.get("name", "") or "",
                testid=raw.get("testid"),
                dom_id=raw.get("dom_id"),
                input_type=raw.get("input_type"),
                href=raw.get("href"),
                disabled=bool(raw.get("disabled")),
                visible=bool(raw.get("visible")),
                in_viewport=bool(raw.get("in_viewport")),
                editable=bool(raw.get("editable")),
                selectors=synthesize_selectors(raw),
                rect=tuple(raw.get("rect", (0, 0, 0, 0))),
            )
        )
    return records, truncated


async def extract_snapshot(
    page: EvaluatesJs, clock: Clock, *, max_elements: int = DEFAULT_MAX_ELEMENTS
) -> PageSnapshot:
    """Run the in-page extraction script and build the typed snapshot."""
    payload = await page.evaluate(EXTRACTION_JS)
    elements, truncated = build_inventory(payload["elements"], max_elements=max_elements)
    return PageSnapshot(
        url=payload["url"],
        title=payload["title"],
        captured_at=clock.now(),
        elements=elements,
        truncated=truncated,
        viewport=tuple(payload.get("viewport", (0, 0))),
    )
