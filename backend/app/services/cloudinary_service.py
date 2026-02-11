"""
Cloudinary service for uploading work photos.
"""
import cloudinary
import cloudinary.uploader
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Configure Cloudinary
if settings.CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def is_cloudinary_configured() -> bool:
    """Check if Cloudinary is properly configured."""
    return bool(
        settings.CLOUDINARY_CLOUD_NAME
        and settings.CLOUDINARY_API_KEY
        and settings.CLOUDINARY_API_SECRET
    )


async def upload_work_photo(
    base64_image: str,
    repair_order_id: str,
    mechanic_id: str,
) -> str:
    """
    Upload a work photo to Cloudinary.
    
    Args:
        base64_image: Base64 encoded image data (with or without data URI prefix)
        repair_order_id: UUID of the repair order
        mechanic_id: UUID of the mechanic uploading
        
    Returns:
        Secure URL of the uploaded image
        
    Raises:
        ValueError: If Cloudinary is not configured
        Exception: If upload fails
    """
    if not is_cloudinary_configured():
        raise ValueError("Cloudinary is not configured. Please set CLOUDINARY_* environment variables.")
    
    try:
        # Upload to Cloudinary with folder organization
        result = cloudinary.uploader.upload(
            base64_image,
            folder=f"work_photos/{repair_order_id}",
            resource_type="image",
            # Optimize for web display
            transformation=[
                {"quality": "auto:good"},
                {"fetch_format": "auto"},
            ],
            # Add metadata
            context={
                "repair_order_id": repair_order_id,
                "mechanic_id": mechanic_id,
            },
        )
        
        logger.info(
            "Work photo uploaded",
            repair_order_id=repair_order_id,
            mechanic_id=mechanic_id,
            public_id=result.get("public_id"),
        )
        
        return result["secure_url"]
        
    except Exception as e:
        logger.error(
            "Failed to upload work photo",
            repair_order_id=repair_order_id,
            mechanic_id=mechanic_id,
            error=str(e),
        )
        raise


async def delete_work_photo(public_id: str) -> bool:
    """
    Delete a work photo from Cloudinary.
    
    Args:
        public_id: Cloudinary public ID of the image
        
    Returns:
        True if deleted successfully
    """
    if not is_cloudinary_configured():
        raise ValueError("Cloudinary is not configured.")
    
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception as e:
        logger.error("Failed to delete work photo", public_id=public_id, error=str(e))
        return False
