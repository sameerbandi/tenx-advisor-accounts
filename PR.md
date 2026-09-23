### What was wrong
- **N+1 Queries**: `GET /accounts/{id}/positions` queried funds inside a loop, issuing 8 SELECTs per request.
- **Precision Loss**: Float math caused rounding drift during money transfers (e.g. `998.9999999999998`).
- **Missing Idempotency**: `POST /transfers` ignored `Idempotency-Key`, causing duplicate transfers on retry.
- **Transfer Defects**: The endpoint accepted negative/zero amounts, sub-cent fractions, and transfers to the same account without transaction rollback on failure.

### What was changed
- Replaced the positions query loop with a single SQL `JOIN`, reducing queries to <= 2.
- Switched transfer math and monetary responses to `decimal.Decimal` with strict two-decimal string formatting.
- Added `Idempotency-Key` tracking and replay on the `transfers` table.
- Added Pydantic validation for positive two-decimal amounts and route validation rejecting self-transfers (400).
- Wrapped transfer execution in atomic transaction rollback.
- Added test coverage for negative, zero, fractional, and self-transfers.

### What was not changed & why
- SQLite column types (`REAL`) were preserved to prevent migration issues with existing databases; precision is strictly managed in the application layer instead.
