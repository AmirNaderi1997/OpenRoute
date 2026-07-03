import hashlib
import hmac
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

NOWPAYMENTS_API_BASE = "https://api.nowpayments.io/v1"
TOMAN_TO_USD_RATE = 60000.0


def _json_headers() -> dict[str, str] | None:
    if not settings.NOWPAYMENTS_API_KEY:
        logger.error("NOWPayments API key is missing.")
        return None
    return {
        "x-api-key": settings.NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json",
    }


def verify_ipn_signature(payload: dict, received_signature: str | None) -> bool:
    if not settings.NOWPAYMENTS_IPN_SECRET or not received_signature:
        return False

    sorted_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    expected_signature = hmac.new(
        settings.NOWPAYMENTS_IPN_SECRET.encode(),
        sorted_payload.encode(),
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)


async def create_nowpayments_invoice(
    amount_toman: int,
    order_id: str,
    order_description: str | None = None,
    price_amount_usd: float | None = None,
    callback_url: str | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
    partially_paid_url: str | None = None,
) -> tuple[str | None, str | None]:
    headers = _json_headers()
    if not headers:
        return None, None

    amount_usd = round(float(price_amount_usd), 2) if price_amount_usd is not None else round(float(amount_toman) / TOMAN_TO_USD_RATE, 2)
    payload = {
        "price_amount": amount_usd,
        "price_currency": "usd",
        "order_id": order_id,
        "order_description": order_description or f"OpenRoute payment #{order_id}",
        "ipn_callback_url": callback_url or settings.NOWPAYMENTS_WEBHOOK_URL,
        "success_url": success_url or settings.NOWPAYMENTS_SUCCESS_URL,
        "cancel_url": cancel_url or settings.NOWPAYMENTS_CANCEL_URL,
        "partially_paid_url": partially_paid_url or settings.NOWPAYMENTS_PARTIAL_URL,
        "is_fixed_rate": True,
        "is_fee_paid_by_user": False,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{NOWPAYMENTS_API_BASE}/invoice",
                json=payload,
                headers=headers,
                timeout=20,
            )
        except Exception as exc:
            logger.error(f"NOWPayments invoice generation exception: {exc}")
            return None, None

    if response.status_code not in {200, 201}:
        logger.error(
            "NOWPayments invoice generation failed: %s - %s",
            response.status_code,
            response.text,
        )
        return None, None

    try:
        data = response.json()
    except Exception as exc:
        logger.error(f"NOWPayments invoice response parsing failed: {exc}")
        return None, None

    invoice_url = data.get("invoice_url")
    invoice_id = str(data.get("id")) if data.get("id") is not None else None
    return invoice_url, invoice_id


async def get_nowpayments_payment_status(payment_id: str | int) -> dict | None:
    headers = _json_headers()
    if not headers:
        return None

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{NOWPAYMENTS_API_BASE}/payment/{payment_id}",
                headers=headers,
                timeout=20,
            )
        except Exception as exc:
            logger.error(f"NOWPayments payment status exception: {exc}")
            return None

    if response.status_code != 200:
        logger.error(
            "NOWPayments payment status lookup failed: %s - %s",
            response.status_code,
            response.text,
        )
        return None

    try:
        return response.json()
    except Exception as exc:
        logger.error(f"NOWPayments status response parsing failed: {exc}")
        return None
