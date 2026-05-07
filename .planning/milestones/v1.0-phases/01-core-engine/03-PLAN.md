---
phase: 01-core-engine
plan: 03
type: execute
wave: 2
depends_on:
  - 01
files_modified:
  - app/core/policy.py
  - app/api/v1/policies.py
  - app/policies/default.yaml
autonomous: true
requirements:
  - POLC-01
  - POLC-02
  - POLC-03
  - POLC-04
  - POLC-05
  - POLC-06

must_haves:
  truths:
    - "YAML policy files are loaded and evaluated against review submissions"
    - "Policy rules route items to AUTO/HUMAN/AI_AUDIT/BLOCK based on AND/OR conditions and risk_score thresholds"
    - "Invalid YAML policies are rejected with clear validation errors via JSON Schema"
    - "Policies can be created, read, updated, and deleted via REST API with version tracking"
    - "Policy changes are logged in the audit trail"
    - "When no rules match, the default disposition is HUMAN (safe conservative default)"
  artifacts:
    - path: "app/core/policy.py"
      provides: "YAML policy parser, JSON Schema validator, AND/OR condition evaluator, risk-tier routing"
      exports: ["PolicyEngine", "PolicyEvaluationError", "evaluate_policy"]
    - path: "app/api/v1/policies.py"
      provides: "CRUD API endpoints for policy management"
      exports: ["router"]
    - path: "app/policies/default.yaml"
      provides: "Default policy rules for initial seed data"
  key_links:
    - from: "app/api/v1/policies.py"
      to: "app/core/policy.py"
      via: "import PolicyEngine for CRUD operations and validation"
      pattern: "from app\\.core\\.policy import"
    - from: "app/core/policy.py"
      to: "app/policies/default.yaml"
      via: "load YAML policy files from disk"
      pattern: "yaml\\.safe_load"
    - from: "app/api/v1/policies.py"
      to: "app/core/audit.py"
      via: "append_audit on policy changes (POLC-06)"
      pattern: "append_audit|audit"
---

<objective>
Implement the YAML policy engine with JSON Schema validation and AND/OR condition evaluation, plus the Policy CRUD API with version tracking.

Purpose: The policy engine is the core decision-maker. Every review submission passes through it to determine routing (AUTO/HUMAN/AI_AUDIT/BLOCK). JSON Schema validation catches policy errors at load time. The CRUD API lets external systems manage policies without code changes.

Output: Working policy engine that evaluates YAML rules against review payloads, validates policies via JSON Schema, and exposes full CRUD via REST API.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-core-engine/01-CONTEXT.md
@.planning/phases/01-core-engine/01-RESEARCH.md
@.planning/phases/01-core-engine/01-SUMMARY.md

<interfaces>
<!-- From Plan 01: Foundation types -->

From app/models/schema.py:
```python
class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    id: Mapped[int]  # primary key
    name: Mapped[str]  # unique, not null
    version: Mapped[str]  # not null
    content: Mapped[str]  # raw YAML, not null
    is_active: Mapped[bool]  # default True
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class Review(Base):
    __tablename__ = "reviews"
    # has: type, source_system, priority, risk_score, metadata_json, state, disposition
```

From app/core/audit.py:
```python
async def append_audit(session, review_id, action, actor, **kwargs) -> AuditEntry: ...
```

From app/core/database.py:
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]: ...
```

From app/models/schemas.py:
```python
class Disposition(str, Enum):
    AUTO = "AUTO"
    HUMAN = "HUMAN"
    AI_AUDIT = "AI_AUDIT"
    BLOCK = "BLOCK"

class PolicyCreateRequest(BaseModel):
    name: str
    content: str

class PolicyUpdateRequest(BaseModel):
    content: str

class PolicyResponse(BaseModel):
    name: str
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement YAML policy engine with JSON Schema validation and condition evaluator</name>
  <files>app/core/policy.py, app/policies/default.yaml</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: YAML AND/OR conditions + risk_score threshold, default to HUMAN)
    - .planning/phases/01-core-engine/01-RESEARCH.md (Pattern 4: YAML Policy Engine with JSON Schema Validation)
    - .planning/research/PITFALLS.md (Pitfall 5: YAML Policy Silent Failures)
    - app/models/schema.py (Review model for field access)
  </read_first>
  <action>
