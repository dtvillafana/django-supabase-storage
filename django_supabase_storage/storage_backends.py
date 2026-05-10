"""
Supabase Storage Backend for Django

This backend uploads ALL files directly to Supabase buckets ONLY.
No files are ever stored locally - everything goes to Supabase.
"""

import logging
import mimetypes
from io import BytesIO
from django.contrib.staticfiles.storage import ManifestFilesMixin
from django.core.files.storage import Storage
from django.conf import settings

try:
    from supabase import create_client
except ImportError:
    create_client = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SupabaseStorage(Storage):
    """
    Supabase S3 Storage Backend
    
    ALL files are uploaded DIRECTLY to Supabase Storage buckets.
    NO files are stored locally - ever.
    
    Required Settings:
        SUPABASE_URL - Your Supabase project URL
        SUPABASE_KEY - Your Supabase public API key (anon)
        SUPABASE_BUCKET - The bucket name (e.g., 'media', 'static')
    """
    folder_path=''

    def _build_storage_path(self, name):
        """Build a bucket-relative path that consistently includes folder_path."""
        cleaned_name = str(name).lstrip('/') if name else ''
        cleaned_folder = str(self.folder_path).strip('/') if self.folder_path else ''
        if cleaned_folder and cleaned_name:
            return f"{cleaned_folder}/{cleaned_name}"
        if cleaned_folder:
            return cleaned_folder
        return cleaned_name

    def __init__(self):
        """Initialize Supabase client."""
        # Get settings
        self.supabase_url = getattr(settings, 'SUPABASE_URL', None)
        self.supabase_key = getattr(settings, 'SUPABASE_KEY', None)
        self.bucket_name = getattr(settings, 'SUPABASE_BUCKET', 'media')

        # Validate required settings
        if not self.supabase_url:
            error_msg = (
                "SUPABASE_URL is not configured!\n"
                "Add to your .env file:\n"
                "  SUPABASE_URL=https://your-project-id.supabase.co"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if not self.supabase_key:
            error_msg = (
                "SUPABASE_KEY is not configured!\n"
                "Add to your .env file:\n"
                "  SUPABASE_KEY=your-anon-public-key"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Create Supabase client
        if create_client is None:
            error_msg = (
                "supabase is required but not installed!\n"
                "Install it with: pip install supabase"
            )
            logger.error(error_msg)
            raise ImportError(error_msg)
        
        try:
            self.client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✓ Supabase client initialized successfully")
        except Exception as e:
            error_msg = f"Failed to create Supabase client: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _save(self, name, content):
        """
        SAVE FILE TO SUPABASE ONLY - NEVER LOCALLY
        
        This is the critical method that ensures files go to Supabase.
        
        Args:
            name: File path/name
            content: File content (file-like object or bytes)
            
        Returns:
            The file path in Supabase
        """
        # Validate inputs
        if not name:
            raise ValueError("File name cannot be empty or None")

        # Clean the path
        original_name = name
        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)
        
        logger.info(f"\n{'*' * 70}")
        logger.info(f"FILE SAVE REQUEST TO SUPABASE")
        logger.info(f"{'*' * 70}")
        logger.info(f"Original name: {original_name}")
        logger.info(f"Cleaned name: {name}")
        logger.info(f"Bucket: {self.bucket_name}")
        logger.info(f"Folder Path: {self.folder_path}")
        # Read file content
        try:
            if hasattr(content, 'read'):
                logger.debug("Content is file-like object, reading...")
                file_content = content.read()
            else:
                logger.debug("Content is bytes, using directly...")
                file_content = content
            
            file_size = len(file_content) if file_content else 0
            logger.info(f"File size: {file_size} bytes")
            
            if not file_content:
                error_msg = f"File is empty: {name}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
        except Exception as e:
            error_msg = f"Failed to read file content: {str(e)}"
            logger.error(error_msg)
            raise IOError(error_msg)

        # Upload to Supabase ONLY
        try:
            logger.info(f"Uploading to Supabase: {self.bucket_name}/{storage_path}")
            
            mime_type, _ = mimetypes.guess_type(name)
            file_options = {"upsert": "true"}
            if mime_type:
                file_options["content-type"] = mime_type
                logger.debug(f"Detected MIME type for {name}: {mime_type}")
            else:
                logger.debug(f"No MIME type detected for {name}; using default")

            response = self.client.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_content,
                file_options=file_options
            )

            logger.info(f"✓ UPLOAD SUCCESSFUL")
            logger.info(f"  Path: {self.bucket_name}/{storage_path}")
            logger.info(f"  Response: {response}")
            logger.info(f"{'*' * 70}\n")
            
            return name

        except Exception as e:
            error_msg = (
                f"UPLOAD TO SUPABASE FAILED!\n"
                f"Error: {str(e)}\n"
                f"File: {name}\n"
                f"Bucket: {self.bucket_name}"
            )
            logger.error(error_msg)
            logger.exception("Full traceback:")
            raise IOError(error_msg)

    def _open(self, name, mode='rb'):
        """
        Open/download a file from Supabase.
        
        Args:
            name: File path in Supabase
            mode: File mode (ignored)
            
        Returns:
            BytesIO object with file content
        """
        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)
        logger.info(f"Opening file from Supabase: {self.bucket_name}/{storage_path}")

        try:
            data = self.client.storage.from_(self.bucket_name).download(storage_path)
            logger.info(f"✓ File opened: {name}")
            return BytesIO(data)
        except Exception as e:
            error_msg = f"Failed to download {name}: {str(e)}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

    def delete(self, name):
        """
        Delete a file from Supabase.
        
        Args:
            name: File path in Supabase
        """
        if not name:
            return

        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)
        logger.info(f"Deleting from Supabase: {self.bucket_name}/{storage_path}")

        try:
            self.client.storage.from_(self.bucket_name).remove([storage_path])
            logger.info(f"✓ Deleted: {name}")
        except Exception as e:
            logger.warning(f"Could not delete {name}: {str(e)}")

    def exists(self, name):
        """
        Check if file exists in Supabase.
        
        Args:
            name: File path in Supabase
            
        Returns:
            True if exists, False otherwise
        """
        if not name:
            return False

        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)

        try:
            self.client.storage.from_(self.bucket_name).get_metadata(storage_path)
            return True
        except Exception:
            return False

    def listdir(self, path):
        """
        List files in a Supabase directory.
        
        Args:
            path: Directory path
            
        Returns:
            (directories, files) tuple
        """
        path = str(path).lstrip('/') if path else ''
        storage_path = self._build_storage_path(path)

        try:
            response = self.client.storage.from_(self.bucket_name).list(path=storage_path)
            dirs = []
            files = []

            for item in response:
                if item.get('id') is None:
                    dirs.append(item['name'])
                else:
                    files.append(item['name'])

            return dirs, files
        except Exception as e:
            logger.warning(f"Could not list directory {path}: {str(e)}")
            return [], []

    def size(self, name):
        """
        Get file size in bytes.
        
        Args:
            name: File path in Supabase
            
        Returns:
            File size or 0 if error
        """
        if not name:
            return 0

        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)

        try:
            metadata = self.client.storage.from_(self.bucket_name).get_metadata(storage_path)
            size = metadata.get('metadata', {}).get('size', 0)
            return size
        except Exception:
            return 0

    def url(self, name):
        """
        Get public URL for a file in Supabase.
        
        Args:
            name: File path in Supabase
            
        Returns:
            Public HTTPS URL to access the file
        """
        if not name:
            return ''

        name = str(name).lstrip('/')

        # Construct the public URL
        storage_path = self._build_storage_path(name)
        url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{storage_path}"
        return url

    def get_accessed_time(self, name):
        """Get file access time."""
        return self.get_created_time(name)

    def get_created_time(self, name):
        """Get file creation time."""
        if not name:
            return None

        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)

        try:
            metadata = self.client.storage.from_(self.bucket_name).get_metadata(storage_path)
            return metadata.get('created_at')
        except Exception:
            return None

    def get_modified_time(self, name):
        """Get file modification time."""
        if not name:
            return None

        name = str(name).lstrip('/')
        storage_path = self._build_storage_path(name)

        try:
            metadata = self.client.storage.from_(self.bucket_name).get_metadata(storage_path)
            return metadata.get('updated_at')
        except Exception:
            return None


