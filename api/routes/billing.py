"""Billing endpoints — Stripe checkout + credit management."""

import hashlib
import hmac
import json
import logging
import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

_STRIPE_API = "https://api.stripe.com/v1"

PACKAGES = {
    "starter": {"price_id": "price_1Tl1GLAKwWYZcStyToXGZjIz", "credits": 100},
    "pro":     {"price_id": "price_1Tl1GLAKwWYZcStyinXgJNjn", "credits": 500},
    "max":     {"price_id": "price_1Tl1GMAKwWYZcStyLls9zzP6", "credits": 1200},
}


class CheckoutRequest(BaseModel):
    package: str


@router.get("/credits")
def get_credits(username: str = Depends(get_current_user)):
    from src.utils.credit_storage import get_balance
    return {"username": username, "balance": get_balance(username)}


@router.post("/checkout")
def create_checkout(body: CheckoutRequest, username: str = Depends(get_current_user)):
    pkg = PACKAGES.get(body.package)
    if not pkg:
        raise HTTPException(status_code=400, detail=f"Unknown package: {body.package}")

    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    success_url = f"{frontend}/admin/billing?success=true&pkg={body.package}"
    cancel_url = f"{frontend}/admin/billing"

    with httpx.Client(timeout=15) as client:
        r = client.post(
            f"{_STRIPE_API}/checkout/sessions",
            auth=(secret, ""),
            data={
                "mode": "payment",
                "line_items[0][price]": pkg["price_id"],
                "line_items[0][quantity]": "1",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata[username]": username,
                "metadata[credits]": str(pkg["credits"]),
                "metadata[package]": body.package,
            },
        )

    if r.status_code != 200:
        logger.error("Stripe checkout error %s: %s", r.status_code, r.text)
        raise HTTPException(status_code=502, detail="Failed to create checkout session")

    return {"url": r.json()["url"]}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not _verify_webhook(payload, sig):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = json.loads(payload)
    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})
        username = meta.get("username")
        credits = int(meta.get("credits", 0))

        if username and credits > 0:
            try:
                from src.utils.credit_storage import add_credits
                new_balance = add_credits(username, credits)
                logger.info("Added %d credits to %s → balance %d", credits, username, new_balance)
            except Exception as e:
                # Return 200 so Stripe doesn't retry; log the failure
                logger.error("Failed to add credits for %s: %s", username, e)

    return {"ok": True}


def _verify_webhook(payload: bytes, sig_header: str) -> bool:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature check")
        return True
    try:
        parts = {k.strip(): v.strip() for item in sig_header.split(",") for k, v in [item.split("=", 1)]}
        timestamp = parts.get("t", "")
        v1 = parts.get("v1", "")
        if not timestamp or not v1:
            return False
        signed = f"{timestamp}.".encode() + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if abs(time.time() - int(timestamp)) > 300:
            return False
        return hmac.compare_digest(expected, v1)
    except Exception:
        return False
