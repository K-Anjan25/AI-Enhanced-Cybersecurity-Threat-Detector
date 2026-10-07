# AEGIS API reference

> Generated from the application's Pydantic schemas by
> `scripts/generate_api_reference.py`; do not edit by hand. CI renders this
> document again and fails when the two differ (T-320, D-054).

**AEGIS Backend** — API version `0.1.0`. Every request and response named below is a
Pydantic schema in `backend/app/schemas/`, and every path is one the application
actually serves.

## Authentication

One credential per request (R-53, FR-44): a bearer token as
`Authorization: Bearer <token>`, or an issued API key as `X-API-Key: <key>` or as a
bearer token. The roles column is the route matrix `test_rbac.py` asserts is
complete, so a route cannot be added without one.

Every operation answers `422` with `HTTPValidationError` when its query parameters
or body do not match the schema below.

## Routes

| Method | Path | Summary | Roles | Success | Request body |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/alerts` | Query alerts within a time window | admin, analyst, responder, viewer | `200` `AlertPage` | — |
| `POST` | `/api/v1/alerts/export` | Export an alert batch as CSV or PDF (FR-23) | admin, responder | `200` `application/pdf`, `text/csv` | `AlertExportRequest` |
| `GET` | `/api/v1/alerts/notifications` | Alerts published after a stream cursor (FR-20 fallback) | admin, analyst, responder, viewer | `200` `AlertNotificationsOut` | — |
| `GET` | `/api/v1/alerts/stream` | Server-Sent Events alert stream (FR-20 fallback) | admin, analyst, responder, viewer | `200` `text/event-stream` | — |
| `GET` | `/api/v1/alerts/{alert_id}` | Read one alert with its explanation, evidence, verdict and context (FR-51) | admin, analyst, responder, viewer | `200` `AlertDetailOut` | — |
| `POST` | `/api/v1/alerts/{alert_id}/verdict` | Record an analyst verdict on an alert (FR-16) | admin, analyst, responder | `200` `VerdictOutcomeOut` | `VerdictRequest` |
| `GET` | `/api/v1/alerts/{alert_id}/verdicts` | Read an alert's verdict history, oldest first (FR-16, FR-18) | admin, analyst, responder, viewer | `200` `VerdictHistoryOut` | — |
| `GET` | `/api/v1/audit` | Read the audit trail, newest first (FR-42) | admin, analyst, responder, viewer | `200` `AuditPageOut` | — |
| `POST` | `/api/v1/auth/login` | Sign in with an account password | unauthenticated | `200` `TokenPairOut` | `CredentialsIn` |
| `POST` | `/api/v1/auth/logout` | Revoke the refresh-token family | unauthenticated | `204` | `RefreshIn` |
| `POST` | `/api/v1/auth/refresh` | Rotate a single-use refresh token | unauthenticated | `200` `TokenPairOut` | `RefreshIn` |
| `POST` | `/api/v1/auth/setup` | Create the first local development administrator | unauthenticated | `201` `TokenPairOut` | `CredentialsIn` |
| `GET` | `/api/v1/auth/status` | Whether first-admin setup is available | unauthenticated | `200` `AuthStatusOut` | — |
| `GET` | `/api/v1/flows` | Count one window of traffic: volume, addresses and relationships (FR-52) | admin, analyst, responder, viewer | `200` `FlowAggregateOut` | — |
| `POST` | `/api/v1/hunt/export` | Export the alerts matching a hunt as CSV (FR-23) | admin, responder | `200` `text/csv` | `HuntExportRequest` |
| `POST` | `/api/v1/ingest/flows` | Ingest flow records (flow@1) | admin, analyst, responder | `200` `IngestResponse` | `FlowRecordIn` |
| `POST` | `/api/v1/ingest/logs` | Ingest log lines (log@1) | admin, analyst, responder | `200` `IngestResponse` | `LogRecordIn` |
| `GET` | `/api/v1/keys` | List API keys (FR-44) | admin | `200` `ApiKeyListOut` | — |
| `POST` | `/api/v1/keys` | Issue an API key (FR-44) | admin | `201` `ApiKeyIssuedOut` | `ApiKeyCreate` |
| `GET` | `/api/v1/keys/scopes` | List the scopes a key may hold (FR-44) | admin | `200` `ScopeListOut` | — |
| `DELETE` | `/api/v1/keys/{key_id}` | Revoke an API key (FR-44) | admin | `200` `ApiKeyOut` | — |
| `GET` | `/api/v1/logs` | Clustered log read (log@1) | admin, analyst, responder, viewer | `200` `LogTailOut` | — |
| `GET` | `/api/v1/logs/lines` | Raw log lines behind a cluster (log@1) | admin, analyst, responder, viewer | `200` `LogLinesOut` | — |
| `GET` | `/api/v1/models` | List registered model versions (FR-30) | admin, analyst, responder, viewer | `200` `ModelListOut` | — |
| `POST` | `/api/v1/models/{kind}/rollback` | Reverse the most recent promotion of a kind (FR-33) | admin | `200` `ModelTransitionOut` | `RollbackRequest` |
| `GET` | `/api/v1/models/{model_id}/metrics` | Held-out metrics and recorded evaluation artifacts for one version (FR-31, T-420) | admin, analyst, responder, viewer | `200` `ModelMetricsOut` | — |
| `POST` | `/api/v1/models/{model_id}/promote` | Make a version active and retire the incumbent (FR-33) | admin | `200` `ModelTransitionOut` | `PromotionRequest` |
| `GET` | `/api/v1/overview` | One window's counts, severity series and named entities (FR-50) | admin, analyst, responder, viewer | `200` `OverviewOut` | — |
| `POST` | `/api/v1/privacy/erasure` | Erase one data subject across every store (NFR-05, R-37) | admin | `200` `ErasureReportOut` | `ErasureRequest` |
| `GET` | `/api/v1/privacy/erasures` | The erasure ledger, newest first (NFR-05) | admin | `200` `ErasureLedgerPageOut` | — |
| `GET` | `/api/v1/retention` | Retention policy and the plan a run would execute (NFR-05) | admin | `200` `RetentionPlanOut` | — |
| `POST` | `/api/v1/retention/run` | Apply the retention plan (NFR-05) | admin | `200` `RetentionRunOut` | — |
| `GET` | `/api/v1/thresholds` | Thresholds in force, and the FR-13 defaults behind them (R-69) | admin, analyst, responder, viewer | `200` `ThresholdListOut` | — |
| `GET` | `/api/v1/thresholds/preview` | What a proposed threshold would have produced over the last 7 days (design.md §4.8) | admin, analyst, responder, viewer | `200` `ThresholdImpactOut` | — |
| `POST` | `/api/v1/thresholds/recalibrate` | Recalibrate a band from analyst verdicts, under T-207's guardrail (FR-18) | admin | `200` `RecalibrationOut` | `RecalibrationRequest` |
| `PUT` | `/api/v1/thresholds/{family}/{band}` | Set one threshold by hand, or refuse a band set it would invert (T-410) | admin | `200` `ThresholdSetOut` | `ThresholdSetRequest` |
| `GET` | `/api/v1/users` | The user directory and how many admins are active (T-410, R-53) | admin | `200` `UserListOut` | — |
| `GET` | `/api/v1/users/roles` | R-53's roles and what each may do | admin | `200` `RoleListOut` | — |
| `POST` | `/api/v1/users/{user_id}/role` | Set one user's role, refusing to empty the admin role (T-410, R-53) | admin | `200` `RoleChangeOut` | `RoleChangeRequest` |
| `GET` | `/api/v1/webhooks` | List registered webhooks, without secrets | admin, responder | `200` `WebhookListOut` | — |
| `POST` | `/api/v1/webhooks` | Register an outbound webhook (FR-21) | admin, responder | `201` `WebhookCreatedOut` | `WebhookCreate` |
| `GET` | `/api/v1/webhooks/deliveries` | Recent delivery attempts, newest first (T-422) | admin, responder | `200` `DeliveryListOut` | — |
| `DELETE` | `/api/v1/webhooks/{webhook_id}` | Delete a webhook | admin, responder | `204` | — |
| `POST` | `/api/v1/webhooks/{webhook_id}/test` | Attempt one delivery to a target (T-422) | admin, responder | `200` `DeliveryOut` | — |
| `GET` | `/healthz` | Liveness probe | unauthenticated | `200` `HealthResponse` | — |
| `GET` | `/metrics` | Prometheus metrics | unauthenticated | `200` `text/plain` | — |
| `GET` | `/readyz` | Readiness probe | unauthenticated | `200` `ReadinessResponse` | — |

## Schemas

### `AlertDetailOut`

Everything design.md §4.3's four zones render, in one response.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alert` | `AlertRow` | yes | — |
| `models` | `AlertModelsOut` | no | — |
| `explanation` | `ExplanationOut` | yes | — |
| `evidence` | `EvidenceOut` | yes | — |
| `verdict` | `AlertVerdictOut` | no | — |
| `related` | `RelatedAlertsOut` | yes | — |
| `family_history` | `FamilyHistoryOut` | yes | — |

