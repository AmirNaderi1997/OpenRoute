import asyncio
from app.services.payment_pipeline import execute_payment_approval

async def main():
    result = await execute_payment_approval(3)
    print(result)

asyncio.run(main())
