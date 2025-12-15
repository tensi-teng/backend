from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..extensions import db


class Payment(db.Model):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="NGN")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    type: Mapped[str] = mapped_column(String(50), default="subscription")
    paid_at = mapped_column(server_default=func.now())