### `AlertExportRequest`

A queue filter, as the body of an export.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | `string (date-time)` | yes | — |
| `end` | `string (date-time)` | yes | — |
| `severity` | list of `string` or `null` | no | — |
| `status` | list of `string` or `null` | no | — |
| `family` | list of `string` or `null` | no | — |
| `entity_id` | `integer` or `null` | no | — |
| `min_score` | `number` or `null` | no | — |
| `order` | `desc` or `asc` | no | — |
| `limit` | `integer` | no | — |
| `cursor` | `null` | no | Not accepted: an export mirrors the query's first page. |
| `format` | `ExportFormat` | no | csv (rows only, for a spreadsheet) or pdf (a report, with the filter on the page). |

### `AlertModelsOut`

The model versions that scored this alert, when the row recorded them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `flow` | `string` or `null` | no | Pinned flow-model version, e.g. flownet@1.4.2. |
| `log` | `string` or `null` | no | Pinned log-model version. |

### `AlertNotificationOut`

One alert plus its stream position.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `sequence` | `integer` | yes | — |
| `alert` | `AlertRow` | yes | — |

### `AlertNotificationsOut`

The polling fallback, and what a client gets when it must resync.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `AlertNotificationOut` | yes | — |
| `oldest_available` | `integer` or `null` | yes | — |
| `latest` | `integer` or `null` | yes | — |
| `resync_required` | `boolean` | yes | — |
| `epoch` | `string` | yes | — |

### `AlertPage`

A page of alerts plus the cursor for the next one.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `AlertRow` | yes | — |
| `next_cursor` | `string` or `null` | yes | — |
| `limit` | `integer` | yes | — |
| `order` | `desc` or `asc` | yes | — |

### `AlertRow`

One alert as returned by the API.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `entity_id` | `integer` | yes | — |
| `family` | `string` | yes | — |
| `severity` | `string` | yes | — |
| `score` | `number` | yes | — |
| `status` | `string` | yes | — |
| `first_seen` | `string (date-time)` | yes | — |
| `last_seen` | `string (date-time)` | yes | — |
| `occurrence_count` | `integer` | yes | — |
| `trace_id` | `string` or `null` | no | — |

### `AlertVerdictOut`

The alert's verdict history, oldest first, and the current one.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `current` | `VerdictRecordOut` or `null` | no | — |
| `history` | `VerdictRecordOut` | no | — |

