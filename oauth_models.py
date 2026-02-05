from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

# OAuth Session Models
class SessionData(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None
    session_token: str

class UserSession(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = datetime.now(timezone.utc)

# Stripe Payment Models
class PaymentTransaction(BaseModel):
    id: str
    user_id: str
    event_id: str
    session_id: str
    amount: float
    currency: str
    payment_status: str  # initiated, completed, failed, expired
    payment_provider: str  # stripe, iyzico, vakifbank
    metadata: dict
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)

class StripeCheckoutRequest(BaseModel):
    event_id: str
    package_type: str  # ticket type
    origin_url: str
