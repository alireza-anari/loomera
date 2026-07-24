from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import MediaProcessingJob

ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_upload_file(file_obj, *, allowed_mime_types=None, max_size_mb=None):
    max_size_mb = max_size_mb or getattr(settings, "LOOMERA_MAX_UPLOAD_SIZE_MB", 8)
    max_size = int(max_size_mb) * 1024 * 1024
    size = getattr(file_obj, "size", 0) or 0
    if size > max_size:
        return False, f"حجم فایل نباید بیشتر از {max_size_mb} مگابایت باشد."
    mime_type = getattr(file_obj, "content_type", "") or mimetypes.guess_type(getattr(file_obj, "name", ""))[0] or ""
    if allowed_mime_types and mime_type not in set(allowed_mime_types):
        return False, "نوع فایل مجاز نیست."
    return True, ""


def enqueue_media_processing(*, file_obj, target=None, file_kind=MediaProcessingJob.FileKind.OTHER, created_by=None):
    from django.contrib.contenttypes.models import ContentType

    content_type = None
    object_id = None
    if target is not None:
        content_type = ContentType.objects.get_for_model(target, for_concrete_model=False)
        object_id = getattr(target, "pk", None)
    mime_type = getattr(file_obj, "content_type", "") or mimetypes.guess_type(getattr(file_obj, "name", ""))[0] or ""
    job = MediaProcessingJob.objects.create(
        target_content_type=content_type,
        target_object_id=object_id,
        source_file=file_obj,
        file_kind=file_kind,
        mime_type=mime_type,
        size_bytes=getattr(file_obj, "size", 0) or 0,
        created_by=created_by,
    )
    return job


def _save_image_derivative(job, image, *, width, suffix, field_name, format="WEBP"):
    from io import BytesIO

    img = image.copy()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if img.width > width:
        ratio = width / float(img.width)
        height = max(int(img.height * ratio), 1)
        img = img.resize((width, height))
    buffer = BytesIO()
    save_kwargs = {"quality": getattr(settings, "LOOMERA_IMAGE_WEBP_QUALITY", 82)} if format == "WEBP" else {}
    img.save(buffer, format=format, **save_kwargs)
    source_name = Path(job.source_file.name).stem
    name = f"{source_name}-{suffix}.webp"
    getattr(job, field_name).save(name, ContentFile(buffer.getvalue()), save=False)


def process_media_job(job: MediaProcessingJob):
    job.status = MediaProcessingJob.Status.PROCESSING
    job.attempts += 1
    job.save(update_fields=["status", "attempts", "updated_at"])
    try:
        if job.mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            job.status = MediaProcessingJob.Status.SKIPPED
            job.processed_at = timezone.now()
            job.metadata = {**(job.metadata or {}), "reason": "unsupported_mime_type"}
            job.save(update_fields=["status", "processed_at", "metadata", "updated_at"])
            return job

        from PIL import Image, ImageOps

        job.source_file.open("rb")
        with Image.open(job.source_file) as img:
            img = ImageOps.exif_transpose(img)
            _save_image_derivative(
                job,
                img,
                width=getattr(settings, "LOOMERA_IMAGE_MAX_WIDTH", 1920),
                suffix="optimized",
                field_name="processed_file",
            )
            _save_image_derivative(
                job,
                img,
                width=getattr(settings, "LOOMERA_IMAGE_THUMBNAIL_WIDTH", 640),
                suffix="thumb",
                field_name="thumbnail_file",
            )
        job.status = MediaProcessingJob.Status.COMPLETED
        job.processed_at = timezone.now()
        job.error_message = ""
        job.save(update_fields=["processed_file", "thumbnail_file", "status", "processed_at", "error_message", "updated_at"])
        return job
    except Exception as exc:
        job.status = MediaProcessingJob.Status.FAILED
        job.error_message = f"{exc.__class__.__name__}: {exc}"
        job.save(update_fields=["status", "error_message", "updated_at"])
        return job


def process_pending_media_jobs(*, limit=25):
    jobs = list(MediaProcessingJob.objects.filter(status=MediaProcessingJob.Status.PENDING).order_by("created_at")[:limit])
    for job in jobs:
        process_media_job(job)
    return jobs
