from datetime import datetime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import func
from .extensions import db


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    reg_number = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    gestures = db.relationship("Gesture", backref="user", cascade="all, delete-orphan")
    workouts = db.relationship("Workout", backref="user", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="user", cascade="all, delete-orphan")
    reminders = db.relationship(
        "Reminder", backref="user", cascade="all, delete-orphan"
    )


class Gesture(db.Model):
    __tablename__ = "gestures"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class Workout(db.Model):
    __tablename__ = "workouts"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    equipment = db.Column(db.Text)  # comma-separated
    image_url = db.Column(db.Text)
    public_id = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # checklist items are stored in a generic table that can point to
    # either created workouts or saved workouts (no FK for flexibility)


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(255), nullable=False)
    done = db.Column(db.Boolean, default=False)
    workout_id = db.Column(db.Integer, nullable=False)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), default="NGN")
    status = db.Column(db.String(50), default="pending")
    type = db.Column(db.String(50), default="subscription")
    paid_at = db.Column(db.DateTime, server_default=func.now())


class PublicWorkout(db.Model):
    __tablename__ = "public_workouts"
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(120))
    name = db.Column(db.String(255), nullable=False)
    muscles = db.Column(ARRAY(db.String), default=list)
    equipment = db.Column(db.Text)  # comma-separated
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)
    level = db.Column(db.String(50))


class SavedWorkout(db.Model):
    __tablename__ = "saved_workouts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    public_workout_id = db.Column(db.Integer, db.ForeignKey("public_workouts.id"))
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    equipment = db.Column(db.Text)  # comma-separated
    type = db.Column(db.String(120))
    muscles = db.Column(ARRAY(db.String), default=list)
    level = db.Column(db.String(50))


class Reminder(db.Model):
    __tablename__ = "reminders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    time = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
