"""CLI behavior and option-forwarding tests."""

from unittest.mock import patch

from click.testing import CliRunner

from external_file_detection.cli import main


def test_analyze_files_forwards_cloud_credentials():
    runner = CliRunner()
    with patch(
        'external_file_detection.cli.ExternalFileDetectorApp'
    ) as app_type:
        app_type.return_value.analyze_files.return_value = []
        result = runner.invoke(main, [
            'analyze-files',
            's3://bucket/data.csv',
            '--aws-access-key-id',
            'access',
            '--aws-secret-access-key',
            'secret',
            '--aws-region',
            'west',
        ])

    assert result.exit_code == 0
    app_type.assert_called_once_with({
        'aws_access_key_id': 'access',
        'aws_secret_access_key': 'secret',
        'region_name': 'west',
    })
    app_type.return_value.analyze_files.assert_called_once_with(
        ['s3://bucket/data.csv'],
        None,
    )


def test_analyze_files_returns_nonzero_when_any_file_fails():
    runner = CliRunner()
    failed_result = {
        'file_path': 'broken.csv',
        'error': 'invalid file',
        'metadata': {'file_type': 'csv'},
        'sql_ddl': None,
    }
    with patch(
        'external_file_detection.cli.ExternalFileDetectorApp'
    ) as app_type:
        app_type.return_value.analyze_files.return_value = [failed_result]
        result = runner.invoke(main, ['analyze-files', 'broken.csv'])

    assert result.exit_code != 0
    assert '1 of 1 files could not be analyzed' in result.output


def test_gui_commands_share_the_same_launcher():
    runner = CliRunner()
    with patch('external_file_detection.cli._run_web_gui') as run_gui:
        gui_result = runner.invoke(main, [
            'gui',
            '--port',
            '5050',
            '--root-dir',
            'data',
        ])
        web_result = runner.invoke(main, [
            'web',
            '--port',
            '5051',
            '--root-dir',
            'other-data',
        ])

    assert gui_result.exit_code == 0
    assert web_result.exit_code == 0
    assert run_gui.call_args_list[0].args == (
        '127.0.0.1',
        5050,
        False,
        'data',
    )
    assert run_gui.call_args_list[1].args == (
        '127.0.0.1',
        5051,
        False,
        'other-data',
    )
