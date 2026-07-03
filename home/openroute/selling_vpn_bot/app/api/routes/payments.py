from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

from app.db.database import async_session_maker
from app.db.models import Payment
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CardVerifyRequest(BaseModel):
    payment_id: int
    card_last_four: str


@router.post("/card/verify")
async def verify_card_payment(req: CardVerifyRequest) -> Dict[str, Any]:
    async with async_session_maker() as session:
        payment = await session.get(Payment, req.payment_id)
        if not payment or payment.status != "pending":
            raise HTTPException(status_code=400, detail="Invalid payment record")

        if payment.card_last_four == req.card_last_four:
            payment.status = "completed"
            await session.commit()
            return {"status": "success", "message": "Payment verified"}

        payment.status = "failed"
        await session.commit()
        raise HTTPException(
            status_code=400,
            detail="اطلاعات پرداخت شما نامتعبر می باشد. درصورت خطا لطفا با پشتیبانی تماس بگیرید."
        )
