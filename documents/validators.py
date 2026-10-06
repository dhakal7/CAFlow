import os
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_DOCUMENT_EXTENSIONS = {
    'pdf', 'xlsx', 'xls', 'csv', 'docx', 'doc',
    'png', 'jpg', 'jpeg', 'webp', 'txt', 'zip'
}

PROHIBITED_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'sh', 'php', 'py', 'js', 'html', 'htm',
    'vbs', 'jar', 'apk', 'dll', 'bin', 'msi', 'com', 'scr', 'pif'
}


def validate_document_file(file):
    """
    Validates uploaded document file type and size.
    Prevents executable uploads and oversized payloads.
    """
    if not file:
        raise ValidationError(_("No file was provided."))

    # 1. Validate size
    if file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            _(f"File size exceeds the allowed limit of {MAX_FILE_SIZE_MB} MB. "
              f"Current size is {round(file.size / (1024 * 1024), 2)} MB.")
        )

    # 2. Validate extension
    ext = os.path.splitext(file.name)[1].lstrip('.').lower()
    if not ext:
        raise ValidationError(_("File must have a valid extension (e.g. .pdf, .xlsx, .docx)."))

    if ext in PROHIBITED_EXTENSIONS:
        raise ValidationError(_(f"Files with extension '.{ext}' are prohibited for security reasons."))

    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        allowed_str = ", ".join(sorted(f".{e}" for e in ALLOWED_DOCUMENT_EXTENSIONS))
        raise ValidationError(_(f"Unsupported file format '.{ext}'. Allowed formats: {allowed_str}."))

    return file