class SupabaseMediaStorage(SupabaseStorage):
    """
    Media Files Storage (e.g., uploads, images, documents)
    
    All user uploads go to the 'media' bucket in Supabase.
    """
    folder_path = 'media'

    def __init__(self):
        super().__init__()
        self.bucket_name = getattr(
            settings,
            'SUPABASE_MEDIA_BUCKET',
            getattr(settings, 'SUPABASE_BUCKET', self.bucket_name or 'media'),
        )
        logger.info(f"✓ SupabaseMediaStorage initialized for Media bucket")


class SupabaseStaticStorageBase(SupabaseStorage):
    """
    Static Files Storage (CSS, JavaScript, Images, etc.)
    
    All static files go to the 'static' bucket in Supabase.
    """
    folder_path='static'

    def __init__(self):
        super().__init__()
        self.bucket_name = getattr(
            settings,
            'SUPABASE_STATIC_BUCKET',
            getattr(settings, 'SUPABASE_BUCKET', self.bucket_name or 'static'),
        )
        logger.info("✓ SupabaseStaticStorage initialized for Static bucket")


class SupabaseStaticStorageNoManifest(SupabaseStaticStorageBase):
    """Static storage without manifest hashing."""


class SupabaseStaticStorage(ManifestFilesMixin, SupabaseStaticStorageBase):
    """
    Static storage with manifest hashing enabled by default.

    Set SUPABASE_STATIC_MANIFEST = False to opt out and use plain static names.
    """

    def __new__(cls, *args, **kwargs):
        use_manifest = getattr(settings, "SUPABASE_STATIC_MANIFEST", True)
        if cls is SupabaseStaticStorage and not use_manifest:
            return SupabaseStaticStorageNoManifest(*args, **kwargs)
        return super().__new__(cls)