### `ApiKeyCreate`

A key to issue.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `scopes` | list of `string` | yes | — |

### `ApiKeyIssuedOut`

A newly issued key, with its secret shown exactly once.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `name` | `string` | yes | — |
| `prefix` | `string` | yes | — |
| `owner` | `string` | yes | — |
| `scopes` | list of `string` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `last_used_at` | `string (date-time)` or `null` | yes | — |
| `revoked_at` | `string (date-time)` or `null` | yes | — |
| `secret` | `string` | yes | The API key. Shown once; store it now. |

### `ApiKeyListOut`

Every key, revoked ones included, so the list is the record of what existed.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ApiKeyOut` | yes | — |

### `ApiKeyOut`

An issued key, **without** its secret.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `name` | `string` | yes | — |
| `prefix` | `string` | yes | — |
| `owner` | `string` | yes | — |
| `scopes` | list of `string` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `last_used_at` | `string (date-time)` or `null` | yes | — |
| `revoked_at` | `string (date-time)` or `null` | yes | — |

### `AuditAction`

The actions the trail records, one per mutating route.

Types: `ingest.flows` or `ingest.logs` or `alert.verdict` or `webhook.create` or `webhook.delete` or `key.create` or `key.revoke` or `retention.apply` or `privacy.erasure` or `model.promote` or `model.rollback` or `threshold.recalibrate` or `threshold.set` or `user.role` or `hunt.export` or `alert.export` or `webhook.test` or `auth.setup` or `auth.login` or `auth.refresh` or `auth.logout`.

### `AuditEntryOut`

One recorded action.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | Trail sequence, 1-based and monotonic. |
| `actor` | `string` | yes | The principal the access token named. |
| `action` | `string` | yes | — |
| `target_type` | `string` | yes | — |
| `target_id` | `string` | yes | — |
| `detail` | `object` | yes | — |
| `ip` | `string` or `null` | yes | — |
| `at` | `string (date-time)` | yes | — |

### `AuditPageOut`

A page of the trail, newest first.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `AuditEntryOut` | yes | — |
| `next_before` | `integer` or `null` | yes | — |

### `AuthStatusOut`

Whether the explicitly enabled local first-admin setup is still available.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `setup_available` | `boolean` | yes | True only when development-only setup is enabled and no account exists. The first account is an administrator and is held in memory. |
| `setup_enabled` | `boolean` | yes | Whether AEGIS_DEV_AUTH_SETUP_ENABLED is enabled for this process. |
| `account_exists` | `boolean` | yes | Whether an administrator has been provisioned in this process. |

### `ConfusionMatrixOut`

Recorded TP/FP/TN/FN counts, threshold and exact artifact provenance.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `threshold` | `number` | yes | — |
| `tp` | `integer` | yes | — |
| `fp` | `integer` | yes | — |
| `tn` | `integer` | yes | — |
| `fn` | `integer` | yes | — |
| `artifact` | `string` | yes | Recorded evaluation run containing this matrix. |
| `field` | `string` | yes | Field path inside the recorded evaluation run. |

### `CredentialsIn`

Email and password for local account setup or sign-in.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `email` | `string` | yes | — |
| `password` | `string (password)` | yes | — |

### `DeliveryListOut`

Recent delivery attempts, newest first, with what qualifies them (R-70).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `DeliveryOut` | yes | — |
| `held` | `integer` | yes | How many records the process still holds. |
| `recorded` | `integer` | yes | How many it has made, including dropped ones. |
| `dispatch_configured` | `boolean` | yes | Whether this deployment has a sender, so an empty list can be read. |
| `caveats` | list of `string` | yes | — |

### `DeliveryOut`

One delivery attempt, as the connectors screen reads it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `delivery_id` | `string` | yes | — |
| `target_id` | `string` | yes | — |
| `at` | `string (date-time)` | yes | When the delivery finished, on the API's clock. |
| `delivered` | `boolean` | yes | — |
| `attempt_count` | `integer` | yes | Requests made, retries included. |
| `waited_seconds` | `number` | yes | Time spent in backoffs between them. |
| `outcome` | `string` | yes | The last attempt: delivered, retry, rejected, blocked or transport_error. |
| `status` | `integer` or `null` | no | HTTP status of the last attempt. |
| `reason` | `string` | yes | A short code, never a message from the receiver. |

### `Direction`

Traffic direction relative to the monitored boundary.

Types: `inbound` or `outbound` or `internal`.

### `DroppedPartitionOut`

One monthly partition, with the span it covers.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `table` | `string` | yes | — |
| `name` | `string` | yes | — |
| `year` | `integer` | yes | — |
| `month` | `integer` | yes | — |
| `covers_start` | `string (date)` | yes | — |
| `covers_end` | `string (date)` | yes | — |
| `statement` | `string` | yes | — |

### `ErasureLedgerEntryOut`

One recorded erasure.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `sequence` | `integer` | yes | — |
| `tombstone` | `string` | yes | — |
| `kind` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `requested_by` | `string` | yes | — |
| `targets` | `ErasureTargetOut` | yes | — |

### `ErasureLedgerPageOut`

A page of the erasure ledger, newest first, with a cursor.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ErasureLedgerEntryOut` | yes | — |
| `next_before` | `integer` or `null` | yes | — |

### `ErasureReportOut`

The result of an erasure -- with the tombstone, never the identifier.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | `string` | yes | — |
| `tombstone` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `targets` | `ErasureTargetOut` | yes | — |
| `preserved` | `PreservedLedgerOut` | yes | — |
| `already_erased` | `boolean` | yes | — |
| `ledger_sequence` | `integer` or `null` | yes | — |
| `affected` | `integer` | yes | — |
| `reason` | `string` | no | — |

### `ErasureRequest`

