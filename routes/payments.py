from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

blueprint = Blueprint("payments", __name__)

# ---------------- PAYSTACK PAYMENT WEBHOOK ----------------
#endpoint to initiate payment webhook handling


