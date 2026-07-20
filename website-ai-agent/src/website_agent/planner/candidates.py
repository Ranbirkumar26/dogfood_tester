"""Deterministic candidate generation from a page snapshot.

Design rationale (docs/architecture/planner.md, section 2, step 1): candidates come from
code, not the model. Every interactive inventory element expands to its afforded actions,
frontier pages expand to navigate candidates. Risk classification here is the input to the
policy gate (design D12): submit-like buttons and elements whose name matches destructive
verbs are flagged so a safe-explore run never triggers them. Being conservative about risk
is deliberate: a false "destructive" only skips an action; a false "safe" could delete data.
"""

from __future__ import annotations

import re

from website_agent.browser.models import ElementRecord, PageSnapshot
from website_agent.core.types import RiskClass
from website_agent.planner.models import ActionCandidate, ActionType

# Accessible-name patterns that mark an action as destructive (checked case-insensitively).
_DESTRUCTIVE = re.compile(
    r"\b(delete|remove|destroy|drop|deactivate|close account|cancel subscription|"
    r"unsubscribe|log ?out|sign ?out|reset|wipe|purge|revoke)\b",
    re.IGNORECASE,
)
# Names or types that mutate state without being destructive.
_MUTATING = re.compile(
    r"\b(submit|save|send|create|add|update|apply|confirm|pay|checkout|subscribe|"
    r"post|upload|publish)\b",
    re.IGNORECASE,
)


def classify_risk(*, name: str, tag: str, input_type: str | None, action: ActionType) -> RiskClass:
    """Risk class for an action, from the element's accessible name and kind."""
    if _DESTRUCTIVE.search(name):
        return RiskClass.DESTRUCTIVE
    is_submit = input_type in ("submit", "image") or (tag == "button" and _MUTATING.search(name))
    if action is ActionType.FILL:
        return RiskClass.SAFE  # typing into a field is safe; submitting it is the mutation
    if is_submit or _MUTATING.search(name):
        return RiskClass.MUTATING
    return RiskClass.SAFE


def _afforded_action(element: ElementRecord) -> ActionType | None:
    """The single primary action for an element, or None if not actionable."""
    if element.disabled or not element.visible:
        return None
    if element.tag == "select" or element.role in ("combobox", "listbox"):
        return ActionType.SELECT
    if element.editable and element.tag in ("input", "textarea"):
        if element.input_type in ("checkbox", "radio", "submit", "button", "image"):
            return ActionType.CLICK
        return ActionType.FILL
    if element.role in ("link", "button", "menuitem", "tab", "checkbox", "radio", "switch"):
        return ActionType.CLICK
    return ActionType.CLICK  # onclick/contenteditable fall through to click


def generate_candidates(
    snapshot: PageSnapshot, *, frontier_urls: list[str] | None = None
) -> list[ActionCandidate]:
    """All afforded actions on the current page plus navigations to frontier pages."""
    candidates: list[ActionCandidate] = []

    for element in snapshot.elements:
        action = _afforded_action(element)
        if action is None:
            continue
        risk = classify_risk(
            name=element.name, tag=element.tag, input_type=element.input_type, action=action
        )
        label = _label(action, element)
        candidates.append(
            ActionCandidate(
                action=action,
                element_id=element.element_id,
                element_signature=element.signature,
                label=label,
                risk=risk,
                target_url=element.href if action is ActionType.CLICK else None,
            )
        )

    for url in frontier_urls or []:
        candidates.append(
            ActionCandidate(
                action=ActionType.NAVIGATE,
                element_id=None,
                element_signature=None,
                label=f"navigate to {url}",
                risk=RiskClass.SAFE,
                target_url=url,
            )
        )

    return candidates


def _label(action: ActionType, element: ElementRecord) -> str:
    name = element.name or element.role or element.tag
    return f"{action.value} {element.role} '{name}'".strip()