1. Create `app/policies/` directory and `app/policies/default.yaml`:
   ```yaml
   name: default_routing
   version: "1.0"
   rules:
     - name: auto_approve_low_risk
       priority: 1
       conditions:
         operator: AND
         checks:
           - field: risk_score
             operator: less_than
             value: 0.3
           - field: source_system
             operator: equals
             value: kais-movie-agent
       disposition: AUTO

     - name: human_review_high_risk
       priority: 2
       conditions:
         operator: OR
         checks:
           - field: risk_score
             operator: greater_than
             value: 0.7
           - field: priority
             operator: equals
             value: critical
       disposition: HUMAN

     - name: block_flagged_content
       priority: 3
       conditions:
         operator: AND
         checks:
           - field: metadata.flagged
             operator: equals
             value: true
       disposition: BLOCK
   ```

2. Create `app/core/policy.py`:

   **JSON Schema constant:**
   ```python
   POLICY_JSON_SCHEMA = {
       "type": "object",
       "required": ["name", "version", "rules"],
       "properties": {
           "name": {"type": "string", "minLength": 1},
           "version": {"type": "string", "pattern": r"^\d+\.\d+$"},
           "rules": {
               "type": "array",
               "minItems": 1,
               "items": {
                   "type": "object",
                   "required": ["name", "priority", "conditions", "disposition"],
                   "properties": {
                       "name": {"type": "string", "minLength": 1},
                       "priority": {"type": "integer", "minimum": 1},
                       "conditions": {
                           "type": "object",
                           "required": ["operator", "checks"],
                           "properties": {
                               "operator": {"type": "string", "enum": ["AND", "OR"]},
                               "checks": {
                                   "type": "array",
                                   "minItems": 1,
                                   "items": {
                                       "type": "object",
                                       "required": ["field", "operator", "value"],
                                       "properties": {
                                           "field": {"type": "string"},
                                           "operator": {"type": "string", "enum": [
                                               "equals", "not_equals",
                                               "greater_than", "less_than",
                                               "greater_than_or_equal", "less_than_or_equal",
                                               "contains", "in"
                                           ]},
                                           "value": {}
                                       }
                                   }
                               }
                           }
                       },
                       "disposition": {"type": "string", "enum": ["AUTO", "HUMAN", "AI_AUDIT", "BLOCK"]}
                   }
               }
           }
       }
   }
   ```

   **Exceptions:**
   ```python
   class PolicyError(Exception): pass
   class PolicyValidationError(PolicyError): pass
   class PolicyEvaluationError(PolicyError): pass
   ```

   **PolicyEngine class:**
   ```python
   class PolicyEngine:
       def __init__(self):
           self._policies: dict[str, dict] = {}  # name -> parsed policy dict

       def validate_policy(self, yaml_content: str) -> dict:
           """Parse and validate YAML policy. Returns parsed dict or raises PolicyValidationError."""
           try:
               data = yaml.safe_load(yaml_content)
           except yaml.YAMLError as e:
               raise PolicyValidationError(f"Invalid YAML syntax: {e}")
           try:
               jsonschema.validate(instance=data, schema=POLICY_JSON_SCHEMA)
           except jsonschema.ValidationError as e:
               raise PolicyValidationError(f"Policy schema validation failed: {e.message}")
           return data

       def load_policy(self, name: str, yaml_content: str) -> dict:
           """Validate and store a policy. Returns parsed dict."""
           data = self.validate_policy(yaml_content)
           self._policies[name] = data
           return data

       def load_from_file(self, filepath: str) -> dict:
           """Load policy from YAML file path."""
           with open(filepath, 'r') as f:
               content = f.read()
           data = self.validate_policy(content)
           self._policies[data['name']] = data
           return data

       def load_from_directory(self, dirpath: str) -> list[str]:
           """Load all .yaml files from directory. Returns list of loaded policy names."""
           loaded = []
           for filename in sorted(Path(dirpath).glob("*.yaml")):
               data = self.load_from_file(str(filename))
               loaded.append(data['name'])
           return loaded

       def evaluate(self, review_data: dict, policy_name: str | None = None) -> Disposition:
           """Evaluate review data against policy rules. Returns Disposition enum.
           If policy_name is None, evaluates against all loaded policies in alphabetical order.
           Default to HUMAN if no rules match."""
           policies_to_eval = (
               {policy_name: self._policies[policy_name]}
               if policy_name and policy_name in self._policies
               else dict(sorted(self._policies.items()))
           )

           for policy_name, policy in policies_to_eval.items():
               rules = sorted(policy.get("rules", []), key=lambda r: r.get("priority", 999))
               for rule in rules:
                   if self._evaluate_conditions(rule["conditions"], review_data):
                       return Disposition(rule["disposition"])

           # Default: HUMAN review (safe conservative default per CONTEXT.md)
           return Disposition.HUMAN

       def _evaluate_conditions(self, conditions: dict, data: dict) -> bool:
           """Evaluate an AND/OR condition block against review data."""
           operator = conditions["operator"]
           checks = conditions["checks"]

           if operator == "AND":
               return all(self._evaluate_check(check, data) for check in checks)
           elif operator == "OR":
               return any(self._evaluate_check(check, data) for check in checks)
           return False

       def _evaluate_check(self, check: dict, data: dict) -> bool:
           """Evaluate a single condition check. Supports dotted field access (e.g., metadata.flagged)."""
           field = check["field"]
           op = check["operator"]
           expected = check["value"]

           # Support dotted field access: "metadata.flagged" -> data["metadata"]["flagged"]
           value = data
           for part in field.split("."):
               if isinstance(value, dict) and part in value:
                   value = value[part]
               else:
                   return False  # Field not found, condition fails

           # Evaluate operator
           if op == "equals":
               return value == expected
           elif op == "not_equals":
               return value != expected
           elif op == "greater_than":
               return value > expected
           elif op == "less_than":
               return value < expected
           elif op == "greater_than_or_equal":
               return value >= expected
           elif op == "less_than_or_equal":
               return value <= expected
           elif op == "contains":
               return expected in value if isinstance(value, (str, list)) else False
           elif op == "in":
               return value in expected if isinstance(expected, (list, tuple)) else False
           return False

       def get_policy(self, name: str) -> dict | None:
           return self._policies.get(name)

       def list_policies(self) -> list[str]:
           return sorted(self._policies.keys())

       def remove_policy(self, name: str) -> bool:
           if name in self._policies:
               del self._policies[name]
               return True
           return False
   ```

   **Module-level convenience function:**
   ```python
   # Global engine instance, initialized at startup
   _engine: PolicyEngine | None = None

   def get_policy_engine() -> PolicyEngine:
       global _engine
       if _engine is None:
           _engine = PolicyEngine()
       return _engine
   ```

   **Important:** The PolicyEngine stores parsed policies in memory. On startup (in main.py lifespan), load default policies from `app/policies/` directory. When policies are created/updated via API, the in-memory cache is updated AND the database stores the versioned YAML content.
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.core.policy import PolicyEngine, PolicyValidationError, POLICY_JSON_SCHEMA, Disposition

