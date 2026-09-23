app/routes/test_transfers.py
What was wrong:

Precision Loss: Float arithmetic caused subtle rounding errors during money transfers (e.g., deducting 0.10 ten times left 998.9999999999998 instead of 999.00).

Missing Idempotency: Duplicate retry requests were processed as entirely new transactions, causing double-billing and failing idempotency tests.

Missing Validation: The endpoint accepted invalid states, such as negative amounts and transfers to the exact same account.

What I changed:

Migrated all amount calculations to decimal.Decimal to guarantee precise mathematical operations before persisting to the database.

Implemented Idempotency-Key header tracking. The route now queries a newly created transfers table to check for previously processed keys and returns the original transaction ID without altering balances.

Added pydantic.condecimal to automatically reject negative or zero amounts (422 Unprocessable Entity) and route logic to reject self-transfers (400 Bad Request).

app/routes/test_accounts.py
What was wrong:

N+1 Query Issue: The get_positions endpoint queried the database inside a loop for every single fund, generating 8 SELECT statements per request and failing query count limits.

Formatting Failures: SQLite stores numeric values as REAL (floats), which naturally drop trailing zeros (e.g., returning 750.0 instead of 750.00). This caused exact string equality assertions in the tests to fail.

What I changed:

Optimized get_positions by replacing the iterative queries with a single SQL JOIN between the positions and funds tables.

Enforced strict string formatting for monetary and unit outputs. Account balances and market values are now explicitly formatted to two decimal places (:.2f), and fund units to four (:.4f), ensuring exact compliance with the JSON shapes expected by the test suite.
