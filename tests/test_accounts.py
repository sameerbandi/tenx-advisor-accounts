# def test_get_account(client):
#     r = client.get("/accounts/ACC-1001")
#     assert r.status_code == 200
#     assert r.json()["client_name"] == "Client One"


# def test_get_account_not_found(client):
#     assert client.get("/accounts/ACC-9999").status_code == 404


# def test_positions_shape(client):
#     r = client.get("/accounts/ACC-1001/positions")
#     assert r.status_code == 200
#     positions = r.json()["positions"]
#     assert len(positions) == 6
#     assert positions[0] == {"fund_code": "FND-101", "fund_name": "Maple Canadian Equity",
#                             "units": "100.0000", "market_value": "2451.00"}


# def test_positions_query_count(client, query_log):
#     query_log.reset()
#     r = client.get("/accounts/ACC-1001/positions")
#     assert r.status_code == 200
#     assert len(query_log.selects()) <= 2, f"{len(query_log.selects())} SELECT statements for one request"

from fastapi import APIRouter, Depends, HTTPException
from app.db import get_conn
import sqlite3

router = APIRouter(prefix="/accounts")

@router.get("/{account_id}")
def get_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT name, balance FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Format to strictly two decimal places to pass string equality assertions
    return {"client_name": row[0], "balance": f"{row[1]:.2f}"}

@router.get("/{account_id}/positions")
def get_positions(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    # 3. Consolidate into a single JOIN to fix the N+1 query problem 
    query = """
        SELECT p.fund_code, f.name, p.units, f.price 
        FROM positions p
        JOIN funds f ON p.fund_code = f.code
        WHERE p.account_id = ?
    """
    rows = conn.execute(query, (account_id,)).fetchall()
    
    positions = []
    for row in rows:
        code, name, units, price = row[0], row[1], row[2], row[3]
        market_value = units * price
        
        positions.append({
            "fund_code": code,
            "fund_name": name,
            "units": f"{units:.4f}",
            "market_value": f"{market_value:.2f}"
        })
        
    return {"positions": positions}