"""Tests for storage handlers."""

import os
import tempfile
from unittest.mock import ANY, patch, MagicMock

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

    def test_list_files_missing_path_raises(self):
        handler = LocalStorageHandler()
        with tempfile.TemporaryDirectory() as td:
            try:
                handler.list_files(os.path.join(td, 'missing'))
                assert False, 'Expected a missing path error'
            except FileNotFoundError:
                pass

    def test_list_files_keeps_iceberg_table_as_single_item(self):
        with tempfile.TemporaryDirectory() as td:
            table_dir = os.path.join(td, 'iceberg')
            metadata_dir = os.path.join(table_dir, 'metadata')
            data_dir = os.path.join(table_dir, 'data')
            os.makedirs(metadata_dir)
            os.makedirs(data_dir)
            with open(
                os.path.join(metadata_dir, '00001-table.metadata.json'),
                'w',
                encoding='utf-8',
            ) as handle:
                handle.write('{}')
            with open(
                os.path.join(data_dir, 'part.parquet'), 'wb'
            ) as handle:
                handle.write(b'PAR1')

            handler = LocalStorageHandler()

            assert handler.list_files(table_dir) == [table_dir]
            assert handler.list_files(td) == [table_dir]


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

    def test_list_download_round_trip_preserves_reserved_key_characters(self):
        from external_file_detection.storage_handlers import S3StorageHandler
        handler = S3StorageHandler.__new__(S3StorageHandler)
        paginator = MagicMock()
        paginator.paginate.return_value = [{
            'Contents': [
                {'Key': 'reports/a?b#c.csv'},
                {'Key': 'reports/literal%2Fname.csv'},
            ],
        }]
        handler.s3_client = MagicMock()
        handler.s3_client.get_paginator.return_value = paginator

        files = handler.list_files('s3://bucket/reports/')

        assert files == [
            's3://bucket/reports/a%3Fb%23c.csv',
            's3://bucket/reports/literal%252Fname.csv',
        ]
        with tempfile.TemporaryDirectory() as td:
            handler.download_file(files[0], os.path.join(td, 'download.csv'))
        handler.s3_client.download_file.assert_called_once_with(
            'bucket',
            'reports/a?b#c.csv',
            ANY,
        )

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

    def test_download_file_requires_object_key(self):
        from external_file_detection.storage_handlers import S3StorageHandler
        handler = S3StorageHandler.__new__(S3StorageHandler)
        handler.s3_client = MagicMock()
        try:
            handler.download_file('s3://bucket', 'local.csv')
            assert False, "Should have required an object key"
        except ValueError as e:
            assert 'key' in str(e)


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

    def test_list_files_propagates_service_errors(self):
        from external_file_detection.storage_handlers import AzureStorageHandler
        handler = AzureStorageHandler.__new__(AzureStorageHandler)
        container_client = MagicMock()
        container_client.list_blobs.side_effect = RuntimeError('service unavailable')
        handler.blob_service_client = MagicMock()
        handler.blob_service_client.get_container_client.return_value = (
            container_client
        )

        try:
            handler.list_files('azure://container/prefix')
            assert False, 'Expected the service error to propagate'
        except RuntimeError as e:
            assert 'service unavailable' in str(e)

    def test_list_download_round_trip_preserves_reserved_blob_characters(self):
        from external_file_detection.storage_handlers import AzureStorageHandler
        handler = AzureStorageHandler.__new__(AzureStorageHandler)
        handler.blob_service_client = MagicMock()
        container_client = MagicMock()
        first_blob = MagicMock()
        first_blob.name = 'reports/a?b#c.csv'
        second_blob = MagicMock()
        second_blob.name = 'reports/literal%2Fname.csv'
        container_client.list_blobs.return_value = [first_blob, second_blob]
        handler.blob_service_client.get_container_client.return_value = (
            container_client
        )
        blob_client = MagicMock()
        handler.blob_service_client.get_blob_client.return_value = blob_client

        files = handler.list_files('azure://container/reports/')

        assert files == [
            'azure://container/reports/a%3Fb%23c.csv',
            'azure://container/reports/literal%252Fname.csv',
        ]
        with tempfile.TemporaryDirectory() as td:
            handler.download_file(files[0], os.path.join(td, 'download.csv'))
        handler.blob_service_client.get_blob_client.assert_called_once_with(
            container='container',
            blob='reports/a?b#c.csv',
        )

    def test_https_blob_parser_preserves_empty_path_segments(self):
        from external_file_detection.storage_handlers import AzureStorageHandler
        handler = AzureStorageHandler.__new__(AzureStorageHandler)
        handler.blob_service_client = MagicMock()
        handler.blob_service_client.get_blob_client.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            handler.download_file(
                'https://account.blob.core.windows.net/'
                'container/a//b%3Fc.csv?sig=ignored',
                os.path.join(td, 'download.csv'),
            )

        handler.blob_service_client.get_blob_client.assert_called_once_with(
            container='container',
            blob='a//b?c.csv',
        )


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

    def test_rejects_lookalike_azure_hostname(self):
        handler = StorageFactory.create_handler(
            'https://account.blob.core.windows.net.attacker.example/container'
        )
        assert isinstance(handler, LocalStorageHandler)

    def test_cache_key_keeps_azure_accounts_separate(self):
        first = StorageFactory.cache_key(
            'https://one.blob.core.windows.net/container/a.csv'
        )
        second = StorageFactory.cache_key(
            'https://two.blob.core.windows.net/container/b.csv'
        )
        assert first != second
