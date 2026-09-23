## What I don't trust
Before shipping to production, I would verify:
1. **SQLite Concurrency & Locking**: Under concurrent transfer requests, SQLite's database-level write locks can encounter `sqlite3.OperationalError: database is locked`. In production, a client-server RDBMS (e.g., PostgreSQL) with row-level locks (`SELECT ... FOR UPDATE`) is essential.
2. **Cursor Tampering**: Cursors are URL-safe base64 JSON encoding timestamp and ID. While malformed cursors return 400, they lack cryptographic HMAC signing. A user could forge arbitrary timestamp boundaries.
3. **Timezone Boundary Edge Cases**: SQLite's `date(created_at)` relies on UTC strings. If transactions arrive with non-UTC timezone offsets, date-range filtering could misalign without explicit normalization.

## AI use
I used an AI assistant in the Antigravity IDE for:
- Resolving IDE language server configuration for virtual environments.
- Formulating the composite cursor pagination logic (`created_at DESC, id DESC`).
- Generating boundary test cases covering date/type filters, pagination resilience, and error statuses.
- Performing structured security and distributed systems analysis on `review/pr_17.diff` (SQL injection and dual-write failure modes).
