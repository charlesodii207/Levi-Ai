import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
BUCKET_NAME = "knowledge-base"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_file(file_bytes: bytes, file_path: str, content_type: str) -> str:
    """Upload file to Supabase storage and return the storage path."""
    supabase.storage.from_(BUCKET_NAME).upload(
        path=file_path,
        file=file_bytes,
        file_options={"content-type": content_type}
    )
    return file_path


def delete_file(file_path: str):
    """Delete a file from Supabase storage."""
    supabase.storage.from_(BUCKET_NAME).remove([file_path])


def get_file_url(file_path: str) -> str:
    """Get a signed URL for temporary file access."""
    response = supabase.storage.from_(BUCKET_NAME).create_signed_url(
        file_path, expires_in=3600
    )
    return response["signedURL"]


def download_file(file_path: str) -> bytes:
    """Download file bytes from Supabase storage."""
    return supabase.storage.from_(BUCKET_NAME).download(file_path)
