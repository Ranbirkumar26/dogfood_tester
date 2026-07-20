# Module: prompts

Layer 2 capability: versioned prompt templates with strict rendering. Prompts are load-bearing code and live as reviewable files inside the package (they ship in the wheel).

## Template format

One file per template, `<name>.md`, split into a system section and a user section by a `---USER---` marker line. Variables use `$name` / `${name}` (Python `string.Template`):

```
You are a $role QA agent exploring $url.
---USER---
Current page inventory:
$inventory

Goal: $goal
```

## Rendering

`PromptManager.render(name, variables)` takes variables as a mapping (not kwargs, so a template may use any identifier including `name`). Rendering is strict both directions:

- a variable the template needs but the caller omitted is a `ConfigError` (missing),
- a variable the caller passed but the template does not use is a `ConfigError` (unused).

Strictness catches silent prompt drift: a renamed template variable that no longer substitutes would otherwise surface only as degraded agent behavior.

## Versioning

`version_of(name)` is a content hash of the template file: it changes exactly when the template changes, with no manual bookkeeping. Role code logs the version with every call, and it feeds cassette keys so a template edit invalidates stale recordings (design D13).

## Where templates live

Role templates (`planner.md`, `executor.md`, `reviewer.md`, and the docs/QA templates) are added in their implementing phases (6 onward) under `src/website_agent/prompts/templates/`. The manager can also be pointed at any directory for tests.

## Usage

```python
manager = PromptManager()  # ships-with-package templates
prompt = manager.render("planner", {"role": "explorer", "url": url, "inventory": inv, "goal": goal})
result = await model_manager.complete("planner", prompt, Plan)
```