An erasure request. The only model here that carries the subject's value.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | `string` | yes | 'user' (an account) or 'entity' (an observed host, service or address). |
| `value` | `string` | yes | The identifier to erase. |
| `reason` | `string` | no | Why the request was made. Recorded; never an identifier. |

### `ErasureTargetOut`

What one store did.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `affected` | `integer` | yes | — |

### `EvaluationDetailsOut`

The confusion matrix and score distribution from one evaluation artifact.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `confusion` | `ConfusionMatrixOut` | yes | — |
| `score_histogram` | `ScoreHistogramOut` | yes | — |

### `EvidenceOccurrenceOut`

One window in the evidence trail behind an alert.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | The window's stable identity, as T-307 emitted it. |
| `modality` | `string` | yes | Which model scored the window: flow or log. |
| `score` | `number` | yes | That model's score for the window, in [0, 1]. |
| `at` | `string (date-time)` | yes | When the window closed, timezone-aware UTC. |
| `model` | `string` or `null` | no | The version that scored it. |
| `expires_at` | `string (date-time)` | yes | When FR-05's raw-record window takes this evidence away. |
| `expired` | `boolean` | yes | True once the raw records behind it are gone. |

### `EvidenceOut`

design.md §4.3's zone 3: the raw records behind the alert.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `window_id` | `string` or `null` | no | The window the case opened on, when recorded. |
| `trace_id` | `string` or `null` | no | Trace of the ingest request that opened the case (T-317). |
| `grouped` | `boolean` | no | True when the correlator fused several detections into one case. |
| `occurrences` | `EvidenceOccurrenceOut` | no | — |
| `retention_days` | `integer` | yes | FR-05's raw-record window the expiry dates above are computed from. |
| `expired` | `boolean` | no | True when every occurrence is past retention. |
| `unreadable` | `integer` | no | Trail entries that could not be decoded, reported rather than dropped. |
| `note` | `string` or `null` | no | Why the trail is incomplete, in the operator's words. |

### `ExplanationOut`

R-70's explanation contract, as the alert row stored it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `reasons` | list of `string` | no | Rendered reasons, most contributory first. |
| `unavailable` | `boolean` | no | True when no explanation could be produced (R-70). |
| `detail` | `string` or `null` | no | Why it is unavailable. Never a stack trace (R-58). |
| `unavailable_modalities` | list of `string` | no | Modalities that contributed without reasons. |
| `partial_evidence` | `boolean` | no | True while only one modality has contributed. |
| `families` | list of `string` | no | Every family the case's occurrences named. |

### `ExportFormat`

The two shapes an alert batch leaves in (FR-23).

Types: `csv` or `pdf`.

### `FamilyHistoryOut`

The trust hint: what analysts decided about this entity and family before.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `family` | `string` | yes | — |
| `window_days` | `integer` | yes | How far back the counts reach. |
| `prior_alerts` | `integer` | no | Alerts on this entity and family before this one. |
| `labelled` | `integer` | no | How many of them carry a verdict at all. |
| `false_positive` | `integer` | no | — |
| `benign` | `integer` | no | — |
| `true_positive` | `integer` | no | — |

### `FlowAggregateOut`

One window's traffic: the series, the addresses, the relationships and the caveats.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `window` | `FlowWindowOut` | yes | The window these numbers describe. |
| `bucket_minutes` | `integer` | yes | Resolution of the series. |
| `source` | `store` or `rollup` | yes | Which read model answered: the flow store or the in-process rollup. |
| `filters` | `FlowFiltersOut` | yes | The narrowing applied to the read. |
| `series` | `FlowBucketOut` | yes | Volume per bucket, oldest first. |
| `entities` | `FlowEntityOut` | yes | Addresses, busiest first, capped. |
| `edges` | `FlowEdgeOut` | yes | Relationships, heaviest first, capped. |
| `totals` | `FlowTotalsOut` | yes | The window's counts and the caps' effect. |
| `caveats` | list of `string` | yes | What a reader must know about these numbers, in the source's words. |

### `FlowBucketOut`

One point of the volume series, with the alert overlay it is drawn against.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | `string (date-time)` | yes | Inclusive lower bound of the bucket. |
| `flows` | `integer` | yes | Flow records in the bucket. |
| `bytes` | `integer` | yes | Bytes those records carried. |
| `packets` | `integer` | yes | Packets those records carried. |
| `alerts` | `integer` | yes | Alerts raised in the bucket, joined on its instant. |
| `score` | `number` or `null` | no | Mean composite score of those alerts, or null when the bucket held none. Null rather than zero: an empty bucket is not a benign one. |

### `FlowEdgeOut`

One directional relationship: two addresses that exchanged traffic.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source` | `string` | yes | Source address. |
| `target` | `string` | yes | Destination address. |
| `flows` | `integer` | yes | Records between them, in that direction. |
| `bytes` | `integer` | yes | Bytes those records carried. |

### `FlowEntityOut`

One address's share of the window, and the alerts that attach to it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ip` | `string` | yes | The address, as it appeared on the wire. |
| `flows` | `integer` | yes | Records in which it was an end. |
| `bytes` | `integer` | yes | Bytes those records carried. |
| `packets` | `integer` | yes | Packets those records carried. |
| `inbound` | `integer` | yes | Records in which it was the destination. |
| `outbound` | `integer` | yes | Records in which it was the source. |
| `first_seen` | `string (date-time)` or `null` | no | Oldest record, in window. |
| `last_seen` | `string (date-time)` or `null` | no | Newest record, in window. |
| `alerts` | `integer` | no | Alerts in the window whose entity value is this address. |
| `open_alerts` | `integer` | no | How many of them are still open. |
| `worst_severity` | `string` or `null` | no | Most serious band among them, or null for none. |
| `max_score` | `number` or `null` | no | Highest score among them, or null for none. |

