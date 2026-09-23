import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException

from app.db import get_conn
from app.models import TransferRequest, TransferResponse

router = APIRouter()


@router.post("/transfers", status_code=201, response_model=TransferResponse)
def create_transfer(
    req: TransferRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if idempotency_key:
        existing = conn.execute(
            "SELECT id, from_balance, to_balance FROM transfers WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return {
                "transfer_id": existing["id"],
                "from_balance": f"{Decimal(str(existing['from_balance'])):.2f}",
                "to_balance": f"{Decimal(str(existing['to_balance'])):.2f}",
            }

    if req.from_account == req.to_account:
        raise HTTPException(status_code=400, detail="cannot transfer to same account")

    src = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (req.from_account,)).fetchone()
    dst = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (req.to_account,)).fetchone()
    if src is None or dst is None:
        raise HTTPException(status_code=404, detail="account not found")

    src_balance = Decimal(str(src["balance"]))
    dst_balance = Decimal(str(dst["balance"]))
    amount = req.amount

    if src_balance < amount:
        raise HTTPException(status_code=409, detail="insufficient funds")

    new_src = src_balance - amount
    new_dst = dst_balance + amount
    transfer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (float(new_src), req.from_account))
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (float(new_dst), req.to_account))
        conn.execute(
            """
            INSERT INTO transfers (
                id, from_account, to_account, amount, created_at, idempotency_key, from_balance, to_balance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transfer_id,
                req.from_account,
                req.to_account,
                float(amount),
                now,
                idempotency_key,
                float(new_src),
                float(new_dst),
            ),
        )
        conn.execute(
            "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, 'transfer_out', ?, ?, ?)",
            (req.from_account, float(amount), now, transfer_id),
        )
        conn.execute(
            "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, 'transfer_in', ?, ?, ?)",
            (req.to_account, float(amount), now, transfer_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        if idempotency_key:
            existing = conn.execute(
                "SELECT id, from_balance, to_balance FROM transfers WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return {
                    "transfer_id": existing["id"],
                    "from_balance": f"{Decimal(str(existing['from_balance'])):.2f}",
                    "to_balance": f"{Decimal(str(existing['to_balance'])):.2f}",
                }
        raise
    except Exception:
        conn.rollback()
        raise

    return {
        "transfer_id": transfer_id,
        "from_balance": f"{new_src:.2f}",
        "to_balance": f"{new_dst:.2f}",
    }
