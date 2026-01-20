from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class Task(BaseModel):
    input_data: Dict[str, Any]

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None

class RagisterRequest(BaseModel):
    user_id: str
    user_name: str

class TransactionRequest(BaseModel):
    user_id: str
    asset_type: str  # equity, mutual_fund, property, etc.
    transaction_type: str  # buy, sell
    purchase_date: datetime
    purchase_price: float
    quantity: float
    asset_name: str
    sale_date: Optional[datetime] = None
    sale_price: Optional[float] = None
    notes: Optional[str] = None
