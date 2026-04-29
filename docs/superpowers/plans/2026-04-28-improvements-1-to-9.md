# tg-monitor Improvements 1–9 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 9 pending improvements in order: auto-reconnect, smarter backfill, history window, packaging script, version source-of-truth, reply detection in backfill, test coverage, config-load deduplication, and notification-click-to-Telegram.

**Architecture:** Changes span three layers — `tg_client.py` (items 1, 2, 6, 8), `app.py` (items 3, 9), packaging/build tooling (items 4, 5), and tests (item 7). Each task is self-contained and commits independently. TDD where the code under test is a pure/mockable function; manual verification where macOS AppKit UI is required.

**Tech Stack:** Python 3.11+, Telethon, rumps, PyObjC (AppKit), SQLite, pytest, uv/hatchling, bash

**Status:** ✅ All 9 tasks completed — PR #1 open at https://github.com/fzh160616/TGMonitor/pull/1

---

## Chunk 1: tg_client.py improvements (Items 1, 2, 6, 8)

### Task 1: Auto-reconnect (Item 1) ✅

**Files:**
- Modify: `tg_monitor/tg_client.py` — wrap `_main()` in a retry loop inside `_run()`
- Test: `tests/test_tg_client_utils.py` — test `_reconnect_delay()` helper

**Context:** Added `_shutdown: threading.Event` to `TgWorker`. `_run()` now loops with exponential backoff (5s→10s→…→120s). Backoff resets to 0 after a healthy connection (≥60s). Sleep is interruptible via `_shutdown.wait(timeout=delay)`. `_stop_event` is created in `_run()` before each `_main()` call to avoid races.

- [x] Write failing test for `_reconnect_delay()`
- [x] Add `_reconnect_delay()` helper
- [x] Add `_shutdown` threading.Event and update `stop()`
- [x] Replace `_run()` with retry loop; move `_stop_event` creation out of `_main()`
- [x] All tests pass
- [x] Commit: `feat: auto-reconnect with exponential backoff on worker crash`

---

### Task 2: Smarter Backfill Limit (Item 2) ✅

**Files:**
- Modify: `tg_monitor/tg_client.py` — replace hard-coded `limit=30` with dynamic limit
- Test: `tests/test_tg_client_utils.py` — test `_backfill_limit()`

**Context:** `_backfill_limit(minutes) = max(100, minutes * 20)`. `iter_messages` is newest-first by default; break on `msg.date.timestamp() < cutoff`. Added `_shutdown` check at top of dialog loop for fast exit. Do NOT use `offset_date` — Telethon's `offset_date` always means "older than", regardless of `reverse`.

- [x] Write failing test for `_backfill_limit()`
- [x] Add `_backfill_limit()` helper
- [x] Update `_backfill()` with dynamic limit + shutdown check
- [x] All tests pass
- [x] Commit: `feat: dynamic backfill limit based on backfill_minutes`

---

### Task 3: Reply Detection in Backfill (Item 6) ✅

**Files:**
- Modify: `tg_monitor/tg_client.py` — fix `_process_raw()` to detect reply
- Test: `tests/test_tg_client_utils.py` — test `_raw_is_reply()`, `_raw_reply_msg_id()`

**Context:** Added `_raw_is_reply(msg)` and `_raw_reply_msg_id(msg)` helpers (duck-typed, testable without Telethon). In `_process_raw()`, fetch replied-to message via `client.get_messages(dialog.id, ids=reply_msg_id)` and use `getattr(replied, "sender_id", None)` to guard against `MessageEmpty`.

- [x] Write failing tests for reply helpers
- [x] Add `_raw_is_reply()` and `_raw_reply_msg_id()` helpers
- [x] Update `_process_raw()` to detect replies
- [x] All tests pass
- [x] Commit: `fix: detect reply-to-me in backfill messages`

---

### Task 4: Config Load Deduplication (Item 8) ✅

**Files:**
- Modify: `tg_monitor/tg_client.py` — pass pre-loaded `Config` into `_process_raw()`

**Context:** `_backfill()` loads config once; `_process_raw()` now accepts `c: cfg.Config` parameter instead of calling `cfg.load()` internally.

- [x] Update `_process_raw()` signature to `(self, client, msg, dialog, c)`
- [x] Update `_backfill()` to load once and pass `c`
- [x] All tests pass
- [x] Commit: `refactor: pass config into _process_raw to avoid redundant cfg.load()`

---

## Chunk 2: UI improvements (Items 3 & 9)

### Task 5: History Window (Item 3) ✅

