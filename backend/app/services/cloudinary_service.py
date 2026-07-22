from __future__ import annotations

"""
Cloudinary service for uploading work photos.
"""
import base64
import time

import cloudinary
import cloudinary.uploader
import cloudinary.utils
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


def create_direct_image_upload_signature(folder: str) -> dict[str, str | int]:
    """Return signed Cloudinary browser-upload parameters for one image."""
    if not is_cloudinary_configured():
        raise ValueError("Cloudinary is not configured. Please set CLOUDINARY_* environment variables.")

    timestamp = int(time.time())
    params = {
        "folder": folder,
        "timestamp": timestamp,
    }
    signature = cloudinary.utils.api_sign_request(params, settings.CLOUDINARY_API_SECRET)
    return {
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
        "api_key": settings.CLOUDINARY_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "folder": folder,
        "upload_url": f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload",
    }


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


async def upload_tenant_logo(
    *,
    image_bytes: bytes,
    tenant_id: str,
    content_type: str,
    source_url: str | None = None,
) -> str:
    """
    Upload a tenant logo image to Cloudinary and return the hosted URL.
    """
    if not is_cloudinary_configured():
        raise ValueError("Cloudinary is not configured. Please set CLOUDINARY_* environment variables.")

    base64_image = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{content_type};base64,{base64_image}"

    context = {"tenant_id": tenant_id}
    if source_url:
        context["source_url"] = source_url

    result = cloudinary.uploader.upload(
        data_uri,
        folder=f"tenant_logos/{tenant_id}",
        resource_type="image",
        transformation=[
            {"quality": "auto:good"},
            {"fetch_format": "auto"},
        ],
        context=context,
    )

    logger.info(
        "Tenant logo uploaded",
        tenant_id=tenant_id,
        public_id=result.get("public_id"),
        source_url=source_url,
    )

    return result["secure_url"]


async def upload_inventory_photo(
    data_uri: str,
    inventory_item_id: str,
) -> tuple[str, str]:
    """
    Upload an inventory part photo to Cloudinary.

    Returns:
        (secure_url, public_id) of the uploaded image

    Raises:
        ValueError: If Cloudinary is not configured
        Exception: If upload fails
    """
    if not is_cloudinary_configured():
        raise ValueError("Cloudinary is not configured. Please set CLOUDINARY_* environment variables.")

    try:
        result = cloudinary.uploader.upload(
            data_uri,
            folder=f"inventory_parts/{inventory_item_id}",
            resource_type="image",
            transformation=[
                {"quality": "auto:good"},
                {"fetch_format": "auto"},
            ],
            context={"inventory_item_id": inventory_item_id},
        )

        logger.info(
            "Inventory photo uploaded",
            inventory_item_id=inventory_item_id,
            public_id=result.get("public_id"),
        )

        return result["secure_url"], result["public_id"]

    except Exception as e:
        logger.error(
            "Failed to upload inventory photo",
            inventory_item_id=inventory_item_id,
            error=str(e),
        )
        raise


async def delete_cloudinary_image(public_id: str) -> bool:
    """
    Delete any Cloudinary image by public ID. Resource-agnostic — used for
    work photos, inventory photos, and any other feature storing a public_id.

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
        logger.error("Failed to delete Cloudinary image", public_id=public_id, error=str(e))
        return False


# Back-compat alias — existing callers reference this name.
delete_work_photo = delete_cloudinary_image
