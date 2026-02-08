#!/usr/bin/env python3
"""
Script to fully fix a User account - sync with Customer and set verified/active.
Usage: python fix_user.py <email> [new_password]
"""

import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.customer import Customer
from app.db.models.user import User
from app.core.security import get_password_hash


async def fix_user(email: str, new_password: str = None):
    """Fully fix a User account."""
    
    async with AsyncSessionLocal() as db:
        # Find user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        # Find customer
        result = await db.execute(select(Customer).where(Customer.email == email))
        customer = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ No user found with email: {email}")
            return
        
        print(f"\n📋 BEFORE FIX:")
        print(f"   User ID:       {user.id}")
        print(f"   Email:         {user.email}")
        print(f"   Is Active:     {user.is_active}")
        print(f"   Is Verified:   {user.is_verified}")
        print(f"   Tenant ID:     {user.tenant_id}")
        print(f"   Customer ID:   {user.customer_id}")
        
        # Apply fixes
        changes = []
        
        # Set verified and active
        if not user.is_verified:
            user.is_verified = True
            changes.append("Set is_verified = True")
        
        if not user.is_active:
            user.is_active = True
            changes.append("Set is_active = True")
        
        # Sync with customer if exists
        if customer:
            if user.customer_id != customer.id:
                user.customer_id = customer.id
                changes.append(f"Set customer_id = {customer.id}")
            
            if user.tenant_id != customer.tenant_id:
                user.tenant_id = customer.tenant_id
                changes.append(f"Set tenant_id = {customer.tenant_id}")
        
        # Reset password if provided
        if new_password:
            user.hashed_password = get_password_hash(new_password)
            changes.append(f"Reset password to: {new_password}")
        
        if changes:
            await db.commit()
            await db.refresh(user)
            
            print(f"\n✅ CHANGES APPLIED:")
            for change in changes:
                print(f"   - {change}")
            
            print(f"\n📋 AFTER FIX:")
            print(f"   User ID:       {user.id}")
            print(f"   Email:         {user.email}")
            print(f"   Is Active:     {user.is_active}")
            print(f"   Is Verified:   {user.is_verified}")
            print(f"   Tenant ID:     {user.tenant_id}")
            print(f"   Customer ID:   {user.customer_id}")
        else:
            print(f"\n✅ No changes needed - user is already correctly configured.")
        
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_user.py <email> [new_password]")
        print("Example: python fix_user.py john@example.com")
        print("Example: python fix_user.py john@example.com NewPass123!")
        sys.exit(1)
    
    email = sys.argv[1]
    new_password = sys.argv[2] if len(sys.argv) > 2 else None
    
    asyncio.run(fix_user(email, new_password))
