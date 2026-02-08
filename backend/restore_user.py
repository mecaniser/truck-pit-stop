#!/usr/bin/env python3
"""
Script to restore a User account for an existing Customer record.
Usage: python restore_user.py <customer_email> <temporary_password>
"""

import asyncio
import sys
from uuid import UUID

# Add the app to the path
sys.path.insert(0, '.')

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.customer import Customer
from app.db.models.user import User, UserRole
from app.core.security import get_password_hash


async def restore_user(customer_email: str, temp_password: str):
    """Restore a User account for an existing Customer."""
    
    async with AsyncSessionLocal() as db:
        # Find the customer by email
        result = await db.execute(
            select(Customer).where(Customer.email == customer_email)
        )
        customer = result.scalar_one_or_none()
        
        if not customer:
            print(f"❌ No customer found with email: {customer_email}")
            return False
        
        # Check if a user already exists with this email
        result = await db.execute(
            select(User).where(User.email == customer_email)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"⚠️  A user already exists with email: {customer_email}")
            print(f"   User ID: {existing_user.id}")
            print(f"   Role: {existing_user.role}")
            print(f"   Is Active: {existing_user.is_active}")
            
            # Check if it's linked to this customer
            if existing_user.customer_id == customer.id:
                print(f"✅ User is already linked to the customer. No action needed.")
            else:
                print(f"⚠️  User is NOT linked to this customer (customer_id: {existing_user.customer_id})")
                print(f"   Customer ID: {customer.id}")
                
                # Offer to link them
                response = input("Do you want to link this user to the customer? (y/n): ")
                if response.lower() == 'y':
                    existing_user.customer_id = customer.id
                    await db.commit()
                    print(f"✅ User linked to customer successfully!")
            return True
        
        # Create new user for the customer
        print(f"\n📋 Customer found:")
        print(f"   ID: {customer.id}")
        print(f"   Name: {customer.first_name} {customer.last_name}")
        print(f"   Email: {customer.email}")
        print(f"   Tenant ID: {customer.tenant_id}")
        
        new_user = User(
            email=customer.email,
            hashed_password=get_password_hash(temp_password),
            first_name=customer.first_name,
            last_name=customer.last_name,
            phone=customer.phone,
            role=UserRole.CUSTOMER,
            is_active=True,
            is_verified=True,  # Skip verification since they had an account before
            tenant_id=customer.tenant_id,
            customer_id=customer.id,
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        print(f"\n✅ User account restored successfully!")
        print(f"   User ID: {new_user.id}")
        print(f"   Email: {new_user.email}")
        print(f"   Temporary Password: {temp_password}")
        print(f"\n⚠️  Please ask the user to change their password after logging in.")
        
        return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python restore_user.py <customer_email> <temporary_password>")
        print("Example: python restore_user.py john@example.com TempPass123!")
        sys.exit(1)
    
    customer_email = sys.argv[1]
    temp_password = sys.argv[2]
    
    print(f"\n🔧 Restoring user account for: {customer_email}\n")
    
    asyncio.run(restore_user(customer_email, temp_password))
