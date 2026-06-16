# Owner Review Package Index

## 1. Package Overview

本 package 的目的仅限于：

- 审 `execution draft`
- 审 `governance evidence`
- 审 `authority model`
- 不批准 `import switch`
- 不批准 `shim removal`

本 package 是 owner review 的单页索引，不是执行入口，不是变更批准单。

## 2. Included Sections

1. Day 2 authoritative rule evidence  
2. Day 3 runtime evidence  
3. Governance evidence consolidation  
4. Import switch execution draft  
5. Owner review question set  
6. Execution authority model  
7. Stop verification layer  

## 3. Current Governance State

```yaml
current_governance_state:
  eligible_for_owner_review:
    - hashing / event_id
    - time / timestamp
    - env / fail-fast
    - async / sleep
    - backoff / retry
    - errors / transport

  blocked:
    - providers.shadow_common shim

  approved_for_import_switch: []

  shim_state:
    status: blocked
    role: compatibility_shim
    removable: false
```

## 4. Explicit Non-Goals

```yaml
explicit_non_goals:
  - not_import_switch_approval
  - not_shim_deletion_approval
  - not_execution_start_approval
```

## 5. Owner Review Required Decisions

```yaml
owner_review_required_decisions:
  - whether to accept the recommended batch order
  - whether to accept per-batch entry criteria
  - whether to accept per-batch stop criteria
  - whether to accept per-batch rollback boundaries
  - whether batch_1 and batch_2 order should remain as drafted
  - whether batch_5 deterministic health/time check is sufficient
  - whether batch_7 must treat unexpected_* as immediate stop
  - whether exception identity drift protection is sufficient
  - whether execution authority assignments are accepted
  - whether stop verification and audit requirements are accepted
```

## 6. Exit Criteria From Owner Review

```yaml
exit_criteria_from_owner_review:
  - owner review must pass before any batch execution can begin
  - even after owner review passes, each batch still requires explicit batch-level approval
  - approved_for_import_switch remains a separate decision and is not granted by owner review alone
  - providers.shadow_common shim remains in place unless separately reviewed and approved
```

## 7. Execution Lock (Hard Gate)

```yaml
execution_lock:

  default_state:
    execution_allowed: false

  unlock_condition:
    - owner_review_passed == true
    - AND explicit_batch_approval_received == true

  constraints:
    - owner_review_passed alone must NOT enable execution
    - absence of explicit batch approval must block execution
    - execution_allowed must be evaluated before every batch

  enforcement:
    - executor must refuse to run any batch if execution_allowed == false
    - any attempt to run without unlock condition satisfied = execution violation

  violation_effect:
    - trigger global freeze
    - mark execution invalid
    - require re-entry into owner review
```

## 8. Batch Approval Interface

```yaml
batch_approval_interface:

  required_fields:
    - batch_id
    - approved_by
    - timestamp_utc
    - approval_scope

  constraints:
    - approval must be explicitly provided before batch execution
    - approval must be tied to a single batch_id
    - approval cannot be reused across batches

approval_validity_rule:

  requirements:
    - approval must be recorded as an auditable artifact
    - approval must include timestamp_utc in ISO 8601 UTC format
    - approval must be attributable to a specific approver identity

  invalid_conditions:
    - missing approval record
    - approval not tied to batch_id
    - approval not attributable to an approver
    - approval reused for multiple batches

  violation_effect:
    - execution must not start
    - trigger execution violation if batch is run
    - trigger global freeze
```