### `FlowFiltersOut`

The narrowing the read applied, so a filter is never invisible on the wire.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `protocol` | `string` or `null` | no | Protocol the read was narrowed to, or null for all. |
| `direction` | `string` or `null` | no | Direction the read was narrowed to, or null for all. |

### `FlowRecordIn`

One flow record on the wire — the ``flow@1`` contract.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | — |
| `timestamp` | `string (date-time)` | yes | — |
| `src_ip` | `string (ipv4)` | yes | — |
| `dst_ip` | `string (ipv4)` | yes | — |
| `src_port` | `integer` | yes | — |
| `dst_port` | `integer` | yes | — |
| `protocol` | `Protocol` | yes | — |
| `direction` | `Direction` | yes | — |
| `service` | `string` or `null` | no | — |
| `state` | `string` or `null` | no | — |
| `packets` | `integer` | yes | — |
| `src_packets` | `integer` | yes | — |
| `dst_packets` | `integer` | yes | — |
| `src_bytes` | `integer` | yes | — |
| `dst_bytes` | `integer` | yes | — |
| `duration` | `number` | yes | — |
| `syn` | `integer` | no | — |
| `ack` | `integer` | no | — |
| `rst` | `integer` | no | — |
| `fin` | `integer` | no | — |
| `psh` | `integer` | no | — |
| `urg` | `integer` | no | — |
| `label` | `string` or `null` | no | — |

### `FlowTotalsOut`

The window's counts, and what each cap did to the lists.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `flows` | `integer` | yes | Flow records in the window -- every one of them. |
| `bytes` | `integer` | yes | Bytes they carried. |
| `packets` | `integer` | yes | Packets they carried. |
| `nodes` | `integer` | yes | Distinct addresses in the window. |
| `edges` | `integer` | yes | Distinct directional pairs in the window. |
| `nodes_capped` | `boolean` | yes | True when more addresses were seen than the entity list holds. |
| `edges_capped` | `boolean` | yes | True when more relationships were seen than the edge list holds. |
| `untracked_address_flows` | `integer` | no | Records the in-process rollup could not attribute to an address because it was full. They are in ``flows`` either way; always 0 for a store. |
| `untracked_pair_flows` | `integer` | no | Records the in-process rollup could not attribute to a pair because it was full. They are in ``flows`` either way; always 0 for a store. |

### `FlowWindowOut`

The window the read answered about, echoed so a client never guesses it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | `string (date-time)` | yes | Inclusive lower bound of the window (R-34). |
| `end` | `string (date-time)` | yes | Exclusive upper bound of the window (R-34). |
| `hours` | `number` | yes | The window's width in hours, for display. |

### `HTTPValidationError`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `detail` | `ValidationError` | no | — |

### `HealthResponse`

Liveness: the process is running. Never reflects dependency state.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | `string` | yes | Always 'ok' when the process is up. |
| `service` | `string` | yes | Service name, e.g. aegis-backend. |
| `version` | `string` | yes | Build version of the running artifact. |
| `environment` | `string` | yes | Deployment environment. |

### `HuntExportRequest`

A hunt's query, as the body of an export.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | `string (date-time)` | yes | — |
| `end` | `string (date-time)` | yes | — |
| `severity` | list of `string` or `null` | no | — |
| `status` | list of `string` or `null` | no | — |
| `family` | list of `string` or `null` | no | — |
| `entity_id` | `integer` or `null` | no | — |
| `min_score` | `number` or `null` | no | — |
| `order` | `desc` or `asc` | no | — |
| `limit` | `integer` | no | — |
| `cursor` | `null` | no | Not accepted: an export mirrors the query's first page. |

### `IngestResponse`

The outcome of a batch. Nothing accepted or rejected goes unreported.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `received` | `integer` | yes | — |
| `accepted` | `integer` | yes | — |
| `rejected` | `integer` | yes | — |
| `errors` | `RecordError` | no | — |

### `LogClusterOut`

One row of the fold: a template (or a repeated message) with its count.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `key` | `string` | yes | Stable id for this cluster; pass it back to expand the rows. |
| `template_id` | `string` or `null` | no | The collector's template id, or null when the lines carried none. |
| `count` | `integer` | yes | How many lines in the window folded into this row. |
| `first_seen` | `string (date-time)` | yes | Oldest line in the cluster, UTC. |
| `last_seen` | `string (date-time)` | yes | Newest line in the cluster, UTC. |
| `worst_level` | `LogLevel` | yes | Most severe level among the cluster's lines. A level, not a score. |
| `levels` | map of string to `integer` | no | How many lines of each level the cluster holds, keyed by level. |
| `hosts` | list of `string` | no | Hosts that emitted the cluster. |
| `services` | list of `string` | no | Services that emitted the cluster. |
| `sample_message` | `string` | yes | The newest line in the cluster, verbatim. |
| `parameters` | map of string to `string` | no | Parameters of the newest line in the cluster. |

### `LogLevel`

Severity levels ``log@1`` recognises.

Types: `debug` or `info` or `warning` or `error` or `critical`.

### `LogLineOut`

One raw log line, with the cluster key the server computed for it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `timestamp` | `string (date-time)` | yes | When the line was emitted, UTC. |
| `host` | `string` | yes | Host that emitted the line. |
| `service` | `string` | yes | Service or component that emitted it. |
| `level` | `LogLevel` | yes | Level as log@1 defines it. |
| `message` | `string` | yes | The raw line, parameters and all. |
| `template_id` | `string` or `null` | no | Template the collector mined for this line, when it sent one. |
| `parameters` | map of string to `string` | no | Named values the template was filled with, when the collector sent them. |
| `key` | `string` | yes | Cluster this line folds into: a template id or a message digest. |

### `LogLinesOut`

