from decimal import Decimal
from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: Decimal = Field(gt=Decimal("0"), decimal_places=2)


class TransferResponse(BaseModel):
    transfer_id: str
    from_balance: str
    to_balance: str


class TransactionItem(BaseModel):
    id: int
    type: str
    amount: str
    created_at: str


class TransactionListResponse(BaseModel):
    items: list[TransactionItem]
    next_cursor: str | None = None
