#!/usr/bin/env python3
"""
Script to create a User account for an existing Customer (or create both if needed).
Usage: python create_user_for_customer.py <email> <password>
"""

import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.customer import Customer
from app.db.models.user import User, UserRole
from app.core.security import get_password_hash


async def create_user_for_customer(email: str, password: str):
    """Create a User account for an existing Customer."""
    
    async with AsyncSessionLocal() as db:
        # Check if user already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"✅ User already exists with email: {email}")
            print(f"   User ID: {existing_user.id}")
            print(f"   Role: {existing_user.role}")
            print(f"   Is Active: {existing_user.is_active}")
            print(f"   Is Verified: {existing_user.is_verified}")
            return
        
        # Find customer by email
        result = await db.execute(select(Customer).where(Customer.email == email))
        customer = result.scalar_one_or_none()
        
        if customer:
            print(f"\n📋 Customer found:")
            print(f"   ID: {customer.id}")
            print(f"   Name: {customer.first_name} {customer.last_name}")
            print(f"   Email: {customer.email}")
            print(f"   Tenant ID: {customer.tenant_id}")
            
            # Create user linked to customer
            new_user = User(
                email=customer.email,
                hashed_password=get_password_hash(password),
                first_name=customer.first_name,
                last_name=customer.last_name,
                phone=customer.phone,
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
                tenant_id=customer.tenant_id,
                customer_id=customer.id,
            )
        else:
            print(f"\n⚠️  No customer found with email: {email}")
            print(f"   Creating a standalone user account...")
            
            # Get first name and last name from email or prompt
            name_parts = email.split('@')[0].split('.')
            first_name = name_parts[0].capitalize() if name_parts else "User"
            last_name = name_parts[1].capitalize() if len(name_parts) > 1 else ""
            
            new_user = User(
                email=email,
                hashed_password=get_password_hash(password),
                first_name=first_name,
                last_name=last_name,
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
                tenant_id=None,  # No tenant - will need to be set manually
                customer_id=None,
            )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        print(f"\n✅ User account created successfully!")
        print(f"   User ID: {new_user.id}")
        print(f"   Email: {new_user.email}")
        print(f"   Name: {new_user.first_name} {new_user.last_name}")
        print(f"   Role: {new_user.role}")
        print(f"   Tenant ID: {new_user.tenant_id}")
        print(f"   Customer ID: {new_user.customer_id}")
        print(f"   Password: {password}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_user_for_customer.py <email> <password>")
        print("Example: python create_user_for_customer.py john@example.com MyPass123!")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    print(f"\n🔧 Creating user account for: {email}\n")
    
    asyncio.run(create_user_for_customer(email, password))