**Files:**
- Create: `tg_monitor/history.py` — `_render_html()` + `open_history()`
- Modify: `tg_monitor/app.py` — add "查看历史…" menu item
- Test: `tests/test_history.py` — HTML generation tests

**Context:** `open_history()` uses `tempfile.mkstemp()` (safe, no TOCTOU race). HTML escapes all user content via `html.escape()`. Opens in default browser via `subprocess.Popen(["open", tmp_path])`.

- [x] Write failing tests for `_render_html()`
- [x] Create `tg_monitor/history.py`
- [x] Add "查看历史…" menu item and `_open_history()` callback to `app.py`
- [x] All tests pass
- [x] Commit: `feat: add history window showing up to 500 mentions in browser`

---

### Task 6: Notification Click to Telegram (Item 9) ✅

**Files:**
- Modify: `tg_monitor/app.py` — `_tg_message_url()` helper + notification handler + menu click fix
- Test: `tests/test_tg_open_url.py` — URL generation tests

**Context:** `@rumps.notifications` + `NSUserNotificationCenter` is broken on macOS 15. Final fix: first click on a menu item marks as read **and** opens Telegram via `tg://openmessage?chat_id=<id>&message_id=<id>`. Second click shows detail dialog. The `@rumps.notifications` handler is kept as best-effort for older macOS.

**Note on `info` parameter:** rumps `Notification` is a `Mapping` that delegates directly to the `data` dict. Access as `info.get("mention_id")`, NOT `info.get("data", {}).get("mention_id")`.

- [x] Write failing test for `_tg_message_url()`
- [x] Add `_tg_message_url()` to `app.py`
- [x] Add `_app_instance` singleton and `@rumps.notifications` handler
- [x] Fix: move Telegram open to first menu-item click (macOS 15 workaround)
- [x] All tests pass
- [x] Commit: `feat: open Telegram message on notification click`
- [x] Commit: `fix: open Telegram on first menu item click instead of unreliable notification click`

---

## Chunk 3: Packaging & Version (Items 4 & 5)

### Task 7: Single Source of Truth for Version (Item 5) ✅

**Files:**
- Modify: `tg_monitor/__init__.py` — use `importlib.metadata`
- Test: `tests/test_version.py`

**Context:** `importlib.metadata.version("tg-monitor")` reads from installed dist-info. Falls back to `"0.1.0"` if not installed. `tomllib` is stdlib in Python 3.11+.

- [x] Write version tests
- [x] Update `__init__.py`
- [x] All tests pass
- [x] Commit: `chore: use importlib.metadata for __version__ single source of truth`

---

### Task 8: Build/Packaging Script (Item 4) ✅

**Files:**
- Create: `scripts/build_release.sh`

**Context:** Uses venv Python for `tomllib` (system Python 3.9 on macOS lacks it). `sed -i ''` is correct BSD sed syntax for macOS. Produces `dist/tg-monitor-<version>.zip` containing wheel + install.sh + creds.env.example + README.md.

- [x] Create `scripts/build_release.sh`
- [x] Verify script runs and produces correct zip
- [x] Commit: `chore: add build_release.sh wheel-based packaging script`

---

## Chunk 4: Test Coverage (Item 7)

### Task 9: Test Coverage ✅

**Files:**
- Create: `tests/test_config.py` — 5 tests
- Create: `tests/test_notifier.py` — 5 tests
- Modify: `tests/test_tg_client_utils.py` — add `_is_excluded`, `_display_name` tests

**Context:**
- Config fixture patches `tg_monitor.config.CONFIG_PATH`, `tg_monitor.paths.DATA_DIR`, and `tg_monitor.paths.LOG_DIR` (all three needed to avoid side effects in `ensure_dirs()`).
- Notifier tests use `mock.call_args.kwargs` (keyword args) not positional — `rumps.notification()` uses all kwargs.
- `app.py` and async Telethon core are not unit-tested (require live macOS/Telethon).

- [x] Write and run config tests (5 pass)
- [x] Write and run notifier tests (5 pass)
- [x] Extend tg_client_utils with `_is_excluded`, `_display_name` tests
- [x] Full suite: 58 passed
- [x] Commit: `test: add coverage for config, notifier, and tg_client utilities`

---

## Final Results

- **Tests:** 58 passed (was 21)
- **New files:** `tg_monitor/history.py`, `scripts/build_release.sh`, `tests/test_config.py`, `tests/test_notifier.py`, `tests/test_history.py`, `tests/test_tg_open_url.py`, `tests/test_version.py`, `tests/test_tg_client_utils.py`
- **PR:** https://github.com/fzh160616/TGMonitor/pull/1
