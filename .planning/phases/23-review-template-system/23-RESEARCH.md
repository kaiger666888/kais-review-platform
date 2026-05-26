# Phase 23: Review Template System - Research

**Researched:** 2026-05-18
**Domain:** Template-driven UI rendering per source_system + phase (FastAPI + Jinja2 + HTMX + Alpine.js)
**Confidence:** HIGH

## Summary

This phase creates a YAML-driven template system that selects and renders different review UI partials based on `source_system` + `phase`. The codebase already has an established YAML loading pattern in `app/core/policy.py` (PolicyEngine with `yaml.safe_load`, JSON Schema validation, and directory-based loading) that should be the blueprint for the template definition loader. The template rendering engine sits between the route handlers in `app/web/routes.py` and the Jinja2 partials in `app/templates/partials/`, selecting which partials to include based on the active template.

A critical discovery is that the V2 `ShotCard` model (`app/models/shot_card.py`) does **not** have a `source_system` field -- only the V1 `Review` model does. The template selection key must therefore derive `source_system` from either the `project_id` prefix (e.g., projects created by movie-agent carry a convention) or a new field on `ShotCard`. This gap must be resolved in the plan. The `narrative_context` JSONB field is the natural place to carry `phase` information.

The desktop workstation renders Shot Card detail via `_decision_panel.html` + `_media_player.html` (OOB swap pattern). The mobile PWA renders via `_mobile_card.html` with Alpine.js client-side state. Both must be template-aware, but the insertion points are different: desktop uses server-side Jinja2 include selection, mobile needs template data passed in the JSON API response.

**Primary recommendation:** Create a `TemplateRegistry` modeled after the existing `PolicyEngine` pattern: YAML config files in `app/templates/config/`, loaded at startup, keyed by `source_system:phase`, with a Jinja2 include-path resolver that returns the correct partial names for desktop and mobile rendering.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Template YAML loading + validation | API / Backend | -- | Matches existing PolicyEngine pattern, runs at startup |
| Template selection logic | API / Backend | -- | Needs source_system + phase from DB, server-side decision |
| Desktop HTML partial rendering | Frontend Server (SSR) | -- | Jinja2 server-side includes, HTMX OOB swaps |
| Mobile card rendering data | API / Backend | Browser / Client | API returns template metadata; Alpine.js uses it for conditional display |
| Fallback template selection | API / Backend | -- | Default template returned when no source_system/phase match |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyYAML | 6.0.2 | Template config file parsing | Already installed, same pattern as policy YAML loading [VERIFIED: requirements.txt] |
| Jinja2 | 3.1.2 | Template rendering with conditional includes | Already in project via FastAPI [VERIFIED: pip show] |
| jinja2-fragments | 1.8.0 | Block-level partial rendering | Already installed, imported in routes.py [VERIFIED: requirements.txt] |
| jsonschema | 4.26.0 | YAML template config validation | Already installed, mirrors PolicyEngine JSON Schema validation [VERIFIED: requirements.txt] |
| FastAPI | 0.136.1 | Route handlers, TemplateResponse | Framework standard [VERIFIED: requirements.txt] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Alpine.js | 3.15.12 (CDN) | Client-side conditional display for mobile template features | Mobile PWA cards that need template-aware UI toggles |
| HTMX | 2.0.9 (CDN) | Desktop partial swaps with template-selected includes | Desktop workstation decision panel + media player |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| YAML template configs | JSON template configs | YAML is already the project standard for config (policies use YAML), more readable for layout rules |
| Jinja2 include selection | Full template per source_system | Include selection reuses existing partials, avoids HTML duplication |
| Server-side template selection | Client-side Alpine.js template logic | Server-side is more testable, matches HTMX pattern, keeps template logic out of client |

**Installation:**
```bash
# No new packages needed -- all dependencies already in requirements.txt
```

## Package Legitimacy Audit

> No new packages are installed in this phase. All dependencies already exist in requirements.txt.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
[Request: GET /partials/shot-card-detail/{id}]
         |
         v
[Route Handler: shot_card_detail_partial()]
         |
         v
[Fetch ShotCard from DB] --> (shot_card.project_id, narrative_context)
         |
         v