The raw lines of one cluster (or one window), oldest first.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source` | `store` or `tail` | yes | Which read model answered: the persistent store, or the in-process tail. |
| `start` | `string (date-time)` | yes | Window start, inclusive, UTC. |
| `end` | `string (date-time)` | yes | Window end, exclusive, UTC. |
| `key` | `string` or `null` | no | Cluster the read was narrowed to, if any. |
| `lines` | `LogLineOut` | no | — |
| `lines_seen` | `integer` | yes | Matching lines, before the row limit. |
| `lines_truncated` | `boolean` | yes | Whether the newest rows only are shown. |
| `retained_from` | `string (date-time)` or `null` | no | — |
| `retained_to` | `string (date-time)` or `null` | no | — |
| `retained_lines` | `integer` | yes | Lines the source holds, across all windows. |
| `dropped_lines` | `integer` or `null` | no | Lines evicted since the process started; null when the source cannot report evictions, which is not the same as zero. |
| `caveats` | list of `string` | no | — |

### `LogRecordIn`

One log line on the wire — the ``log@1`` contract.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | — |
| `timestamp` | `string (date-time)` | yes | — |
| `host` | `string` | yes | — |
| `service` | `string` | yes | — |
| `level` | `LogLevel` | yes | — |
| `message` | `string` | yes | — |
| `template_id` | `string` or `null` | no | — |
| `parameters` | map of string to `string` | no | — |
| `label` | `string` or `null` | no | — |

### `LogTailOut`

Clusters for one window, plus what the tail could and could not cover.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source` | `store` or `tail` | yes | Which read model answered: the persistent store, or the in-process tail. |
| `start` | `string (date-time)` | yes | Window start, inclusive, UTC. |
| `end` | `string (date-time)` | yes | Window end, exclusive, UTC. |
| `clusters` | `LogClusterOut` | no | — |
| `lines_seen` | `integer` | yes | Matching lines folded, before any row limit. |
| `clusters_seen` | `integer` | yes | Distinct clusters in the window, before any limit. |
| `clusters_truncated` | `boolean` | yes | Whether the row limit cut the list. |
| `retained_from` | `string (date-time)` or `null` | no | Oldest instant the source still holds, or null when empty. |
| `retained_to` | `string (date-time)` or `null` | no | Newest instant the source still holds, or null when empty. |
| `retained_lines` | `integer` | yes | Lines the source holds, across all windows. |
| `dropped_lines` | `integer` or `null` | no | Lines evicted since the process started; null when the source cannot report evictions, which is not the same as zero. |
| `caveats` | list of `string` | no | What a reader must know to read the numbers above (R-70). |

### `MetricPointOut`

A metric value beside the run it came from (R-74).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `value` | `number` | yes | — |
| `artifact` | `string` | yes | Path or id of the recorded run the value was read from. |
| `field` | `string` | yes | Location of the value inside that artifact. |

### `ModelListOut`

The registered versions, in the order the version table renders them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ModelOut` | yes | — |
| `count` | `integer` | yes | — |

### `ModelMetricsOut`

FR-31's metrics for one version, on a named split.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `split` | `string` | yes | The split these numbers were measured on, e.g. 'temporal:2025-Q4'. |
| `evaluated_at` | `string (date-time)` | yes | — |
| `metrics` | map of string to `MetricPointOut` | yes | — |
| `evaluation` | `EvaluationDetailsOut` or `null` | no | — |

### `ModelOut`

One registered model version.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `model_id` | `string` | yes | — |
| `kind` | `string` | yes | — |
| `status` | `string` | yes | — |
| `artifact_uri` | `string` | yes | — |
| `sha256` | `string` | yes | — |
| `manifest_present` | `boolean` | yes | Whether a training_manifest.json ships with it. False means R-63 refuses its promotion. |
| `promoted_at` | `string (date-time)` or `null` | no | — |
| `promoted_by` | `string` or `null` | no | — |
| `justification` | `string` | no | — |

### `ModelTransitionOut`

What a promotion or rollback did.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `model_id` | `string` | yes | — |
| `kind` | `string` | yes | — |
| `status` | `string` | yes | — |
| `retired` | `string` or `null` | yes | — |
| `changed` | `boolean` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `actor` | `string` | yes | — |

### `OverviewBucket`

One point of the severity series.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | `string (date-time)` | yes | — |
| `total` | `integer` | yes | — |
| `by_severity` | map of string to `integer` | yes | — |
| `score` | `number` or `null` | no | Mean score of the bucket's alerts; null for a bucket that held none. |

### `OverviewEntity`

One entity in the window, named.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `entity_id` | `integer` | yes | — |
| `kind` | `string` or `null` | yes | — |
| `value` | `string` or `null` | yes | — |
| `named` | `boolean` | yes | — |
| `alerts` | `integer` | yes | — |
| `occurrences` | `integer` | yes | — |
| `open` | `integer` | yes | — |
| `worst_severity` | `string` | yes | — |
| `max_score` | `number` | yes | — |
| `last_seen` | `string (date-time)` | yes | — |

### `OverviewFamily`

One threat family's share of the window.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `family` | `string` | yes | — |
| `alerts` | `integer` | yes | — |
| `worst_severity` | `string` | yes | — |

### `OverviewOut`

The overview's three panels, from one read of one window.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `window` | `OverviewWindow` | yes | — |
| `bucket_minutes` | `integer` | yes | — |
| `totals` | `OverviewTotals` | yes | — |
| `series` | `OverviewBucket` | yes | — |
| `entities` | `OverviewEntity` | yes | — |
| `entities_capped` | `boolean` | yes | — |
| `families` | `OverviewFamily` | yes | — |
| `families_capped` | `boolean` | yes | — |

### `OverviewTotals`

The KPI tiles: the window's counts, complete rather than capped.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alerts` | `integer` | yes | — |
| `open` | `integer` | yes | — |
| `by_severity` | map of string to `integer` | yes | — |
| `unrecognised_severity` | `integer` | yes | — |
| `verdicts` | map of string to `integer` | yes | — |
| `unrecorded` | `integer` | yes | — |
| `verdicts_measured` | `integer` | yes | — |
| `mean_time_to_verdict_seconds` | `number` or `null` | yes | — |

