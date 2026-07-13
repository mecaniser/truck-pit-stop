from sqlalchemy import Column, String, ForeignKey, Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class DescriptionLibraryEntry(BaseModel):
    """AI-canonicalized suggestion text, one row per clean phrase.

    Regenerated in bulk by app/services/description_library_service.py from
    a tenant's raw historical text — repair order descriptions, service
    names, inventory part names, or inventory categories, distinguished by
    library_type. Replaces that tenant's (library_type) row set on each
    regeneration rather than being edited in place.
    """
    __tablename__ = "description_library_entries"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    # 'ro_description' | 'service_name' | 'part_name' | 'part_category'
    library_type = Column(String(30), nullable=False, default="ro_description")
    canonical_text = Column(Text, nullable=False)
    category = Column(String(100), nullable=True)
    source_count = Column(Integer, nullable=False, default=1)
    last_regenerated_at = Column(DateTime(timezone=True), nullable=True)
