import uuid
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from paystackapi.paystack import Paystack
from ..models.payments import Payment
from ..models.users import User
from ..extensions import db

bp = Blueprint("payments", __name__)


@bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate_payment():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    amount = data.get("amount")
    if not amount:
        return jsonify({"error": "Amount is required"}), 400

    # Paystack expects amount in kobo
    try:
        amount_kobo = int(float(amount) * 100)
    except ValueError:
        return jsonify({"error": "Invalid amount"}), 400

    email = user.email
    reference = str(uuid.uuid4())

    paystack_secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not paystack_secret:
        return jsonify({"error": "Paystack not configured"}), 500

    paystack = Paystack(secret_key=paystack_secret)

    try:
        response = paystack.transaction.initialize(
            reference=reference, amount=amount_kobo, email=email
        )

        if not response["status"]:
            return (
                jsonify(
                    {
                        "error": "Payment initialization failed",
                        "details": response.get("message"),
                    }
                ),
                400,
            )

        # Save pending payment
        payment = Payment(
            user_id=user.id,
            amount=int(float(amount)),  # Storing in main currency unit
            reference=reference,
            status="pending",
            type=data.get("type", "one-time"),
        )
        db.session.add(payment)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "reference": reference,
                        "authorization_url": response["data"]["authorization_url"],
                        "access_code": response["data"]["access_code"],
                    },
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/verify/<reference>", methods=["GET"])
@jwt_required()
def verify_payment(reference):
    paystack_secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not paystack_secret:
        return jsonify({"error": "Paystack not configured"}), 500

    payment = db.session.execute(
        db.select(Payment).filter_by(reference=reference)
    ).scalar_one_or_none()
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    paystack = Paystack(secret_key=paystack_secret)

    try:
        response = paystack.transaction.verify(reference=reference)

        if response["status"] and response["data"]["status"] == "success":
            payment.status = "success"
            db.session.commit()
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Payment verified",
                        "data": response["data"],
                    }
                ),
                200,
            )
        else:
            payment.status = "failed"
            db.session.commit()
            return (
                jsonify({"status": "failed", "message": "Payment verification failed"}),
                400,
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