### `OverviewWindow`

The window the figures describe, echoed so a client can label them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | `string (date-time)` | yes | — |
| `end` | `string (date-time)` | yes | — |
| `hours` | `number` | yes | — |

### `PreservedLedgerOut`

An append-only store the erasure did not rewrite, and why.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `reason` | `string` | yes | — |

### `ProbeCheck`

Result of one registered readiness probe.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `status` | `ok` or `degraded` or `unavailable` | yes | — |
| `detail` | `string` | no | — |

### `PromotionRequest`

A request to make a version active.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `justification` | `string` | yes | — |

### `Protocol`

Transport protocols ``flow@1`` recognises.

Types: `tcp` or `udp` or `icmp`.

### `ReadinessResponse`

Readiness: can this process serve traffic right now?

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | `ready` or `not_ready` | yes | — |
| `service` | `string` | yes | — |
| `version` | `string` | yes | — |
| `checks` | `ProbeCheck` | no | One entry per registered dependency. Empty in the S0 skeleton. |

### `RecalibrationOut`

A run's report: the window it read, and every threshold it considered.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `band` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `since` | `string (date-time)` | yes | — |
| `until` | `string (date-time)` | yes | — |
| `quantile` | `number` | yes | — |
| `minimum_sample` | `integer` | yes | — |
| `considered` | `integer` | yes | — |
| `changed` | `integer` | yes | — |
| `outcomes` | `ThresholdOutcomeOut` | yes | — |

### `RecalibrationRequest`

Which band to recalibrate. Everything else is policy, not a per-run knob.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `band` | `string` | no | FR-13 band whose lower bound to move. `high` is the default because the PRD measures precision and recall at the deployed `high` threshold, so that is the bar a false-positive budget applies to. |

### `RecordError`

Why one record in a batch was rejected (FR-04).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `index` | `integer` | yes | — |
| `stage` | `parse` or `validation` | yes | — |
| `message` | `string` | yes | — |
| `field` | `string` or `null` | no | — |

### `RefreshIn`

A single-use refresh token presented for rotation.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `refresh_token` | `string (password)` | yes | — |

### `RelatedAlertsOut`

Other alerts on the same entity around this one, for §4.3's "Related alerts".

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `window_minutes` | `integer` | yes | Half-width of the window searched, in minutes. |
| `items` | `AlertRow` | no | — |
| `truncated` | `boolean` | no | True when more related alerts exist than were returned. |

### `RetentionPlanOut`

What a retention run would do, now.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `planned_at` | `string (date)` | yes | — |
| `policy` | `RetentionPolicyOut` | yes | — |
| `drop` | `DroppedPartitionOut` | yes | — |
| `kept` | `DroppedPartitionOut` | yes | — |
| `missing` | list of `string` | yes | — |
| `unevictable` | `UnevictableOut` | yes | — |
| `external` | map of string to `string` | yes | — |
| `statements` | list of `string` | yes | — |

### `RetentionPolicyOut`

The windows a deployment retains each class of data.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `raw_records_days` | `integer` | yes | — |
| `alerts_days` | `integer` | yes | — |
| `stats_days` | `integer` | yes | — |

### `RetentionRunOut`

What a retention run did, including how much of it was already done.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `started_at` | `string (date-time)` | yes | — |
| `planned` | list of `string` | yes | — |
| `dropped` | list of `string` | yes | — |
| `already_absent` | list of `string` | yes | — |
| `changed_anything` | `boolean` | yes | — |

### `RoleChangeOut`

What a role change did, including when it did nothing.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `user_id` | `integer` | yes | — |
| `previous` | `string` | yes | — |
| `applied` | `string` | yes | — |
| `changed` | `boolean` | yes | False when the user already held the role: nothing was written or audited. |
| `at` | `string (date-time)` | yes | — |
| `actor` | `string` | yes | — |

### `RoleChangeRequest`

A request to set one user's role.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `role` | `string` | yes | One of R-53's four roles. |

### `RoleListOut`

R-53's four roles and their capabilities, read from the matrix itself.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `RoleNameOut` | yes | — |

### `RoleNameOut`

One role, with what it may do, so the screen can explain the choice.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `role` | `string` | yes | — |
| `capabilities` | list of `string` | yes | — |

### `RollbackRequest`

A request to reverse the most recent promotion of a kind.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `reason` | `string` | yes | — |

### `ScopeListOut`

