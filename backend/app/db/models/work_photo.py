"""
Work Photo model for storing mechanic-uploaded photos during repairs.
"""
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.db.base import BaseModel


class WorkPhoto(BaseModel):
    __tablename__ = "work_photos"
    
    repair_order_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("repair_orders.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    repair_order = relationship("RepairOrder", backref="work_photos")
    
    mechanic_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True,
        index=True
    )
    mechanic = relationship("User", backref="uploaded_work_photos")
    
    # Cloudinary URL
    image_url = Column(String(500), nullable=False)
    
    # Cloudinary public_id for deletion
    cloudinary_public_id = Column(String(255), nullable=True)
    
    # Optional caption/note
    caption = Column(String(500), nullable=True)
    
    # Timestamp
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
