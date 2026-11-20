"""Validation helpers for uploaded medical documents."""
from pathlib import Path
import zipfile

from django.core.exceptions import ValidationError


MAX_MEDICAL_DOCUMENT_SIZE = 10 * 1024 * 1024
ALLOWED_MEDICAL_DOCUMENT_EXTENSIONS = (
    '.pdf',
    '.doc',
    '.docx',
    '.jpg',
    '.jpeg',
    '.png',
)


def validate_medical_document(uploaded_file):
    """Validate the size, extension, and file signature of a medical document."""
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_MEDICAL_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            'Unsupported file type. Upload a PDF, DOC, DOCX, JPG, JPEG, or PNG file.'
        )

    if uploaded_file.size > MAX_MEDICAL_DOCUMENT_SIZE:
        raise ValidationError('The file must not exceed 10 MB.')

    uploaded_file.seek(0)
    signature = uploaded_file.read(8)
    uploaded_file.seek(0)

    valid_signature = {
        '.pdf': signature.startswith(b'%PDF-'),
        '.doc': signature.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'),
        '.jpg': signature.startswith(b'\xff\xd8\xff'),
        '.jpeg': signature.startswith(b'\xff\xd8\xff'),
        '.png': signature.startswith(b'\x89PNG\r\n\x1a\n'),
    }

    if extension == '.docx':
        try:
            with zipfile.ZipFile(uploaded_file) as document:
                names = set(document.namelist())
        except zipfile.BadZipFile:
            names = set()
        finally:
            uploaded_file.seek(0)
        is_valid = {
            '[Content_Types].xml',
            'word/document.xml',
        }.issubset(names)
    else:
        is_valid = valid_signature[extension]

    if not is_valid:
        raise ValidationError(
            'The uploaded file content does not match its file type.'
        )

    return uploaded_file
