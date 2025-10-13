# TeamSchedulerBot Improvement Plan

This document outlines the planned improvements to the TeamSchedulerBot codebase, broken down into incremental Pull Requests for easier review and testing.

## Completed PRs

### ✅ PR #1: Add type hints and improve logging
**Branch:** `feat/add-type-hints-and-logging`  
**Status:** Ready for review

**Changes:**
- Added type hints for all functions with proper return types
- Improved logging format with timestamps and structured output
- Added comprehensive docstrings for all functions
- Added more descriptive log messages throughout
- Added `exc_info=True` to error logs for better debugging
- Added startup logging to show configuration at boot

**Benefits:**
- Better code maintainability and IDE support
- Easier debugging with structured logs
- Self-documenting code with docstrings

---

### ✅ PR #2: Add environment variable validation
**Branch:** `feat/env-var-validation`  
**Status:** Ready for review

**Changes:**
- Added `validate_environment()` function that checks required env vars on startup
- Fail fast with clear error message if `SLACK_BOT_TOKEN` or `SLACK_SIGNING_SECRET` missing
- Made reminder schedule configurable via `REMINDER_HOUR`, `REMINDER_MINUTE`, and `REMINDER_TIMEZONE` env vars
- Added comprehensive startup logging showing all configuration
- Improved logging format in main entrypoint

**Benefits:**
- Faster failure detection (fail at startup vs runtime)
- More flexible configuration without code changes
- Better visibility into bot configuration

**New Environment Variables:**
- `REMINDER_HOUR` (default: 9) - Hour to send daily reminder (0-23)
- `REMINDER_MINUTE` (default: 0) - Minute to send daily reminder (0-59)
- `REMINDER_TIMEZONE` (default: "Europe/Berlin") - Timezone for scheduler

---

## Planned PRs

### 📋 PR #3: Move team members to environment variable
**Branch:** `feat/configurable-team-members`  
**Priority:** Medium

**Planned Changes:**
- Extract hardcoded user IDs to `TEAM_MEMBERS` env var (comma-separated)
- Keep backward compatibility with defaults
- Add validation to ensure at least one team member exists

**Benefits:**
- No code changes needed to update team roster
- Easier to manage in different environments (dev/staging/prod)

**New Environment Variables:**
- `TEAM_MEMBERS` - Comma-separated list of Slack user IDs

---

### 📋 PR #4: Add error handling and retry logic
**Branch:** `feat/error-handling-retry`  
**Priority:** High

**Planned Changes:**
- Import and handle `SlackApiError` specifically
- Implement retry logic for Slack API calls (exponential backoff)
- Better exception handling in state management (handle corrupted JSON)
- Add validation in `load_state()` to ensure index is within bounds
- Handle edge cases (empty team_members list, invalid state file)

**Benefits:**
- More resilient to transient Slack API failures
- Better handling of edge cases and corrupted state
- Reduced manual intervention needed

---

### 📋 PR #5: Add health check endpoints
**Branch:** `feat/health-endpoints`  
**Priority:** Medium

**Planned Changes:**
- Add `/health` endpoint (basic liveness check)
- Add `/ready` endpoint (readiness check including scheduler status)
- Add `/metrics` endpoint with basic metrics (rotation count, uptime)
- Enable better Kubernetes integration with proper probes

**Benefits:**
- Better Kubernetes integration (liveness/readiness probes)
- Easier monitoring and debugging
- Visibility into bot state without checking logs

---

### 📋 PR #6: Add graceful shutdown
**Branch:** `feat/graceful-shutdown`  
**Priority:** Medium

**Planned Changes:**
- Add signal handlers for SIGTERM and SIGINT
- Properly shutdown scheduler on termination
- Flush any pending jobs
- Log shutdown sequence

**Benefits:**
- Production readiness (proper Kubernetes termination)
- No lost jobs during container restarts
- Cleaner shutdown process

---

### 📋 PR #7: Clean up dependencies and update Python
**Branch:** `chore/update-dependencies`  
**Priority:** Low

**Planned Changes:**
- Remove unused `schedule` package from requirements.txt
- Remove unused `pytz` import (APScheduler handles timezone)
- Update to Python 3.11+ in Dockerfile
- Pin all dependency versions more strictly
- Add version ranges for security updates

**Benefits:**
- Smaller Docker image
- Better security posture with updated Python
- Clearer dependency management

---

### 📋 PR #8: Add comprehensive documentation
**Branch:** `docs/comprehensive-readme`  
**Priority:** Medium

**Planned Changes:**
- Comprehensive README with:
  - Project overview and purpose
  - Setup instructions (local development + Kubernetes)
  - Environment variable documentation
  - Architecture overview
  - Troubleshooting guide
- Add inline comments for complex logic
- Add docstring examples

**Benefits:**
- Easier onboarding for new developers
- Reduced support burden
- Better long-term maintainability

---

## Implementation Strategy

### Phase 1: Core Improvements (PRs #1-2) ✅
These PRs improve code quality and configuration without changing behavior. Safe to merge quickly.

### Phase 2: Reliability (PRs #3-4)
These PRs improve reliability and make the bot more resilient. Should be tested thoroughly in a dev environment.

### Phase 3: Operations (PRs #5-6)
These PRs improve operational aspects for production deployment. Important for Kubernetes environments.

### Phase 4: Maintenance (PRs #7-8)
These PRs clean up technical debt and improve documentation. Can be done in parallel with other work.

---

## Testing Recommendations

For each PR:
1. **Local Testing:** Run bot locally with test channel to verify functionality
2. **Edge Case Testing:** Test error conditions (missing env vars, invalid state, Slack API errors)
3. **Integration Testing:** Deploy to staging/test environment before production
4. **Monitoring:** Watch logs after deployment to catch any issues

---

## Rollback Strategy

Each PR is independent and can be rolled back individually:
- PRs #1-2: Configuration changes only, safe to rollback
- PRs #3-4: May require environment variable updates on rollback
- PRs #5-6: Safe to rollback, only affects monitoring/shutdown
- PRs #7-8: Safe to rollback, documentation changes only

---

## Questions or Concerns?

If you have questions about any of these improvements or want to adjust priorities, please discuss before merging.

