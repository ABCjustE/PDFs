# Textual Client — Event Cycle / State Timing Note

## Problem Observed

In the Textual prototype, pressing `Confirm` sometimes appeared to do nothing:

- status text did not visibly change
- the job looked like it was not running
- `Confirm` could look dead even though the handler was wired

The underlying `InventoryJob` and `client.py` path were not the real problem.

---

## Actual Root Cause

The issue was in the UI event cycle:

- state update
- widget update
- worker launch

were all happening too eagerly inside the same button event callback.

That meant the Textual app did not always get a clean chance to:

- apply the new widget state
- repaint the status text
- settle the current event cycle

before background work started.

This was a framework timing issue, not a PDF processing issue.

---

## The `_running` Mistake

A silent guard made the problem much worse:

```python
if self._running:
    return
```

Why this was bad:

- it duplicated the protection already provided by disabling the `Confirm` button
- if `_running` was unexpectedly `True`, the handler exited silently
- the UI showed no explanation
- the button looked broken

Removing the guard helped because it removed the silent no-op path.

Lesson:

- avoid silent boolean guard returns in UI event handlers
- if a guard is needed, make it visible in the UI or log

Better pattern:

```python
if self.running:
    status.update("Already running.")
    return
```

---

## Correct Pattern

For long-running work triggered by a Textual button:

1. update UI state first
2. let the event/render cycle finish
3. start the work on the next tick / timer / worker

Example:

```python
status.update("Running inventory job...")
self.refresh(layout=True)
self.set_timer(0.01, self._start_job_thread)
```

This separates:

- visible UI state transition
- expensive side effect

and makes the app behavior predictable.

---

## Practical Rule

In Textual:

- do not do heavy work immediately in the same event callback that changes UI state
- disable buttons for interaction control
- use explicit state for rendering / diagnostics
- do not rely on a silent `_running` guard as the main protection

Short version:

- update UI first
- let Textual breathe
- then launch work

---

## Debugging Note

To debug the issue, a logged property for `running` was helpful:

- log every state transition
- include old value → new value
- include a short stack trace when needed

This proved:

- `confirm_run()` was entered
- the worker actually started
- `_finish_process()` reset the state correctly

So the problem was not "button not wired" or "job broken". It was event-cycle timing plus
an over-eager silent guard.
