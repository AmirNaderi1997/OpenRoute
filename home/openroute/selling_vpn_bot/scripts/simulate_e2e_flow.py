import asyncio
from datetime import datetime

# A complete End-to-End Simulation of the purchase pipeline
# Assumes the FastAPI web server is running locally on port 8000

API_BASE = "http://localhost:8000/api/v1"
ADMIN_TOKEN = "SIMULATION_ADMIN_AUTH"  # We'll mock this or simulate directly in the DB

async def simulate_e2e():
    print("==========================================")
    print("   Starting E2E Payment & VPN Lifecycle   ")
    print("==========================================")
    
    from app.db.database import async_session_maker
    from app.db.models import User, SshServer, Payment, SshAccount
    
    async with async_session_maker() as session:
        print("[1] Offering: Creating Mock User and VPS Server in DB...")
        
        # 1. Create Mock User
        import random
        random_id = random.randint(1000000000, 9999999999)
        user = User(id=random_id, username="e2e_tester")
        session.add(user)
        
        # 2. Create Mock Server
        server = SshServer(
            name="E2E Simulation Node",
            ip_address="127.0.0.1", # Point to localhost for testing without connecting out
            ssh_port=22,
            root_password="mock",
            status="active"
        )
        session.add(server)
        await session.flush()
        
        print("[2] Payment: User submits Card Transfer (Pending)...")
        # 3. Create Pending Payment
        payment = Payment(
            user_id=user.id,
            server_id=server.id,
            amount=50000,
            payment_method="card_to_card",
            card_last_four="1234",
            status="pending"
        )
        session.add(payment)
        await session.commit()
        
        payment_id = payment.id
        user_id = user.id
        
        print(f"    -> Payment #{payment_id} created in 'pending' state.")
        
    print("[3] Admin: Simulating Admin clicking 'Approve & Activate'...")
    # For a true simulation, we can call the execution pipeline directly 
    # to avoid needing a valid FastAPI HTTP token in the test context
    
    from app.services.payment_pipeline import execute_payment_approval
    
    # This will attempt to SSH into 127.0.0.1. It will likely fail unless ssh server is running,
    # but the pipeline logic will execute and we can observe the status transition.
    
    print(f"    -> Invoking payment_pipeline.execute_payment_approval({payment_id})...")
    success = await execute_payment_approval(payment_id)
    
    print("[4] Verification: Checking database state...")
    async with async_session_maker() as session:
        updated_payment = await session.get(Payment, payment_id)
        print(f"    -> Payment Status is now: {updated_payment.status}")
        
        if updated_payment.status == "completed":
            print("✅ Simulation PASS: Payment moved to 'completed'.")
        elif updated_payment.status == "failed":
            print("❌ Simulation FAIL: Payment was rejected.")
        else:
            print(f"⚠️ Simulation Result: Payment stayed in {updated_payment.status}. (Note: If SSH failed, this is expected).")
            
        # Cleanup
        print("[*] Cleaning up database...")
        # Check if an account was created
        from app.db.models import SshAccount
        from sqlalchemy import select
        accounts = await session.scalars(select(SshAccount).where(SshAccount.user_id == user_id))
        for acc in accounts:
            await session.delete(acc)
        await session.delete(updated_payment)
        await session.flush()
        
        server_to_delete = await session.get(SshServer, updated_payment.server_id)
        if server_to_delete:
            await session.delete(server_to_delete)
        user_to_delete = await session.get(User, user_id)
        if user_to_delete:
            await session.delete(user_to_delete)
        await session.commit()
        
    print("==========================================")
    print("   Simulation Cycle Complete!             ")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(simulate_e2e())
