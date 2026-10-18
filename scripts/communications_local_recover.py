"""Bounded recovery for the isolated simulated inbox only; never retries held sends."""
import asyncio
from communications_local_app import sender  # Enforces isolated environment and blocks Twilio.
from app.db.session import AsyncSessionLocal
from app.services.communications_service import process_pending_operations

async def main():
    async with AsyncSessionLocal() as db:
        await process_pending_operations(db, sender, limit=50)
    print('Processed at most 50 pending simulated operations; dispatching/unknown sends were not retried.')

if __name__ == '__main__':
    asyncio.run(main())