[TemplateRegistry.resolve(source_system, phase)]
         |
         +--> Match found? --> TemplateConfig(desktop_partials, mobile_partials, ...)
         |                              |
         +--> No match? -----> DefaultTemplateConfig
                                        |
                                        v
                    [Route returns decision_panel with template-aware includes]
                                        |
                       +----------------+----------------+
                       |                                 |
                       v                                 v
            [Desktop: Jinja2 includes            [Mobile: API returns
             selected partials]                    template_config in JSON]
```

### Recommended Project Structure
```
app/
├── core/
│   └── template_registry.py    # TemplateRegistry: YAML loading, validation, selection
├── templates/
│   ├── config/                 # YAML template definitions (new)
│   │   ├── default.yaml        # Fallback template
│   │   ├── movie-agent.yaml    # kais-movie-agent templates
│   │   └── gold-team.yaml      # kais-gold-team templates
│   ├── partials/
│   │   ├── _decision_panel.html      # (existing, becomes template-aware)
│   │   ├── _media_player.html        # (existing, becomes template-aware)
│   │   ├── _mobile_card.html         # (existing, becomes template-aware)
│   │   ├── _template_candidate_grid.html   # NEW: movie-agent side-by-side candidates
│   │   ├── _template_risk_assessment.html  # NEW: gold-team risk display
│   │   └── ...
│   └── ...
├── web/
│   └── routes.py               # (existing, modified to use TemplateRegistry)
└── ...
```

### Pattern 1: YAML Template Definition + Registry (mirrors PolicyEngine)

**What:** Template configs stored as YAML files, loaded into an in-memory registry at startup, keyed by `source_system:phase`.

**When to use:** Every review rendering decision -- desktop and mobile.

**Example YAML config:**
```yaml
# app/templates/config/movie-agent.yaml
name: movie-agent-templates
version: "1.0"
source_system: kais-movie-agent
templates:
  art-direction:
    desktop:
      decision_panel: "partials/_template_candidate_grid.html"
      media_player: "partials/_media_player.html"  # default media
      show_scores: true
      show_candidates: true
      candidate_layout: "side-by-side"
    mobile:
      card_variant: "candidate-swipe"  # Alpine.js uses this to show candidate switcher
      show_scores: true
  quality-gate:
    desktop:
      decision_panel: "partials/_decision_panel.html"  # default
      media_player: "partials/_media_player.html"
      show_scores: true
      show_candidates: false
    mobile:
      card_variant: "default"
  _default:  # fallback for unknown phases in this source_system
    desktop:
      decision_panel: "partials/_decision_panel.html"
      media_player: "partials/_media_player.html"
    mobile:
      card_variant: "default"
```

```python
# app/core/template_registry.py
# Source: mirrors app/core/policy.py pattern
import yaml
import jsonschema
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class TemplateConfig:
    """Resolved template configuration for a specific rendering context."""
    desktop_decision_panel: str = "partials/_decision_panel.html"
    desktop_media_player: str = "partials/_media_player.html"
    mobile_card_variant: str = "default"
    show_scores: bool = False
    show_candidates: bool = True
    candidate_layout: str = "grid"
    extra_fields: dict = field(default_factory=dict)


class TemplateRegistry:
    """Load YAML template configs, resolve by source_system + phase."""

    def __init__(self) -> None:
        self._templates: dict[str, dict] = {}  # source_system -> phase -> config

    def load_from_directory(self, dirpath: str) -> None:
        for filepath in sorted(Path(dirpath).glob("*.yaml")):
            with open(filepath) as f:
                data = yaml.safe_load(f)
            # Validate and index by source_system
            source_system = data.get("source_system", "")
            self._templates[source_system] = data.get("templates", {})

    def resolve(self, source_system: str, phase: str | None = None) -> TemplateConfig:
        """Resolve template config with fallback chain."""
        source_templates = self._templates.get(source_system, {})
        if phase and phase in source_templates:
            raw = source_templates[phase]
        elif "_default" in source_templates:
            raw = source_templates["_default"]
        else:
            return TemplateConfig()  # global default

        desktop = raw.get("desktop", {})
        mobile = raw.get("mobile", {})
        return TemplateConfig(
            desktop_decision_panel=desktop.get("decision_panel", "partials/_decision_panel.html"),
            desktop_media_player=desktop.get("media_player", "partials/_media_player.html"),
            mobile_card_variant=mobile.get("card_variant", "default"),
            show_scores=desktop.get("show_scores", False),
            show_candidates=desktop.get("show_candidates", True),
            candidate_layout=desktop.get("candidate_layout", "grid"),
            extra_fields={k: v for k, v in desktop.items()
                         if k not in ("decision_panel", "media_player", "show_scores",
                                      "show_candidates", "candidate_layout")},
        )
