# Code Review: PR #17 — Ledger sync + client search

### Comment 1
- **File & Line**: `app/routes/search.py:66-68`
- **Severity**: blocker
- **Problem**: Critical SQL Injection vulnerability. User-controlled input `name` is directly interpolated into the SQL string via an f-string (`f"... LIKE '%{name}%' ..."`), allowing callers to execute arbitrary SQL commands or exfiltrate data.
- **Suggested Fix**: Use parameterized query execution with bound parameters:
  ```python
  rows = conn.execute(
      "SELECT id, client_name FROM accounts WHERE client_name LIKE ? ORDER BY client_name",
      (f"%{name}%",)
  ).fetchall()
  ```

---

### Comment 2
- **File & Line**: `app/routes/transfers.py:101-104`
- **Severity**: blocker
- **Problem**: Dual-write consistency failure. `conn.commit()` commits the local balance transfer before calling `post_transfer()`. If `post_transfer()` fails after its retries, the local database remains debited/credited while the core ledger receives nothing, causing permanent data desynchronization and raising an unhandled 500 error to the client.
- **Suggested Fix**: Implement a transactional outbox table within the same SQLite transaction, or dispatch ledger synchronization via a reliable background worker with retries and dead-letter queueing rather than calling it synchronously post-commit.

---

### Comment 3
- **File & Line**: `app/services/ledger_client.py:35-48`
- **Severity**: blocker
- **Problem**: Lack of downstream idempotency. The retry wrapper in `with_retry` re-posts transfers without passing an idempotency key to the external ledger. If an HTTP request times out after the ledger has already processed it, the retry will cause duplicate execution on the downstream ledger.
- **Suggested Fix**: Generate or forward a unique idempotency key (such as `transfer_id` or the incoming `Idempotency-Key`) in the ledger payload or headers so retried HTTP requests cannot double-charge.

---

### Comment 4
- **File & Line**: `app/services/ledger_client.py:40`
- **Severity**: should-fix
- **Problem**: Naive timestamp generation. `datetime.now().isoformat()` produces a naive local timestamp rather than a UTC ISO 8601 string, violating API conventions.
- **Suggested Fix**: Use UTC timezone:
  ```python
  from datetime import datetime, timezone
  "submitted_at": datetime.now(timezone.utc).isoformat()
  ```

---

### Comment 5
- **File & Line**: `app/routes/search.py:70-71`
- **Severity**: should-fix
- **Problem**: Silent exception swallowing. Catching all `Exception` instances and returning `{"results": []}` conceals database outages, schema errors, and programming bugs from logs and monitoring.
- **Suggested Fix**: Remove the broad `try...except` block or log the exception with `logging.exception()` and allow FastAPI to return an HTTP 500.

---

### Comment 6
- **File & Line**: `app/routes/transfers.py:104`
- **Severity**: should-fix
- **Problem**: String conversion of float amount. `str(req.amount)` can yield unformatted float representations (e.g. `"10.1"` or `"10.100000000000001"`) instead of the required two-decimal currency format.
- **Suggested Fix**: Format the amount strictly to two decimal places:
  ```python
  f"{Decimal(str(req.amount)):.2f}"
  ```

---

### Comment 7
- **File & Line**: `app/services/ledger_client.py:22-31`
- **Severity**: should-fix
- **Problem**: Synchronous blocking sleep in web handler thread. `time.sleep()` blocks the worker thread for up to several seconds during retries, degrading request throughput.
- **Suggested Fix**: Perform downstream synchronization asynchronously or use an async HTTP client with `asyncio.sleep()`.

---

### Comment 8
- **File & Line**: `app/services/ledger_client.py:22`
- **Severity**: nit
- **Problem**: Missing `functools.wraps(fn)` on the retry decorator wrapper, which discards the wrapped function's docstring, name, and signature.
- **Suggested Fix**: Add `@functools.wraps(fn)` to `wrapper`.

---

### Comment 9
- **File & Line**: `app/services/ledger_client.py:43`
- **Severity**: nit
- **Problem**: Creates a new connection on every call with `httpx.post()` instead of reusing a persistent `httpx.Client()` session with connection pooling.
- **Suggested Fix**: Instantiate a shared `httpx.Client()` instance.

---

## Decision
**Request Changes**
The PR cannot be approved due to the critical SQL injection vulnerability in `/accounts/search` and the dual-write consistency / missing idempotency flaws in the core ledger synchronization.
