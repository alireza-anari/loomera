from django.utils.deconstruct import deconstructible

import logging
import os
from uuid import uuid4

from apps.accounts.services.sms import (
    create_random_code,
    create_state_token,
    mask_mobile_number,
    normalize_mobile_number,
    send_otp_sms,
)


# -------------------------------------------------------------------
# File Uploader
@deconstructible
class File_Uploader:
    def __init__(self, dir, prefix):
        self.dir = dir
        self.prefix = prefix

    def upload_to(self, instance, filename):
        filename, ext = os.path.splitext(filename)
        return f"{self.dir}/{self.prefix}/{uuid4()}{ext}"

    def __call__(self, instance, filename):
        return self.upload_to(instance, filename)


# -------------------------------------------------------------------
logger = logging.getLogger(__name__)


def send_sms(mobile_number, message):
    logger.warning(
        "Generic SMS sending is not supported anymore; use send_otp_sms instead | mobile=%s",
        mask_mobile_number(mobile_number),
    )
    return False
