import sqlite3
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_conn

router = APIRouter()


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
