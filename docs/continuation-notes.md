# Continuation Notes — arena/01a04c02

**Branch:** `arena/01a04c02-ai-enhanced-cybersecurity-thre`  
**Head:** Phase 39 scheduled polling — watches continuously  
**Previous Heads:** `c40b693` Phase 38 docs, `301b489` streaming+PDF, `9afccf0` Phase 37  
**Status:** Ready to commit + push. PR #7 open — DO NOT MERGE until user says.

## What is on this branch vs main (3b10bfb)

Main already has PR #6 (connector hardening). This branch adds:

### Phase 36 (b8a9417)
- Trust hardening, 6 scenarios, export JSON, frontend tests

### Phase 37 (dc8b8ce)
- `CONNECTOR_ENCRYPTION_KEY` dedicated key decouples from JWT rotation
- `ANALYST_CHAT_RATE_LIMIT` 20/min per org:user:case, 429 with Retry-After
- `bulk_decide()` honest pending-only, max 50, endpoint + frontend bulk UI
- Scenario validation 422, chat 429 messaging
- Tests: test_analyst_phase37.py 7 tests

### Phase 38 (301b489)
**Live alert streaming (SSE):**
- `app/core/events.py`: EventBus thread-safe via `call_soon_threadsafe`, per-process scope (honest: multi-worker needs Redis), queue full → dropped + gap frame, TicketStore single-use 30s TTL
- `app/api/v1/endpoints/stream.py`: POST /stream/ticket, GET /stream/alerts?ticket=, GET /stream/status
- `connector_service.py`: _ingest_events publishes after commit, never before
- Frontend: streamApi.ts, useAlertStream.ts, AlertList live pill
- Tests: 17 stream tests

**PDF report export:**
- `pdf_report.py`: reportlab, pageCompression=0, preserves '(templated fallback)'
- Endpoint `GET /analyst/cases/{id}/report.pdf`: 409 if no report, 501 if missing dep
- Frontend: CasePage Export PDF via blob download
- Tests: 7 renderer + 5 API + 3 frontend PDF

### Phase 39 (current) — scheduled polling
**Watches continuously without manual Sync:**
- `app/core/config.py`: CONNECTOR_POLL_ENABLED (default true), INTERVAL 900s (15 min), JITTER 60s, BACKOFF base 300s max 3600s
- `app/services/connector_scheduler.py`: daemon thread, _should_poll respects enabled/mode/endpoint/interval+jitter, backoff on error exponential with jitter reset on success, _poll_once queries enabled poll-mode connectors, calls sync with actor='scheduler', thread-safe _NEXT_POLL dict, start/stop/reset
- `app/main.py`: lifespan starts scheduler on startup, stops on shutdown (honest: per-process, N workers -> N threads poll, dedupe prevents duplicate alerts)
- `connector_service.py` already publishes to EventBus after commit (Phase 38) — scheduler benefits automatically, so scheduled poll -> ingest -> SSE frame
- Tests: test_connector_scheduler.py 5 tests (never-synced, interval, disabled/push, backoff, enabled flag)
- docs/demo.md: known gaps updated (per-process, backoff, how to disable), automated gates 196+ backend, 43 dashboard
- .env.example: documents CONNECTOR_POLL_* settings

## Gates (verified)

```
backend: 59+ tests (18 analyst + 7 phase37 + 17 stream + 7 pdf renderer + 5 pdf API + 5 scheduler) — all passing
dashboard: 43 tests (10 files) — all passing
build: vite build clean (previous)
py_compile: scheduler, events, stream, pdf_report, analyst, connector_service — OK
```

## Recoverability of previous discussion

The long previous discussion text you saw is not stored as chat history in the workspace — it was condensed into session memory (the internal summary at start of this session). What IS recoverable:

- Git commits: `git log --oneline` shows all phases with messages explaining why
- This file: continuation-notes.md
- `docs/session-log.md` and `docs/demo.md`
- Backend tests: they encode the honesty contract
- PR #7 description contains summary

If you need the full verbatim chat, it is not persisted in the repo — only the condensed memory survives across sessions. The code and tests are the durable artifact.

## How to create PR and merge (when you say)

Branch is pushed: `c40b693` exists on origin. After Phase 39 commit, push again.

PR #7 already exists: https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/pull/7
It now includes Phase 38. Phase 39 will be added on push. You said don't merge until you say — so it's left open.

When you want to merge:
- GitHub UI → Merge PR #7
- After merge, new session will see everything on main via `git log`

## Next candidates

- Connector breadth (more sources — makes live stream + scheduler busy)
- SSO/SCIM
- All preserve honesty contract