```

### Pattern 2: Template-Aware Route Handler

**What:** Route handlers query the TemplateRegistry to select which Jinja2 partials to include.

**When to use:** Desktop workstation detail endpoint, mobile API card bundle response.

**Example:**
```python
# Modified route handler in app/web/routes.py
@router.get("/partials/shot-card-detail/{shot_card_id}")
async def shot_card_detail_partial(request: Request, shot_card_id: int):
    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)
    if shot_card is None:
        return HTMLResponse("<p>Shot card not found.</p>", status_code=404)

    # Resolve template
    source_system = _derive_source_system(shot_card)
    phase = (shot_card.narrative_context or {}).get("phase", "")
    template = template_registry.resolve(source_system, phase)

    return templates.TemplateResponse(request, "partials/_template_wrapper.html", {
        "shot": shot_card,
        "template": template,
    })
```

### Pattern 3: Template Wrapper Partial (Jinja2 dynamic include)

**What:** A wrapper template that uses Jinja2 `{% include %}` with a variable path to select the correct partial.

**When to use:** When the decision panel content varies by template.

**Example:**
```html
<!-- app/templates/partials/_template_wrapper.html -->
{% if shot %}
<div class="space-y-4">
  {% include template.desktop_decision_panel ignore missing with context %}
</div>

<!-- Media Preview OOB swap -->
<div id="media-preview" hx-swap-oob="true">
  {% include template.desktop_media_player ignore missing with context %}
