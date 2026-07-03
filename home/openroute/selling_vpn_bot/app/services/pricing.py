from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import DiscountCode
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY

PLAN_DEFINITIONS = {
    101: {
        "service_type": ACCOUNT_TYPE_SSH,
        "title": "OpenRoute England (1 User) 1Month",
        "price_toman": 600000,
        "price_usd": 6.0,
        "max_connections": 1,
        "data_limit_gb": None,
        "volume_label": "Unlimited",
    },
    102: {
        "service_type": ACCOUNT_TYPE_SSH,
        "title": "OpenRoute England (2 Users) 1Month",
        "price_toman": 800000,
        "price_usd": 8.0,
        "max_connections": 2,
        "data_limit_gb": None,
        "volume_label": "Unlimited",
    },
    1: {
        "service_type": ACCOUNT_TYPE_V2RAY,
        "title": "BNETS PRO (5GB) 1Month",
        "price_toman": 98000,
        "price_usd": 1.0,
        "max_connections": 1,
        "data_limit_gb": 5,
        "volume_label": "5GB",
    },
    2: {
        "service_type": ACCOUNT_TYPE_V2RAY,
        "title": "BNETS PRO (10GB) 1Month",
        "price_toman": 188000,
        "price_usd": 2.0,
        "max_connections": 1,
        "data_limit_gb": 10,
        "volume_label": "10GB",
    },
    3: {
        "service_type": ACCOUNT_TYPE_V2RAY,
        "title": "BNETS PRO (20GB) 1Month",
        "price_toman": 268000,
        "price_usd": 3.0,
        "max_connections": 2,
        "data_limit_gb": 20,
        "volume_label": "20GB",
    },
    4: {
        "service_type": ACCOUNT_TYPE_V2RAY,
        "title": "BNETS PRO (30GB) 1Month",
        "price_toman": 358000,
        "price_usd": 4.0,
        "max_connections": 2,
        "data_limit_gb": 30,
        "volume_label": "30GB",
    },
    5: {
        "service_type": ACCOUNT_TYPE_V2RAY,
        "title": "BNETS PRO (50GB) 1Month",
        "price_toman": 498000,
        "price_usd": 5.0,
        "max_connections": 3,
        "data_limit_gb": 50,
        "volume_label": "50GB",
    },
    6: {
        "service_type": ACCOUNT_TYPE_V2RAY,
        "title": "BNETS PRO (100GB) 1Month",
        "price_toman": 698000,
        "price_usd": 7.0,
        "max_connections": 4,
        "data_limit_gb": 100,
        "volume_label": "100GB",
    },
}

PLAN_PRICES_TOMAN = {plan_id: int(plan["price_toman"]) for plan_id, plan in PLAN_DEFINITIONS.items()}
PLAN_PRICES_USD = {plan_id: float(plan["price_usd"]) for plan_id, plan in PLAN_DEFINITIONS.items()}

DISCOUNT_SCOPE_ALL = "all"
DISCOUNT_SCOPE_CARD = "card_to_card"
DISCOUNT_SCOPE_CRYPTO = "crypto"
DISCOUNT_SCOPE_WALLET = "wallet"


def get_plan_price_toman(plan_id: int) -> int:
    return int(PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["price_toman"])


def get_plan_price_usd(plan_id: int) -> float:
    return float(PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["price_usd"])


def get_plan_title(plan_id: int) -> str:
    return str(PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["title"])


def get_plan_service_type(plan_id: int) -> str:
    return str(PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["service_type"])


def get_plan_max_connections(plan_id: int) -> int:
    return int(PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["max_connections"])


def get_plan_data_limit_gb(plan_id: int) -> int | None:
    return PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["data_limit_gb"]


def get_plan_volume_label(plan_id: int) -> str:
    return str(PLAN_DEFINITIONS.get(plan_id, PLAN_DEFINITIONS[1])["volume_label"])


def get_service_plans(service_type: str) -> list[dict]:
    return [
        {"id": plan_id, **plan}
        for plan_id, plan in PLAN_DEFINITIONS.items()
        if plan["service_type"] == service_type
    ]


def normalize_discount_code(code: str | None) -> str | None:
    if not code:
        return None
    normalized = code.strip().upper()
    return normalized or None


def normalize_discount_payment_method(method: str | None) -> str | None:
    if not method:
        return None
    normalized = method.strip().lower()
    aliases = {
        "all": DISCOUNT_SCOPE_ALL,
        "card": DISCOUNT_SCOPE_CARD,
        "card_to_card": DISCOUNT_SCOPE_CARD,
        "crypto": DISCOUNT_SCOPE_CRYPTO,
        "wallet": DISCOUNT_SCOPE_WALLET,
    }
    return aliases.get(normalized)


def discount_scope_label(scope: str | None) -> str:
    normalized = normalize_discount_payment_method(scope) or DISCOUNT_SCOPE_ALL
    labels = {
        DISCOUNT_SCOPE_ALL: "همه روش‌ها",
        DISCOUNT_SCOPE_CARD: "کارت به کارت",
        DISCOUNT_SCOPE_CRYPTO: "رمزارز",
        DISCOUNT_SCOPE_WALLET: "کیف پول",
    }
    return labels.get(normalized, normalized)


