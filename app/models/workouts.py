from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY

from ..extensions import db


class Workout(db.Model):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    equipment: Mapped[Optional[str]] = mapped_column(Text)  # comma-separated
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    public_id: Mapped[Optional[str]] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(255), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    # generic reference that can point to either workouts.id or saved_workouts.id
    workout_id: Mapped[int] = mapped_column(Integer, nullable=False)


class PublicWorkout(db.Model):
    __tablename__ = "public_workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[Optional[str]] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    muscles: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    equipment: Mapped[Optional[str]] = mapped_column(Text)  # comma-separated
    description: Mapped[Optional[str]] = mapped_column(Text)
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    level: Mapped[Optional[str]] = mapped_column(String(50))


class SavedWorkout(db.Model):
    __tablename__ = "saved_workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    public_workout_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("public_workouts.id")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    equipment: Mapped[Optional[str]] = mapped_column(Text)  # comma-separated
    type: Mapped[Optional[str]] = mapped_column(String(120))
    muscles: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    level: Mapped[Optional[str]] = mapped_column(String(50))
