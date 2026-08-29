# Continuation Notes — arena/01a04c02

**Branch:** `arena/01a04c02-ai-enhanced-cybersecurity-thre`  
**Head:** `dc8b8ce` Phase 37  
**Status:** Committed + pushed to origin. Ready for PR.

## What is on this branch vs main (3b10bfb)

Main (3b10bfb) already contains:
- NOCTRA rebrand, SIGNAL demo, connector hardening (PR #6 merged)

This branch adds **Phase 36 + Phase 37**:

### Phase 36 (b8a9417)
- Trust hardening: reasoning source naming, confidence n/a on fallback, honest empty states
- 6 scenarios (credential_leak, phishing_outbreak, data_exfiltration, compromised_api_key, insider_threat, ransomware_activity)
- Export case JSON, scenario list endpoint
- Frontend tests fixed (32 tests passing)

### Phase 37 (dc8b8ce) — current HEAD
- `CONNECTOR_ENCRYPTION_KEY` dedicated key in config.py — decouples connector secret encryption from JWT rotation
  - `secrets.py` now prefers `CONNECTOR_ENCRYPTION_KEY`, fallback `JWT_SECRET_KEY`
  - Verified: encrypt with dedicated key, rotate JWT, still decrypts
- `ANALYST_CHAT_RATE_LIMIT=20` per org:user:case
  - `analyst_service.py`: `_chat_limiter` RateLimiter, `ChatRateLimited` with retry_after, `_check_chat_rate()`
  - Endpoint `POST /analyst/cases/{id}/chat` returns 429 with Retry-After on abuse
- `bulk_decide()` — honest bulk approve/decline
  - Only pending cases acted upon, failed list with reasons, never silent skip
  - Max 50 case_ids via Pydantic validation
  - New endpoint `POST /analyst/bulk-decide` + frontend UI in FeedPage (checkboxes, select-all pending, bulk actions)
- Scenario validation: `POST /analyst/simulate?scenario_type=invalid` → 422 with valid list
- Frontend: `CasePage.tsx` shows rate-limit message in chat
- Tests: `tests/test_analyst_phase37.py` 7 tests — bulk, rate-limit (unit + HTTP 429), scenario 422, encryption decoupling
- Docs: `.env.example` documents new keys

## Gates (verified)

```
backend: 25 tests (test_analyst.py + test_analyst_phase37.py) — 18 + 7 = 25 passed
dashboard: 32 tests — all passing
build: vite build clean
py_compile: analyst.py, analyst_service.py, config.py, secrets.py — OK
```

## How to create PR and merge

This branch is pushed: `dc8b8ce` exists on origin (verified via `git ls-remote`).

1. GitHub → Pull Requests → New PR → base: main, compare: arena/01a04c02-ai-enhanced-cybersecurity-thre
2. Or via CLI:
   ```
   gh pr create --base main --head arena/01a04c02-ai-enhanced-cybersecurity-thre --title "Phase 37: bulk decisions, chat rate-limit, dedicated connector key" --body "See docs/continuation-notes.md"
   ```
3. Merge — it's a fast-forward of main (no conflicts expected for these files, since main is ancestor for most, but check).

## What next session should do

After merge, new session starts from updated main. Check:
```
git log --oneline -5
```
Should show dc8b8ce (or its squash). If not, this file tells you what was done.

Next candidates (Stage 8 was pick-one, but we did bulk/rate-limit as hardening):
- Live alert streaming (SSE) — pairs with scheduled polling
- PDF report export — analyst workflow
- Connector breadth (more sources)
- SSO/SCIM

All preserve honesty contract: SOAR record-only, reasoning source named, confidence n/a on fallback, no fake telemetry, tenant scoping, append-only audit.

## Standing limits

- Stream is per-process (if implemented later, needs Redis for multi-worker)
- Polling on by default (CONNECTOR_POLL_ENABLED)
- PDF needs reportlab if added later
- Demo evidence never generated — always from real rows
