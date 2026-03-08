"""Tests for storage handlers."""

import os
import tempfile
from unittest.mock import patch, MagicMock

from external_file_detection.storage_handlers import (
    LocalStorageHandler,
    StorageFactory,
)


class TestLocalStorageHandler:
    """Tests for LocalStorageHandler."""

    def test_list_files_single_file(self):
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            f.write(b'a,b\n1,2\n')
            path = f.name
        try:
            handler = LocalStorageHandler()
            files = handler.list_files(path)
            assert files == [path]
        finally:
            os.unlink(path)

    def test_list_files_directory(self):
        with tempfile.TemporaryDirectory() as td:
            for name in ('a.csv', 'b.json'):
                with open(os.path.join(td, name), 'w') as f:
                    f.write('data')
            handler = LocalStorageHandler()
            files = handler.list_files(td)
            assert len(files) == 2
            basenames = sorted(os.path.basename(f) for f in files)
            assert basenames == ['a.csv', 'b.json']

    def test_get_file_info(self):
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b'hello')
            path = f.name
        try:
            handler = LocalStorageHandler()
            info = handler.get_file_info(path)
            assert info['size'] == 5
            assert info['is_file'] is True
        finally:
            os.unlink(path)

    def test_download_file_returns_source_path(self):
        handler = LocalStorageHandler()
        assert handler.download_file('/src/path', '/dst/path') == '/src/path'


class TestS3StorageHandler:
    """Tests for S3StorageHandler (mocked boto3)."""

    def test_import_error_when_boto3_missing(self):
        import importlib
        with patch.dict('sys.modules', {'boto3': None}):
            try:
                from external_file_detection.storage_handlers import S3StorageHandler
                S3StorageHandler()
                assert False, "Should have raised ImportError"
            except ImportError:
                pass

    def test_list_files_invalid_path(self):
        with patch('boto3.client'):
            from external_file_detection.storage_handlers import S3StorageHandler
            handler = S3StorageHandler.__new__(S3StorageHandler)
            handler.s3_client = MagicMock()
            try:
                handler.list_files('/not/s3/path')
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert 's3://' in str(e)

    def test_list_files_parses_bucket_prefix(self):
        with patch('boto3.client'):
            from external_file_detection.storage_handlers import S3StorageHandler
            handler = S3StorageHandler.__new__(S3StorageHandler)
            mock_paginator = MagicMock()
            mock_paginator.paginate.return_value = [
                {'Contents': [
                    {'Key': 'data/file1.csv'},
                    {'Key': 'data/file2.csv'},
                    {'Key': 'data/subdir/'},  # directory, should be skipped
                ]}
            ]
            handler.s3_client = MagicMock()
            handler.s3_client.get_paginator.return_value = mock_paginator

            files = handler.list_files('s3://mybucket/data/')
            assert len(files) == 2
            assert files[0] == 's3://mybucket/data/file1.csv'

    def test_download_file_invalid_path(self):
        with patch('boto3.client'):
            from external_file_detection.storage_handlers import S3StorageHandler
            handler = S3StorageHandler.__new__(S3StorageHandler)
            handler.s3_client = MagicMock()
            try:
                handler.download_file('/not/s3', '/local')
                assert False, "Should have raised ValueError"
            except ValueError:
                pass


class TestAzureStorageHandler:
    """Tests for AzureStorageHandler (mocked azure libs)."""

    def test_list_files_invalid_path(self):
        mock_bsc = MagicMock()
        with patch.dict('sys.modules', {
            'azure': MagicMock(),
            'azure.storage': MagicMock(),
            'azure.storage.blob': MagicMock(),
            'azure.identity': MagicMock(),
        }):
            from external_file_detection.storage_handlers import AzureStorageHandler
            handler = AzureStorageHandler.__new__(AzureStorageHandler)
            handler.blob_service_client = mock_bsc
            try:
                handler.list_files('/invalid/path')
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert 'https://' in str(e) or 'azure://' in str(e)

    def test_download_file_invalid_path(self):
        mock_bsc = MagicMock()
        with patch.dict('sys.modules', {
            'azure': MagicMock(),
            'azure.storage': MagicMock(),
            'azure.storage.blob': MagicMock(),
            'azure.identity': MagicMock(),
        }):
            from external_file_detection.storage_handlers import AzureStorageHandler
            handler = AzureStorageHandler.__new__(AzureStorageHandler)
            handler.blob_service_client = mock_bsc
            try:
                handler.download_file('/not/azure', '/local')
                assert False, "Should have raised ValueError"
            except ValueError:
                pass


class TestStorageFactory:
    """Tests for StorageFactory."""

    def test_creates_local_handler_for_local_path(self):
        handler = StorageFactory.create_handler('/some/local/path')
        assert isinstance(handler, LocalStorageHandler)

    def test_creates_local_handler_for_relative_path(self):
        handler = StorageFactory.create_handler('relative/path')
        assert isinstance(handler, LocalStorageHandler)

    def test_creates_s3_handler(self):
        with patch('boto3.client'):
            handler = StorageFactory.create_handler('s3://bucket/key')
            from external_file_detection.storage_handlers import S3StorageHandler
            assert isinstance(handler, S3StorageHandler)

    def test_creates_azure_handler_for_https(self):
        with patch.dict('sys.modules', {
            'azure': MagicMock(),
            'azure.storage': MagicMock(),
            'azure.storage.blob': MagicMock(),
            'azure.identity': MagicMock(),
        }):
            handler = StorageFactory.create_handler(
                'https://myaccount.blob.core.windows.net/container',
                azure_account_name='myaccount',
                azure_account_key='key123',
            )
            from external_file_detection.storage_handlers import AzureStorageHandler
            assert isinstance(handler, AzureStorageHandler)