def apply_percent_discount_toman(amount: int, percent_off: int) -> int:
    return max(0, int(round(amount * (100 - percent_off) / 100)))


def apply_percent_discount_usd(amount: float, percent_off: int) -> float:
    return max(0.0, round(amount * (100 - percent_off) / 100, 2))


def _validate_discount_code_record(
    discount: DiscountCode | None,
    payment_method: str | None = None,
) -> tuple[bool, str]:
    if not discount or not discount.is_active:
        return False, "invalid_or_inactive"
    if bool(discount.is_used):
        return False, "already_used"

    normalized_method = normalize_discount_payment_method(payment_method)
    normalized_scope = normalize_discount_payment_method(discount.payment_method_scope) or DISCOUNT_SCOPE_ALL
    if normalized_method and normalized_scope not in (DISCOUNT_SCOPE_ALL, normalized_method):
        return False, "scope_mismatch"

    return True, "ok"


async def get_active_discount_code(session, code: str | None, payment_method: str | None = None) -> DiscountCode | None:
    normalized = normalize_discount_code(code)
    if not normalized:
        return None

    discount = await session.scalar(
        select(DiscountCode).where(
            DiscountCode.code == normalized,
        )
    )
    is_valid, _ = _validate_discount_code_record(discount, payment_method)
    return discount if is_valid else None


def discount_failure_message(failure_reason: str | None) -> str:
    if failure_reason == "already_used":
        return "این کد تخفیف قبلاً استفاده شده است."
    if failure_reason == "scope_mismatch":
        return "این کد تخفیف برای این روش پرداخت معتبر نیست."
    return "کد تخفیف معتبر یا فعال نیست."


async def get_discount_preview(
    session,
    *,
    original_toman: int | None = None,
    original_usd: float | None = None,
    discount_code: str | None = None,
    payment_method: str | None = None,
) -> dict[str, int | float | str | bool | None]:
    normalized = normalize_discount_code(discount_code)
    preview: dict[str, int | float | str | bool | None] = {
        "discount_code": normalized,
        "discount_applied": False,
        "percent_off": 0,
        "payment_method_scope": None,
        "failure_reason": None,
        "original_toman": original_toman,
        "original_usd": original_usd,
        "payable_toman": original_toman,
        "payable_usd": original_usd,
    }
    if not normalized:
        return preview

    discount = await session.scalar(select(DiscountCode).where(DiscountCode.code == normalized))
    is_valid, failure_reason = _validate_discount_code_record(discount, payment_method)
    if not is_valid:
        preview["failure_reason"] = failure_reason
        return preview

    preview["discount_applied"] = True
    preview["percent_off"] = discount.percent_off
    preview["payment_method_scope"] = normalize_discount_payment_method(discount.payment_method_scope) or DISCOUNT_SCOPE_ALL
    if original_toman is not None:
        preview["payable_toman"] = apply_percent_discount_toman(original_toman, discount.percent_off)
    if original_usd is not None:
        preview["payable_usd"] = apply_percent_discount_usd(original_usd, discount.percent_off)
    return preview


async def mark_discount_code_as_used(
    session,
    code: str | None,
    *,
    user_id: int | None = None,
    payment_id: int | None = None,
) -> bool:
    normalized = normalize_discount_code(code)
    if not normalized:
        return False

    discount = await session.scalar(select(DiscountCode).where(DiscountCode.code == normalized))
    if not discount:
        return False
    if discount.is_used and discount.used_payment_id == payment_id:
        return True
    if discount.is_used:
        return False

    discount.is_used = True
    discount.used_by_user_id = user_id
    discount.used_payment_id = payment_id
    discount.used_at = datetime.now(timezone.utc)
    return True


def encode_payment_metadata(
    base_ref: str | None,
    *,
    payable_toman: int | None = None,
    payable_usd: float | None = None,
    discount_code: str | None = None,
) -> str | None:
    if not base_ref:
        return None

    parts = [base_ref]
    if payable_toman is not None:
        parts.append(f"payable_toman={int(payable_toman)}")
    if payable_usd is not None:
        parts.append(f"payable_usd={payable_usd:.2f}")
    if discount_code:
        parts.append(f"discount={normalize_discount_code(discount_code)}")
    return "|".join(parts)


def decode_payment_metadata(value: str | None) -> dict[str, str | int | float | bool | None]:
    result: dict[str, str | int | float | bool | None] = {
        "base_ref": value,
        "payable_toman": None,
        "payable_usd": None,
        "discount_code": None,
        "discount_applied": False,
    }
    if not value:
        return result

    parts = value.split("|")
    result["base_ref"] = parts[0]
    for item in parts[1:]:
        if "=" not in item:
            continue
        key, raw_val = item.split("=", 1)
        if key == "payable_toman":
            try:
                result["payable_toman"] = int(raw_val)
            except ValueError:
                pass
        elif key == "payable_usd":
            try:
                result["payable_usd"] = float(raw_val)
            except ValueError:
                pass
        elif key == "discount":
            result["discount_code"] = raw_val
            result["discount_applied"] = True

    return result
