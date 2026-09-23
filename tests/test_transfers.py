#def _transfer(client, amount, key=None, src="ACC-1001", dst="ACC-1002"):
 #   headers = {"Idempotency-Key": key} if key else {}
 #   return client.post("/transfers", json={"from_account": src, "to_account": dst, "amount": amount}, headers=headers)


#def test_transfer_moves_money(client):
#    r = _transfer(client, 250)
#    assert r.status_code == 201
#    assert client.get("/accounts/ACC-1001").json()["balance"] == "750.00"
#    assert client.get("/accounts/ACC-1002").json()["balance"] == "750.00"


#def test_transfer_insufficient_funds(client):
 #   assert _transfer(client, 5000).status_code == 409


#def test_transfer_unknown_account(client):
#    assert _transfer(client, 10, dst="ACC-9999").status_code == 404


#def test_transfer_precision(client):
 #   for _ in range(10):
  #      assert _transfer(client, 0.10).status_code == 201
   # assert client.get("/accounts/ACC-1001").json()["balance"] == "999.00"
    #assert client.get("/accounts/ACC-1002").json()["balance"] == "501.00"


#def test_transfer_idempotency_key(client):
 #   first = _transfer(client, 100, key="retry-abc-123")
  #  second = _transfer(client, 100, key="retry-abc-123")
   # assert first.status_code == 201
    #assert second.json()["transfer_id"] == first.json()["transfer_id"]
    #assert client.get("/accounts/ACC-1001").json()["balance"] == "900.00"

#-------------------------------------------

# tests/test_transfers.py

import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, condecimal
from app.db import get_conn
import sqlite3

router = APIRouter()

class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: condecimal(gt=Decimal("0"))  # Pydantic validation rejects <= 0 (422 Unprocessable Entity)

@router.post("/transfers", status_code=201)
def create_transfer(
    payload: TransferRequest, 
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"), 
    conn: sqlite3.Connection = Depends(get_conn)
):
    if payload.from_account == payload.to_account:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account.")

    # Ensure idempotency storage exists (since it wasn't in conftest init_db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE
        )
    """)

    # 1. Idempotency Check
    if idempotency_key:
        existing = conn.execute(
            "SELECT id FROM transfers WHERE idempotency_key = ?", 
            (idempotency_key,)
        ).fetchone()
        if existing:
            return {"transfer_id": existing[0]}

    try:
        # SQLite implicit transactions begin on write, but BEGIN IMMEDIATE ensures a write lock
        conn.execute("BEGIN IMMEDIATE")

        src_row = conn.execute("SELECT balance FROM accounts WHERE id = ?", (payload.from_account,)).fetchone()
        dst_row = conn.execute("SELECT balance FROM accounts WHERE id = ?", (payload.to_account,)).fetchone()

        if not src_row or not dst_row:
            raise HTTPException(status_code=404, detail="Account not found.")

        # 2. Use Decimal math to eliminate float precision drift
        src_balance = Decimal(str(src_row[0]))
        dst_balance = Decimal(str(dst_row[0]))
        amount = Decimal(str(payload.amount))

        if src_balance < amount:
            raise HTTPException(status_code=409, detail="Insufficient funds.")

        new_src = src_balance - amount
        new_dst = dst_balance + amount
        transfer_id = str(uuid.uuid4())

        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (float(new_src), payload.from_account))
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (float(new_dst), payload.to_account))
        
        conn.execute(
            "INSERT INTO transfers (id, idempotency_key) VALUES (?, ?)", 
            (transfer_id, idempotency_key)
        )
        
        conn.commit()
        return {"transfer_id": transfer_id}
        
    except Exception as e:
        conn.rollback()
        raise e