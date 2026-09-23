import base64
import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_conn
from app.models import TransactionListResponse

router = APIRouter()

ALLOWED_TYPES = {"deposit", "withdrawal", "transfer_in", "transfer_out"}


def _encode_cursor(created_at: str, item_id: int) -> str:
    payload = json.dumps({"created_at": created_at, "id": item_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor_str: str) -> tuple[str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        created_at = data["created_at"]
        item_id = int(data["id"])
        if not isinstance(created_at, str):
            raise ValueError()
        return created_at, item_id
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


def _validate_date(date_str: str, param_name: str) -> str:
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        if parsed.strftime("%Y-%m-%d") != date_str:
            raise ValueError()
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"Invalid '{param_name}' date format. Expected YYYY-MM-DD."
        )


@router.get("/accounts/{account_id}")
def get_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute(
        "SELECT id, client_name, balance FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {
        "id": row["id"],
        "client_name": row["client_name"],
        "balance": f"{Decimal(str(row['balance'])):.2f}",
    }


@router.get("/accounts/{account_id}/positions")
def get_positions(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="account not found")

    query = """
        SELECT p.fund_code, f.name AS fund_name, p.units, f.nav
        FROM positions p
        JOIN funds f ON p.fund_code = f.code
        WHERE p.account_id = ?
        ORDER BY p.fund_code
    """
    rows = conn.execute(query, (account_id,)).fetchall()
    result = []
    for row in rows:
        units = Decimal(str(row["units"]))
        nav = Decimal(str(row["nav"]))
        market_value = units * nav
        result.append(
            {
                "fund_code": row["fund_code"],
                "fund_name": row["fund_name"],
                "units": f"{units:.4f}",
                "market_value": f"{market_value:.2f}",
            }
        )
    return {"account_id": account_id, "positions": result}


@router.get("/accounts/{account_id}/transactions", response_model=TransactionListResponse)
def get_transactions(
    account_id: str,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="account not found")

    if type is not None and type not in ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid type. Must be one of {sorted(ALLOWED_TYPES)}.")

    from_date = _validate_date(from_, "from") if from_ else None
    to_date = _validate_date(to, "to") if to else None

    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="'from' date cannot be after 'to' date.")

    cursor_created_at, cursor_id = _decode_cursor(cursor) if cursor else (None, None)

    conditions = ["account_id = ?"]
    params: list[object] = [account_id]

    if from_date:
        conditions.append("date(created_at) >= ?")
        params.append(from_date)

    if to_date:
        conditions.append("date(created_at) <= ?")
        params.append(to_date)

    if type:
        conditions.append("type = ?")
        params.append(type)

    if cursor_created_at is not None and cursor_id is not None:
        conditions.append("(created_at < ? OR (created_at = ? AND id < ?))")
        params.extend([cursor_created_at, cursor_created_at, cursor_id])

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT id, type, amount, created_at
        FROM transactions
        WHERE {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """
    params.append(limit + 1)

    rows = conn.execute(query, params).fetchall()
    has_more = len(rows) > limit
    paged_rows = rows[:limit]

    items = [
        {
            "id": r["id"],
            "type": r["type"],
            "amount": f"{Decimal(str(r['amount'])):.2f}",
            "created_at": r["created_at"],
        }
        for r in paged_rows
    ]

    next_cursor = _encode_cursor(paged_rows[-1]["created_at"], paged_rows[-1]["id"]) if has_more else None

    return {"items": items, "next_cursor": next_cursor}
