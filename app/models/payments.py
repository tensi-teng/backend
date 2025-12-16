from datetime import datetime
from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ..extensions import db

class Payment(db.Model):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="NGN")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    type: Mapped[str] = mapped_column(String(50), default="subscription")
    paid_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