The scopes a key may be issued with, and what each one grants.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ScopeOut` | yes | — |

### `ScopeOut`

One scope, with the capabilities it grants.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `capabilities` | list of `string` | yes | — |

### `ScoreHistogramBinOut`

One lower-inclusive score interval and the observed class counts.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `lower` | `number` | yes | — |
| `upper` | `number` | yes | — |
| `benign` | `integer` | yes | — |
| `threat` | `integer` | yes | — |

### `ScoreHistogramOut`

The recorded score distribution and its artifact provenance.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `bins` | `ScoreHistogramBinOut` | yes | — |
| `artifact` | `string` | yes | Recorded evaluation run containing this histogram. |
| `field` | `string` | yes | Field path inside the recorded evaluation run. |

### `ThresholdImpactOut`

What a proposed threshold would have produced over the preview window.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `family` | `string` | yes | — |
| `band` | `string` | yes | — |
| `proposed` | `number` | yes | — |
| `current` | `number` | yes | — |
| `current_source` | `string` | yes | — |
| `window_start` | `string (date-time)` | yes | — |
| `window_end` | `string (date-time)` | yes | — |
| `alerts_read` | `integer` | yes | — |
| `would_fire` | `integer` | yes | — |
| `would_stop_firing` | `integer` | yes | — |
| `would_start_firing` | `integer` | yes | — |
| `complete` | `boolean` | yes | False when the page cap stopped the walk: the counts are a floor, not a total. |

### `ThresholdListOut`

The values in force for this deployment, and the defaults behind them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `defaults` | map of string to `number` | yes | FR-13's documented initial band edges, in force wherever no row exists. |
| `items` | `ThresholdOut` | yes | — |

### `ThresholdOut`

One ``thresholds`` row, as the API returns it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `family` | `string` | yes | — |
| `band` | `string` | yes | — |
| `value` | `number` | yes | — |
| `source` | `string` | yes | Stored provenance, as written: `recalculation` for a fitted value, `manual` for one a person set. |
| `source_label` | `string` | no | design.md §4.8's vocabulary: `calibrated` or `manual`. A family with no row at all is `default`, which the listing reports as a documented value rather than as a row. |
| `updated_at` | `string (date-time)` | yes | — |
| `changed_by` | `string` or `null` | no | Who last moved this value, read from the audit trail. Null when the trail holds no record at the row's write instant, which is a fact rather than a reason to guess. |

### `ThresholdOutcomeOut`

What the run decided about one threshold.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `family` | `string` | yes | — |
| `band` | `string` | yes | — |
| `previous` | `number` | yes | — |
| `previous_was_default` | `boolean` | yes | — |
| `requested` | `number` or `null` | yes | — |
| `applied` | `number` | yes | — |
| `changed` | `boolean` | yes | — |
| `clamped` | `boolean` | yes | — |
| `sample_size` | `integer` | yes | — |
| `reason` | `string` | yes | `fitted` or `insufficient_feedback`. |

### `ThresholdSetOut`

What a hand-set threshold did, including when it changed nothing.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `family` | `string` | yes | — |
| `band` | `string` | yes | — |
| `previous` | `number` | yes | — |
| `previous_label` | `string` | yes | — |
| `applied` | `number` | yes | — |
| `source` | `string` | yes | — |
| `changed` | `boolean` | yes | False when the same hand had already set this value: nothing was written. |
| `at` | `string (date-time)` | yes | — |

### `ThresholdSetRequest`

A hand-set threshold (design.md §4.8's manual edit).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `value` | `number` | yes | The new lower bound, strictly inside (0, 1). |

### `TokenPairOut`

The bearer pair returned after setup, login or refresh rotation.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `access_token` | `string` | yes | — |
| `refresh_token` | `string` | yes | — |
| `token_type` | `string` | no | — |
| `expires_in` | `integer` | yes | Access-token lifetime in seconds. |
| `subject` | `string` | yes | — |
| `role` | `string` | yes | — |

### `UnevictableOut`

A table retention will not touch, and the reason in one sentence.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `table` | `string` | yes | — |
| `reason` | `string` | yes | — |

### `UserListOut`

The directory, in the order the screen renders it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `UserOut` | yes | — |
| `count` | `integer` | yes | — |
| `active_admins` | `integer` | yes | How many accounts can currently administer the deployment. The same number the last-admin refusal is decided by. |

### `UserOut`

One user, as the admin screen needs them. Never a credential.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `email` | `string` | yes | — |
| `role` | `string` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `disabled_at` | `string (date-time)` or `null` | no | When the account stopped being usable. A disabled admin is not an admin in force, so it neither holds the floor up nor counts towards it. |

### `ValidationError`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `loc` | list of `string` or `integer` | yes | — |
| `msg` | `string` | yes | — |
| `type` | `string` | yes | — |
| `input` | `any` | no | — |
| `ctx` | `object` | no | — |

### `VerdictHistoryOut`

Every verdict recorded on one alert, oldest first.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alert_id` | `integer` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `current` | `VerdictRecordOut` or `null` | yes | — |
| `items` | `VerdictRecordOut` | yes | — |

### `VerdictOutcomeOut`

The result of recording a verdict.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | `string` | yes | — |
| `record` | `VerdictRecordOut` | yes | — |
| `superseded` | `VerdictRecordOut` or `null` | yes | — |

### `VerdictRecordOut`

One verdict record as returned by the API.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | — |
| `alert_id` | `integer` | yes | — |
| `verdict` | `string` | yes | — |
| `actor` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `note` | `string` or `null` | yes | — |
| `supersedes` | `string` or `null` | yes | — |

### `VerdictRequest`

A verdict to record on one alert.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `verdict` | `string` | yes | true_positive, false_positive or benign. |
| `created_at` | `string (date-time)` | yes | The alert's created_at, which addresses its partition (D-030). |
| `note` | `string` or `null` | no | — |

### `WebhookCreate`

A webhook target to register.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `url` | `string` | yes | https:// destination. |
| `description` | `string` or `null` | no | — |
| `severity_floor` | `string` | no | Lowest severity delivered: info, low, medium, high or critical. |

### `WebhookCreatedOut`

A newly registered target, with its secret shown exactly once.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | — |
| `url` | `string` | yes | — |
| `description` | `string` or `null` | yes | — |
| `severity_floor` | `string` | yes | — |
| `active` | `boolean` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `secret` | `string` | yes | Signing secret. Shown once; store it now. |

### `WebhookListOut`

Every configured target.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `WebhookOut` | yes | — |

### `WebhookOut`

A configured target, **without** its secret.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | — |
| `url` | `string` | yes | — |
| `description` | `string` or `null` | yes | — |
| `severity_floor` | `string` | yes | — |
| `active` | `boolean` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
