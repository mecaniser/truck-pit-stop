"""Shared upload-image validation, extracted from the fleet incident photo
flow so other features (e.g. inventory part photos) can reuse the same
content-type/size checks instead of importing a module-private helper.
"""
import base64

from fastapi import HTTPException, UploadFile, status

ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


async def read_validated_image(image: UploadFile) -> tuple[str, str]:
    """Validate an uploaded image and return (data_uri, content_type)."""
    content_type = (image.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a JPEG, PNG, WebP, HEIC, or HEIF image")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large. Max 10MB")
    data_uri = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    return data_uri, content_type
