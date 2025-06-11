from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime


class PaymentRequest(BaseModel):
    amount: int  # Amount in cents
    currency: str = "usd"
    description: Optional[str] = None
    customer_email: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

class PaymentResponse(BaseModel):
    payment_intent_id: str
    client_secret: str
    status: str
    amount: int
    currency: str

class RefundRequest(BaseModel):
    payment_intent_id: str
    amount: Optional[int] = None  # If None, refunds full amount
    reason: Optional[str] = None

class RefundResponse(BaseModel):
    refund_id: str
    status: str
    amount: int
    currency: str

class CustomerRequest(BaseModel):
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

class CustomerResponse(BaseModel):
    customer_id: str
    email: str
    name: Optional[str] = None
    created: datetime

class SubscriptionResponse(BaseModel):
    subscription_id: str
    customer_id: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    plan_id: str
    plan_name: Optional[str] = None