engine = PolicyEngine()

# Test loading default.yaml
import os
policy_path = os.path.join(os.path.dirname(__file__), 'app', 'policies', 'default.yaml')
assert os.path.exists(policy_path), 'default.yaml must exist'
loaded = engine.load_from_file(policy_path)
assert loaded['name'] == 'default_routing', f'Expected default_routing, got {loaded[\"name\"]}'
print(f'Loaded policy: {loaded[\"name\"]} with {len(loaded[\"rules\"])} rules')

# Test evaluation: low risk from movie-agent -> AUTO
result = engine.evaluate({
    'risk_score': 0.1,
    'source_system': 'kais-movie-agent',
    'priority': 'normal',
})
assert result == Disposition.AUTO, f'Expected AUTO for low risk, got {result}'
print(f'Low risk -> {result.value}')

# Test evaluation: high risk -> HUMAN
result = engine.evaluate({
    'risk_score': 0.8,
    'source_system': 'kais-movie-agent',
    'priority': 'normal',
})
assert result == Disposition.HUMAN, f'Expected HUMAN for high risk, got {result}'
print(f'High risk -> {result.value}')

# Test evaluation: critical priority -> HUMAN
result = engine.evaluate({
    'risk_score': 0.1,
    'source_system': 'unknown-system',
    'priority': 'critical',
})
assert result == Disposition.HUMAN, f'Expected HUMAN for critical priority, got {result}'
print(f'Critical priority -> {result.value}')

