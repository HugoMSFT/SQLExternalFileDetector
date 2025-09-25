"""Storage handlers for local, S3, and Azure storage."""

import os
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from pathlib import Path
import boto3
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential


class StorageHandler(ABC):
    """Abstract base class for storage handlers."""
    
    @abstractmethod
    def list_files(self, path: str) -> List[str]:
        """List files in the given path."""
        pass
    
    @abstractmethod
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get file information."""
        pass
    
    @abstractmethod
    def download_file(self, source_path: str, local_path: str) -> str:
        """Download file to local path for analysis."""
        pass


class LocalStorageHandler(StorageHandler):
    """Handler for local file system storage."""
    
    def list_files(self, path: str) -> List[str]:
        """List files in the local directory."""
        files = []
        if os.path.isfile(path):
            return [path]
        
        for root, dirs, filenames in os.walk(path):
            for filename in filenames:
                files.append(os.path.join(root, filename))
        
        return files
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get local file information."""
        stat = os.stat(file_path)
        return {
            'path': file_path,
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'is_file': os.path.isfile(file_path)
        }
    
    def download_file(self, source_path: str, local_path: str) -> str:
        """For local storage, just return the source path."""
        return source_path


class S3StorageHandler(StorageHandler):
    """Handler for Amazon S3 storage."""
    
    def __init__(self, aws_access_key_id: str = None, aws_secret_access_key: str = None,
                 region_name: str = 'us-east-1'):
        """Initialize S3 handler."""
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
    
    def list_files(self, path: str) -> List[str]:
        """List files in S3 bucket/prefix."""
        # Parse S3 path: s3://bucket/prefix
        if not path.startswith('s3://'):
            raise ValueError("S3 path must start with s3://")
        
        path_parts = path[5:].split('/', 1)
        bucket = path_parts[0]
        prefix = path_parts[1] if len(path_parts) > 1 else ''
        
        files = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    if not obj['Key'].endswith('/'):  # Skip directories
                        files.append(f"s3://{bucket}/{obj['Key']}")
        
        return files
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get S3 file information."""
        if not file_path.startswith('s3://'):
            raise ValueError("S3 path must start with s3://")
        
        path_parts = file_path[5:].split('/', 1)
        bucket = path_parts[0]
        key = path_parts[1]
        
        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=key)
            return {
                'path': file_path,
                'size': response['ContentLength'],
                'modified': response['LastModified'].timestamp(),
                'is_file': True,
                'etag': response['ETag']
            }
        except Exception as e:
            return {
                'path': file_path,
                'error': str(e),
                'is_file': False
            }
    
    def download_file(self, source_path: str, local_path: str) -> str:
        """Download S3 file to local path."""
        if not source_path.startswith('s3://'):
            raise ValueError("S3 path must start with s3://")
        
        path_parts = source_path[5:].split('/', 1)
        bucket = path_parts[0]
        key = path_parts[1]
        
        # Create local directory if it doesn't exist
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        self.s3_client.download_file(bucket, key, local_path)
        return local_path


class AzureStorageHandler(StorageHandler):
    """Handler for Azure Blob Storage."""
    
    def __init__(self, account_name: str = None, account_key: str = None, 
                 connection_string: str = None):
        """Initialize Azure storage handler."""
        if connection_string:
            self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        elif account_name:
            if account_key:
                account_url = f"https://{account_name}.blob.core.windows.net"
                self.blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=account_key
                )
            else:
                # Use default Azure credentials
                account_url = f"https://{account_name}.blob.core.windows.net"
                credential = DefaultAzureCredential()
                self.blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=credential
                )
        else:
            raise ValueError("Either connection_string or account_name must be provided")
    
    def list_files(self, path: str) -> List[str]:
        """List files in Azure blob container."""
        # Parse Azure path: https://account.blob.core.windows.net/container/prefix
        # or azure://container/prefix
        if path.startswith('https://'):
            # Parse full URL
            parts = path.split('/')
            account_name = parts[2].split('.')[0]
            container = parts[3]
            prefix = '/'.join(parts[4:]) if len(parts) > 4 else ''
        elif path.startswith('azure://'):
            # Parse simplified format
            path_parts = path[8:].split('/', 1)
            container = path_parts[0]
            prefix = path_parts[1] if len(path_parts) > 1 else ''
        else:
            raise ValueError("Azure path must start with https:// or azure://")
        
        files = []
        container_client = self.blob_service_client.get_container_client(container)
        
        try:
            blob_list = container_client.list_blobs(name_starts_with=prefix)
            for blob in blob_list:
                if not blob.name.endswith('/'):  # Skip directories
                    files.append(f"azure://{container}/{blob.name}")
        except Exception as e:
            print(f"Error listing Azure blobs: {e}")
        
        return files
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get Azure blob information."""
        if file_path.startswith('azure://'):
            path_parts = file_path[8:].split('/', 1)
            container = path_parts[0]
            blob_name = path_parts[1]
        else:
            raise ValueError("Azure path must start with azure://")
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=container, 
                blob=blob_name
            )
            properties = blob_client.get_blob_properties()
            
            return {
                'path': file_path,
                'size': properties.size,
                'modified': properties.last_modified.timestamp(),
                'is_file': True,
                'etag': properties.etag,
                'content_type': properties.content_settings.content_type
            }
        except Exception as e:
            return {
                'path': file_path,
                'error': str(e),
                'is_file': False
            }
    
    def download_file(self, source_path: str, local_path: str) -> str:
        """Download Azure blob to local path."""
        if not source_path.startswith('azure://'):
            raise ValueError("Azure path must start with azure://")
        
        path_parts = source_path[8:].split('/', 1)
        container = path_parts[0]
        blob_name = path_parts[1]
        
        # Create local directory if it doesn't exist
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        blob_client = self.blob_service_client.get_blob_client(
            container=container,
            blob=blob_name
        )
        
        with open(local_path, 'wb') as download_file:
            download_file.write(blob_client.download_blob().readall())
        
        return local_path


class StorageFactory:
    """Factory for creating storage handlers."""
    
    @staticmethod
    def create_handler(path: str, **kwargs) -> StorageHandler:
        """Create appropriate storage handler based on path."""
        if path.startswith('s3://'):
            return S3StorageHandler(
                aws_access_key_id=kwargs.get('aws_access_key_id'),
                aws_secret_access_key=kwargs.get('aws_secret_access_key'),
                region_name=kwargs.get('region_name', 'us-east-1')
            )
        elif path.startswith('azure://') or path.startswith('https://') and 'blob.core.windows.net' in path:
            return AzureStorageHandler(
                account_name=kwargs.get('azure_account_name'),
                account_key=kwargs.get('azure_account_key'),
                connection_string=kwargs.get('azure_connection_string')
            )
        else:
            return LocalStorageHandler()