from decimal import Decimal
import pytest
from app.db import connect


def _insert_tx(db_path, account_id, type_, amount, created_at, transfer_id=None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, ?, ?, ?, ?)",
        (account_id, type_, amount, created_at, transfer_id),
    )
    conn.commit()
    inserted_id = cur.lastrowid
    conn.close()
    return inserted_id


def test_transactions_empty(client):
    r = client.get("/accounts/ACC-1001/transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["next_cursor"] is None


def test_transactions_unknown_account(client):
    r = client.get("/accounts/ACC-9999/transactions")
    assert r.status_code == 404


def test_transactions_shape_and_newest_first(client, db_path):
    _insert_tx(db_path, "ACC-1001", "deposit", 100.0, "2026-08-10T10:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "withdrawal", 50.5, "2026-08-11T12:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "transfer_in", 200.0, "2026-08-12T14:00:00+00:00")

    r = client.get("/accounts/ACC-1001/transactions")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 3
    # Newest first
    assert data["items"][0]["type"] == "transfer_in"
    assert data["items"][0]["amount"] == "200.00"
    assert data["items"][0]["created_at"] == "2026-08-12T14:00:00+00:00"
    assert isinstance(data["items"][0]["id"], int)

    assert data["items"][1]["type"] == "withdrawal"
    assert data["items"][1]["amount"] == "50.50"

    assert data["items"][2]["type"] == "deposit"
    assert data["items"][2]["amount"] == "100.00"
    assert data["next_cursor"] is None


def test_transactions_filter_type(client, db_path):
    _insert_tx(db_path, "ACC-1001", "deposit", 100.0, "2026-08-10T10:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "withdrawal", 50.0, "2026-08-11T10:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "deposit", 75.0, "2026-08-12T10:00:00+00:00")

    r = client.get("/accounts/ACC-1001/transactions?type=deposit")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert all(i["type"] == "deposit" for i in items)


def test_transactions_filter_date_range(client, db_path):
    _insert_tx(db_path, "ACC-1001", "deposit", 10.0, "2026-08-01T10:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "deposit", 20.0, "2026-08-05T12:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "deposit", 30.0, "2026-08-10T14:00:00+00:00")
    _insert_tx(db_path, "ACC-1001", "deposit", 40.0, "2026-08-15T16:00:00+00:00")

    # Inclusive date filtering
    r = client.get("/accounts/ACC-1001/transactions?from=2026-08-05&to=2026-08-10")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert [i["amount"] for i in items] == ["30.00", "20.00"]


def test_transactions_invalid_type(client):
    r = client.get("/accounts/ACC-1001/transactions?type=invalid_type")
    assert r.status_code == 422


def test_transactions_invalid_date(client):
    r = client.get("/accounts/ACC-1001/transactions?from=2026-13-45")
    assert r.status_code == 422

    r = client.get("/accounts/ACC-1001/transactions?to=bad-date")
    assert r.status_code == 422


def test_transactions_from_after_to(client):
    r = client.get("/accounts/ACC-1001/transactions?from=2026-08-15&to=2026-08-10")
    assert r.status_code == 422


def test_transactions_invalid_limit(client):
    r = client.get("/accounts/ACC-1001/transactions?limit=0")
    assert r.status_code == 422

    r = client.get("/accounts/ACC-1001/transactions?limit=101")
    assert r.status_code == 422


def test_transactions_invalid_cursor(client):
    r = client.get("/accounts/ACC-1001/transactions?cursor=not-a-valid-cursor")
    assert r.status_code == 400


def test_transactions_pagination_and_resilience(client, db_path):
    # Insert 5 transactions
    for i in range(1, 6):
        _insert_tx(db_path, "ACC-1001", "deposit", float(i * 10), f"2026-08-0{i}T12:00:00+00:00")

    # Page 1 (limit=2)
    p1 = client.get("/accounts/ACC-1001/transactions?limit=2")
    assert p1.status_code == 200
    data1 = p1.json()
    assert len(data1["items"]) == 2
    assert [i["amount"] for i in data1["items"]] == ["50.00", "40.00"]
    cursor1 = data1["next_cursor"]
    assert cursor1 is not None

    # Simulate arrival of new transaction between page requests
    _insert_tx(db_path, "ACC-1001", "deposit", 999.0, "2026-08-06T12:00:00+00:00")

    # Page 2 using cursor1 (limit=2)
    p2 = client.get(f"/accounts/ACC-1001/transactions?limit=2&cursor={cursor1}")
    assert p2.status_code == 200
    data2 = p2.json()
    assert len(data2["items"]) == 2
    # Must seamlessly continue: 30.00 and 20.00 without repeating or skipping
    assert [i["amount"] for i in data2["items"]] == ["30.00", "20.00"]
    cursor2 = data2["next_cursor"]
    assert cursor2 is not None

    # Page 3 using cursor2 (limit=2)
    p3 = client.get(f"/accounts/ACC-1001/transactions?limit=2&cursor={cursor2}")
    assert p3.status_code == 200
    data3 = p3.json()
    assert len(data3["items"]) == 1
    assert [i["amount"] for i in data3["items"]] == ["10.00"]
    # Last page has null next_cursor
    assert data3["next_cursor"] is None


def test_transactions_created_by_transfers(client):
    r = client.post("/transfers", json={"from_account": "ACC-1001", "to_account": "ACC-1002", "amount": 250.0})
    assert r.status_code == 201

    tx_src = client.get("/accounts/ACC-1001/transactions").json()["items"]
    assert len(tx_src) == 1
    assert tx_src[0]["type"] == "transfer_out"
    assert tx_src[0]["amount"] == "250.00"

    tx_dst = client.get("/accounts/ACC-1002/transactions").json()["items"]
    assert len(tx_dst) == 1
    assert tx_dst[0]["type"] == "transfer_in"
    assert tx_dst[0]["amount"] == "250.00"
