---
name: Service-account migration practice
about: One bounded identity cutover with evidence and rollback
labels: ''
---
## Scope
Identity / user IDs (no credentials):
Affected projects, groups and consumers:
Simulated owner:
Ticket/change ID:

## Before the change
Baseline pipeline ID / SHA:
Direct and inherited access:
Required token scopes / expiry:
Schedules, runners, integrations and external consumers:
Maintenance window / in-flight pipelines:

## Change and validation
Replacement identity and PAT ID (not value):
Variable metadata preserved:
Functional proof / pipeline ID:
External automation proof:
Schedule ownership proof:
Rollback decision:

## Decommission and closure
Legacy PAT rejected (HTTP status):
Legacy memberships removed:
Legacy user blocked:
Post-retirement pipeline:
Observation evidence and simulated owner sign-off:

Never attach .lab/secrets.json, tokens, passwords, config.toml, or raw environment dumps.