</div>
{% endif %}
```

### Anti-Patterns to Avoid
- **Full page template per source_system:** Don't create complete page templates per source_system. Use partial selection within the existing workstation layout. This would duplicate the entire 3-column structure per source_system.
- **Client-side template logic for desktop:** Don't push template selection to Alpine.js for desktop. HTMX + server-side include selection is the established pattern. The mobile side can receive template metadata via the API for Alpine.js conditionals.
- **Hardcoded source_system strings in templates:** Don't embed source_system checks in Jinja2 `{% if %}` blocks. Use the template registry to resolve which partials to include.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML config validation | Custom validation logic | jsonschema with a TEMPLATE_JSON_SCHEMA | Mirrors PolicyEngine pattern, consistent validation, good error messages |
| Template config loading | Custom file reader | TemplateRegistry.load_from_directory() | Mirrors PolicyEngine.load_from_directory(), handles sorted glob, indexing |
| Fallback template selection | if/elif chain per source_system | TemplateRegistry.resolve() with fallback chain | Centralized logic, testable, extensible |
| Dynamic partial selection | String concatenation of include paths | Jinja2 `{% include var_name %}` with `ignore missing` | Jinja2 natively supports variable includes, handles missing gracefully |

**Key insight:** The PolicyEngine in `app/core/policy.py` is the exact architectural blueprint for the TemplateRegistry. Same YAML loading, same JSON Schema validation, same directory-based loading, same in-memory registry pattern. Copy that structure.

## Runtime State Inventory

> Not a rename/refactor/migration phase. Omitted.

## Common Pitfalls

### Pitfall 1: ShotCard model has no source_system field
**What goes wrong:** Template resolution requires `source_system`, but `ShotCard` only has `project_id`. Code that tries `shot_card.source_system` will fail with `AttributeError`.
**Why it happens:** V2 data model was designed around Shot Cards (pipeline-level), while `source_system` is a V1 Review concept (submission-level). The V1 Review model has `source_system` but ShotCard does not.
**How to avoid:** Either (a) add a `source_system` column to ShotCard, or (b) derive it from `project_id` via a convention mapping, or (c) store it in `narrative_context` JSONB. Option (a) is cleanest but requires a migration. Option (c) is least intrusive. The planner should decide.
**Warning signs:** Any code referencing `shot_card.source_system` without a resolution strategy.

### Pitfall 2: Jinja2 include with variable path and security
**What goes wrong:** Jinja2 `{% include user_controlled_string %}` can be a sandbox escape if the variable contains path traversal (e.g., `../../etc/passwd`).
**Why it happens:** Template names come from YAML config which is developer-controlled (not user-controlled), but defensive coding is still important.
**How to avoid:** Validate template paths in the registry to only allow `partials/` prefix. Use a whitelist of allowed partial names instead of arbitrary paths.
**Warning signs:** Any `{% include %}` where the variable comes from request parameters instead of the registry.

### Pitfall 3: Mobile API doesn't use Jinja2 -- it's JSON
**What goes wrong:** The mobile PWA doesn't render HTML server-side for cards. It fetches JSON from `/api/v1/mobile/cards` and renders via Alpine.js. Adding "template partials" for mobile means passing template metadata in the JSON response, not rendering HTML.
**Why it happens:** Mobile uses a fundamentally different rendering architecture (client-side Alpine.js vs server-side Jinja2).
**How to avoid:** The `MobileShotCardBundle` model should include a `template_config` field (or similar) that tells Alpine.js which UI variant to render. Don't try to server-side render mobile cards per template.
**Warning signs:** Creating Jinja2 partials for mobile card rendering.

### Pitfall 4: Existing templates use hardcoded shot_card fields
**What goes wrong:** `_decision_panel.html` directly accesses `shot.visual_bundle.prompt`, `shot.narrative_context`, etc. A movie-agent template might want to emphasize candidates while a gold-team template wants to show task parameters -- but the existing partials are structured around ShotCard fields.
**Why it happens:** Current partials were built for a single review type. The template system needs to compose different field subsets.
**How to avoid:** Create specialized partials per source_system (`_template_candidate_grid.html` for movie-agent, `_template_risk_assessment.html` for gold-team) that extract the right fields. The default template continues using `_decision_panel.html` as-is.
**Warning signs:** Trying to make `_decision_panel.html` handle all source_system types with conditionals.

## Code Examples

### Template YAML with JSON Schema validation
```python
# Source: mirrors app/core/policy.py POLICY_JSON_SCHEMA pattern
TEMPLATE_JSON_SCHEMA = {
    "type": "object",
    "required": ["name", "version", "source_system", "templates"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "pattern": r"^\d+\.\d+$"},
        "source_system": {"type": "string", "minLength": 1},
        "templates": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "desktop": {
                        "type": "object",
                        "properties": {
                            "decision_panel": {"type": "string"},
                            "media_player": {"type": "string"},
                            "show_scores": {"type": "boolean"},
                            "show_candidates": {"type": "boolean"},
                            "candidate_layout": {"type": "string", "enum": ["grid", "side-by-side", "stacked"]},
                        },
                    },
                    "mobile": {
                        "type": "object",
                        "properties": {
                            "card_variant": {"type": "string"},
                            "show_scores": {"type": "boolean"},
                        },
                    },
                },
            },
        },
    },
}
```

### Movie-agent candidate grid partial (new)
```html
<!-- app/templates/partials/_template_candidate_grid.html -->
<!-- Movie-agent specific: side-by-side candidate images with scores -->
{% if shot and shot.visual_bundle and shot.visual_bundle.get('candidates') %}
<div class="space-y-3">
  <h3 class="text-xs font-semibold uppercase text-gray-500">Candidates</h3>
  <div class="grid grid-cols-2 gap-3">
    {% for cand in shot.visual_bundle.candidates %}
    <div class="border-2 rounded-lg overflow-hidden
                {% if cand.get('score') and cand.score >= 0.8 %}border-green-600{% else %}border-gray-700{% endif %}">
      {% if cand.get('keyframes', {}).get('first', {}).get('url') %}
      <img class="w-full aspect-video object-cover"
           src="{{ cand.keyframes.first.url }}"
           alt="Candidate {{ loop.index }}" />
      {% endif %}
      <div class="p-2 bg-gray-800">
        <div class="flex items-center justify-between">
          <span class="text-xs text-gray-400">C{{ loop.index }}</span>
          {% if cand.get('score') is not none %}
          <span class="text-xs font-mono px-1.5 py-0.5 rounded
                       {{ 'bg-green-900 text-green-300' if cand.score >= 0.7 else 'bg-yellow-900 text-yellow-300' }}">
            {{ "%.0f" | format(cand.score * 100) }}%
          </span>
          {% endif %}
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
  <!-- Selection buttons -->
  <div class="flex gap-2">
    <button class="flex-1 py-1.5 bg-green-600 hover:bg-green-500 text-white text-sm rounded font-semibold"
            hx-post="/shot-cards/{{ shot.id }}/approve"
            hx-vals='{"selected": "{{ shot.visual_bundle.candidates[0].candidate_id if shot.visual_bundle.candidates else '' }}"}'
            hx-target="#shot-queue-list"
            hx-swap="innerHTML">
      Select & Approve
    </button>
  </div>