# Test evaluation: flagged content -> BLOCK
result = engine.evaluate({
    'risk_score': 0.1,
    'source_system': 'kais-movie-agent',
    'priority': 'normal',
    'metadata': {'flagged': True},
})
assert result == Disposition.BLOCK, f'Expected BLOCK for flagged, got {result}'
print(f'Flagged -> {result.value}')

# Test default to HUMAN when no rules match
result = engine.evaluate({
    'risk_score': 0.5,
    'source_system': 'unknown-system',
    'priority': 'normal',
})
assert result == Disposition.HUMAN, f'Expected HUMAN default, got {result}'
print(f'No match -> {result.value} (default)')

# Test validation rejects invalid YAML
try:
    engine.validate_policy('not: valid: yaml: [}')
    assert False, 'Should reject invalid YAML'
except PolicyValidationError as e:
    print(f'Invalid YAML rejected: {str(e)[:50]}...')

# Test validation rejects missing disposition
try:
    engine.validate_policy('name: test\nversion: \"1.0\"\nrules:\n  - name: bad\n    priority: 1\n    conditions:\n      operator: AND\n      checks:\n        - field: x\n          operator: equals\n          value: 1\n')
    assert False, 'Should reject missing disposition'
except PolicyValidationError:
    print('Missing disposition correctly rejected')

print('Policy engine tests passed')
"</automated>
  </verify>
  <done>
    - PolicyEngine loads YAML files and validates against JSON Schema
    - AND/OR condition evaluation works with all operators (equals, less_than, greater_than, etc.)
    - Dotted field access works (metadata.flagged resolves to nested dict)
    - Risk-score threshold routing works: <0.3 -> AUTO, >0.7 -> HUMAN
    - Default to HUMAN when no rules match
    - Invalid YAML and invalid schema are rejected with clear error messages
    - default.yaml exists with at least 3 rules covering AUTO, HUMAN, and BLOCK dispositions
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement Policy CRUD API with version tracking</name>
  <files>app/api/v1/policies.py</files>
  <read_first>
    - .planning/phases/01-core-engine/01-CONTEXT.md (locked decisions: Policy CRUD via API with version tracking)
    - .planning/phases/01-core-engine/01-RESEARCH.md (POLC-05, POLC-06 requirements)
    - app/core/policy.py (PolicyEngine class from Task 1)
    - app/models/schema.py (PolicyVersion model)
    - app/core/audit.py (append_audit for policy change logging)
  </read_first>
  <action>
