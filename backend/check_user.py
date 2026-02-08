#!/usr/bin/env python3
"""
Script to check User and Customer record details.
Usage: python check_user.py <email>
"""

import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.customer import Customer
from app.db.models.user import User


async def check_user(email: str):
    """Check User and Customer records for an email."""
    
    async with AsyncSessionLocal() as db:
        # Find user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        # Find customer
        result = await db.execute(select(Customer).where(Customer.email == email))
        customer = result.scalar_one_or_none()
        
        print(f"\n{'='*60}")
        print(f"📧 Email: {email}")
        print(f"{'='*60}")
        
        if user:
            print(f"\n👤 USER RECORD:")
            print(f"   ID:          {user.id}")
            print(f"   Email:       {user.email}")
            print(f"   Name:        {user.first_name} {user.last_name}")
            print(f"   Role:        {user.role}")
            print(f"   Is Active:   {user.is_active}")
            print(f"   Is Verified: {user.is_verified}")
            print(f"   Tenant ID:   {user.tenant_id}")
            print(f"   Customer ID: {user.customer_id}")
        else:
            print(f"\n❌ NO USER RECORD FOUND")
        
        if customer:
            print(f"\n🏪 CUSTOMER RECORD:")
            print(f"   ID:          {customer.id}")
            print(f"   Email:       {customer.email}")
            print(f"   Name:        {customer.first_name} {customer.last_name}")
            print(f"   Tenant ID:   {customer.tenant_id}")
        else:
            print(f"\n❌ NO CUSTOMER RECORD FOUND")
        
        # Check for mismatches
        if user and customer:
            print(f"\n🔍 CONSISTENCY CHECK:")
            
            issues = []
            
            if user.customer_id != customer.id:
                issues.append(f"   ⚠️  User.customer_id ({user.customer_id}) != Customer.id ({customer.id})")
            
            if user.tenant_id != customer.tenant_id:
                issues.append(f"   ⚠️  User.tenant_id ({user.tenant_id}) != Customer.tenant_id ({customer.tenant_id})")
            
            if user.email != customer.email:
                issues.append(f"   ⚠️  User.email ({user.email}) != Customer.email ({customer.email})")
            
            if issues:
                print("   Issues found:")
                for issue in issues:
                    print(issue)
                
                # Offer to fix
                response = input("\nDo you want to sync User with Customer data? (y/n): ")
                if response.lower() == 'y':
                    user.customer_id = customer.id
                    user.tenant_id = customer.tenant_id
                    # Don't change email - that requires verification
                    await db.commit()
                    print("✅ User record synced with Customer!")
            else:
                print("   ✅ All records are consistent!")
        
        print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_user.py <email>")
        sys.exit(1)
    
    asyncio.run(check_user(sys.argv[1]))