</div>
{% endif %}
```

### Gold-team risk assessment partial (new)
```html
<!-- app/templates/partials/_template_risk_assessment.html -->
<!-- Gold-team specific: task parameters + risk assessment display -->
{% if shot %}
<div class="space-y-3">
  <!-- Task Parameters -->
  {% set nc = shot.narrative_context or {} %}
  <div>
    <h3 class="text-xs font-semibold uppercase text-gray-500">Task Parameters</h3>
    {% if nc.get('task_type') %}
    <div class="mt-1 flex items-center gap-2">
      <span class="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded font-mono">{{ nc.task_type }}</span>
    </div>
    {% endif %}
    {% if nc.get('task_params') %}
    <div class="mt-2 text-xs text-gray-400">
      {% for key, val in nc.task_params.items() %}
      <div class="flex gap-2"><span class="text-gray-500">{{ key }}:</span> <span>{{ val }}</span></div>
      {% endfor %}
    </div>
    {% endif %}
  </div>

  <!-- Risk Assessment -->
  <div>
    <h3 class="text-xs font-semibold uppercase text-gray-500">Risk Assessment</h3>
    <div class="mt-1">
      {% set risk = nc.get('risk_score', 0.5) %}
      <div class="flex items-center gap-2">
        <div class="flex-1 bg-gray-700 rounded-full h-2">
          <div class="h-2 rounded-full {{ 'bg-red-500' if risk >= 0.7 else ('bg-yellow-500' if risk >= 0.3 else 'bg-green-500') }}"
               style="width: {{ risk * 100 }}%"></div>
        </div>
        <span class="text-xs font-mono {{ 'text-red-400' if risk >= 0.7 else 'text-gray-400' }}">
          {{ "%.0f" | format(risk * 100) }}%
        </span>
      </div>
    </div>
  </div>

  <!-- Standard context + prompts (reused from default) -->
  {% include "partials/_decision_panel.html" %}
</div>
{% endif %}
```

### Source system derivation helper
```python
# Source: new code needed because ShotCard lacks source_system
def _derive_source_system(shot_card) -> str:
    """Derive source_system from ShotCard data.

    Strategy: check narrative_context first, then project_id prefix.
    """
    nc = shot_card.narrative_context or {}
    # Option A: explicit field in narrative_context
    if nc.get("source_system"):
        return nc["source_system"]
    # Option B: project_id convention (e.g., "movie-agent:proj-001")
    if shot_card.project_id.startswith("movie-agent"):
        return "kais-movie-agent"
    if shot_card.project_id.startswith("gold-team"):
        return "kais-gold-team"
    # Fallback
    return "unknown"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single hardcoded review UI | Template-conditional UI per source_system | This phase | Different review experiences per AI system |
| Jinja2 full-page templates | Jinja2 partial includes selected by registry | Established in Phase 20 | Pattern exists, this phase extends it |

**Deprecated/outdated:**
- `_review_detail.html` (V1 Review partial): Still exists for V1 dashboard but Shot Card review uses `_decision_panel.html` + `_media_player.html`. Template system targets V2 Shot Card rendering only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `source_system` can be derived from `narrative_context` or `project_id` convention | Architecture Patterns | If no convention exists, need a migration to add the field |
| A2 | `phase` is stored in `narrative_context` JSONB field | Architecture Patterns | If phase is not in narrative_context, need to find alternative source |
| A3 | The movie-agent `metadata.phase` values (art-direction, character, voice, scene, storyboard, quality-gate) will be stored in `narrative_context.phase` for ShotCards | Architecture Patterns | If phase naming differs, templates won't match |
| A4 | Jinja2 `{% include variable_path %}` with `ignore missing` works safely for partial selection | Code Examples | Jinja2 does support this but need to verify with the project's Jinja2 version |
| A5 | No new Python packages are needed for this phase | Standard Stack | If YAML template features exceed PyYAML capabilities |

## Open Questions

1. **Where does `source_system` live on ShotCard?**
   - What we know: ShotCard model has no `source_system` column. V1 Review has it. Policy YAML files reference `source_system` in conditions.
   - What's unclear: Is there an established convention for encoding source_system in project_id or narrative_context?
   - Recommendation: Add `source_system` to the `narrative_context` JSONB (least intrusive, no migration needed) OR add it as a proper column (cleaner, requires migration). Planner should decide based on query needs.