1. Create `app/api/v1/policies.py`:

   ```python
   router = APIRouter(prefix="/api/v1/policies", tags=["policies"])
   ```

   **Endpoints:**

   - `GET /` -- List all policies:
     - Query database for all PolicyVersion records where `is_active == True`
     - Return `ApiResponse[list[PolicyResponse]]` with data list
     - Requires JWT auth (use `Depends(require_jwt)`)

   - `GET /{name}` -- Get specific policy:
     - Query by name where `is_active == True`
     - Return `ApiResponse[PolicyResponse]` with name, version, content, is_active, timestamps
     - If not found, return 404
     - Requires JWT auth

   - `POST /` -- Create new policy:
     - Accept `PolicyCreateRequest` body (name, content)
     - Validate content via `policy_engine.validate_policy(content)`
     - If validation fails, return 422 with validation error message
     - Check if policy with this name already exists (active), return 409 if so
     - Create PolicyVersion record with name, version="1.0", content, is_active=True
     - Load into in-memory engine: `policy_engine.load_policy(name, content)`
     - Append audit: `await append_audit(session, review_id=0, action="policy_create", actor=f"client:{client}", payload={"policy_name": name})`
     - Return 201 with ApiResponse[PolicyResponse]
     - Requires JWT auth

   - `PUT /{name}` -- Update existing policy:
     - Accept `PolicyUpdateRequest` body (content)
     - Validate content via `policy_engine.validate_policy(content)`
     - Find current active PolicyVersion by name
     - If not found, return 404
     - Increment version: parse current version "X.Y" -> "X.(Y+1)"
     - Deactivate old record (set is_active=False)
     - Create new PolicyVersion with incremented version
     - Reload into in-memory engine: `policy_engine.load_policy(name, content)`
     - Append audit: `await append_audit(session, review_id=0, action="policy_update", actor=f"client:{client}", payload={"policy_name": name, "old_version": old.version, "new_version": new_version})`
     - Return 200 with ApiResponse[PolicyResponse]
     - Requires JWT auth

   - `DELETE /{name}` -- Delete (deactivate) policy:
     - Find active PolicyVersion by name
     - If not found, return 404
     - Set is_active=False
     - Remove from in-memory engine: `policy_engine.remove_policy(name)`
     - Append audit: `await append_audit(session, review_id=0, action="policy_delete", actor=f"client:{client}", payload={"policy_name": name})`
     - Return 200 with `ApiResponse[dict]` data={"deleted": name}
     - Requires JWT auth

   **Dependencies used in endpoints:**
   - `db: AsyncSession = Depends(get_db)`
   - `client: str = Depends(get_current_client)`
   - `engine: PolicyEngine = Depends(get_policy_engine_dependency)` -- wraps `get_policy_engine()` as a FastAPI dependency

   **Response format:** All responses use the `ApiResponse[T]` envelope from schemas.py. Example:
   ```python
   return {"data": policy_response_dict, "meta": {"request_id": "..."}}
   ```
  </action>
  <verify>
    <automated>cd /home/kai/workspace/kais-review-platform && python -c "
from app.api.v1.policies import router
# Verify router exists with correct prefix and routes
assert router.prefix == '/api/v1/policies', f'Wrong prefix: {router.prefix}'
route_methods = {(r.methods, r.path) for r in router.routes if hasattr(r, 'methods')}
paths = [p for _, p in route_methods]
print(f'Policy API routes: {route_methods}')
assert any('/' in p for _, p in route_methods), 'Must have root route'
assert any('{name}' in p for _, p in route_methods), 'Must have name parameter route'
print('Policy CRUD API structure verified')
"</automated>
  </verify>
  <done>
    - GET /api/v1/policies lists active policies
    - GET /api/v1/policies/{name} returns specific policy with content
    - POST /api/v1/policies creates new policy after JSON Schema validation
    - PUT /api/v1/policies/{name} updates policy with version increment
    - DELETE /api/v1/policies/{name} deactivates policy
    - All policy mutations append audit entries
    - All endpoints require JWT authentication
    - Invalid policy YAML returns 422 with clear error message
  </done>
</task>

</tasks>

<verification>
1. PolicyEngine loads and evaluates default.yaml correctly
2. Low risk (0.1) from movie-agent routes to AUTO
3. High risk (0.8) routes to HUMAN
4. Flagged content routes to BLOCK
5. No-match defaults to HUMAN
6. JSON Schema validation rejects malformed policies
7. Policy CRUD API has all 5 endpoints (list, get, create, update, delete)
8. Version increments on update (1.0 -> 1.1)
9. Policy changes logged to audit trail
</verification>

<success_criteria>
- YAML policy engine evaluates AND/OR conditions with risk_score thresholds
- 4 routing dispositions: AUTO, HUMAN, AI_AUDIT, BLOCK
- JSON Schema validation catches invalid policies at load time
- Policy CRUD API with version tracking and audit logging
- Default policy file with 3+ rules covering major routing scenarios
- Default to HUMAN when no rules match
</success_criteria>

<output>
After completion, create `.planning/phases/01-core-engine/03-SUMMARY.md`
</output>