2. **How does `phase` flow into the ShotCard?**
   - What we know: V1 Reviews store `metadata.phase` (art-direction, quality-gate, etc.). ShotCard has `narrative_context` but no explicit `phase` field documented.
   - What's unclear: Does the aggregation pipeline (Phase 16) already set `narrative_context.phase` when creating ShotCards?
   - Recommendation: If not already set, the template system should read from `narrative_context.phase` and the integration documentation should specify that source_systems must include it.

3. **Should mobile card rendering use Alpine.js conditionals or pre-rendered HTML?**
   - What we know: Mobile uses client-side Alpine.js rendering from JSON API responses. Desktop uses server-side Jinja2.
   - What's unclear: Whether mobile should receive `template_config` as JSON metadata (Alpine.js conditionals) or receive pre-rendered HTML snippets.
   - Recommendation: Add `template_config` dict to `MobileShotCardBundle` response. Alpine.js uses `x-if` conditions based on `card.template_config.card_variant`. This matches the existing mobile architecture.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyYAML | Template config loading | Yes | 6.0.2 | -- |
| Jinja2 | Template rendering | Yes | 3.1.2 | -- |
| jsonschema | YAML validation | Yes | 4.26.0 | -- |
| jinja2-fragments | Block rendering | Yes | 1.8.0 | -- |
| Alpine.js (CDN) | Mobile UI conditionals | Yes | 3.15.12 | -- |
| HTMX (CDN) | Desktop partial swaps | Yes | 2.0.9 | -- |

**Missing dependencies with no fallback:** none

**Missing dependencies with fallback:** none

## Validation Architecture

> nyquist_validation is explicitly `false` in `.planning/config.json`. Section omitted per protocol.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Pydantic + jsonschema for YAML config validation |
| V4 Access Control | yes | Existing JWT auth on route handlers |

### Known Threat Patterns for Jinja2 + YAML Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Jinja2 Server-Side Template Injection (SSTI) | Tampering | Template paths come from YAML config (developer-controlled), not user input. Validate paths start with `partials/`. |
| YAML deserialization (unsafe load) | Tampering | Use `yaml.safe_load()` only (never `yaml.load()`). Matches PolicyEngine pattern. |
| Path traversal via include variable | Tampering | Whitelist allowed partial names in registry. Never use user-controlled strings in `{% include %}`. |

## Sources

### Primary (HIGH confidence)
- Codebase: `app/core/policy.py` -- YAML loading, JSON Schema validation, directory loading pattern (blueprint for TemplateRegistry)
- Codebase: `app/core/policy_v2.py` -- PolicyEngine extension pattern (blueprint for extending existing engine)
- Codebase: `app/models/shot_card.py` -- ShotCard model (no source_system field -- key discovery)
- Codebase: `app/models/schema.py` -- Review model (has source_system field)
- Codebase: `app/web/routes.py` -- Route handler patterns, Jinja2Templates + Jinja2Blocks usage
- Codebase: `app/templates/partials/_decision_panel.html` -- Current desktop rendering
- Codebase: `app/templates/partials/_media_player.html` -- Current media rendering
- Codebase: `app/templates/partials/_mobile_card.html` -- Current mobile rendering
- Codebase: `app/policies/movie_agent_phases.yaml` -- Phase names for movie-agent
- Codebase: `app/policies/gold_team_risk.yaml` -- Phase names for gold-team
- Codebase: `app/api/v1/mobile.py` -- Mobile API, MobileShotCardBundle model
- Codebase: `requirements.txt` -- All dependencies verified present

### Secondary (MEDIUM confidence)
- [Jinja2 Fragments Documentation](https://jinja2-fragments.readthedocs.io/) -- Partial rendering patterns for HTMX
- [FastAPI Templates Docs](https://fastapi.tiangolo.com/advanced/templates/) -- Jinja2 integration

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all packages already installed and verified
- Architecture: HIGH - mirrors existing PolicyEngine pattern, established codebase patterns
- Pitfalls: HIGH - discovered critical gap (ShotCard lacks source_system) through codebase analysis

**Research date:** 2026-05-18
**Valid until:** 2026-06-18 (stable architecture, no fast-moving dependencies)
