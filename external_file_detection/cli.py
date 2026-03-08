"""Command-line interface for External File Detection."""

import click
import json
import os
import sys
import logging
from typing import Dict, Any

from .external_file_detector import ExternalFileDetectorApp

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="1.0.0")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(verbose):
    """External File Detector - Detect file types and generate SQL DDL."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@main.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
@click.option('--debug', is_flag=True, help='Enable debug mode')
def gui(host, port, debug):
    """Launch the web-based graphical user interface."""
    try:
        from .web_gui import ExternalFileDetectionWebGUI
        app = ExternalFileDetectionWebGUI()
        app.run(host=host, port=port, debug=debug)
    except ImportError as e:
        click.echo(f"Error: Could not launch web GUI: {e}")
        click.echo("Please ensure Flask is installed: pip install flask")
    except Exception as e:
        click.echo(f"Error: {e}")


@main.command()
@click.argument('location', type=str)
@click.option('--data-source', '-d', default=None, 
              help='Name of the external data source for SQL DDL')
@click.option('--output', '-o', default=None, 
              help='Output file path for results')
@click.option('--format', '-f', default='sql', type=click.Choice(['sql', 'json']),
              help='Output format')
@click.option('--aws-access-key-id', default=None, envvar='AWS_ACCESS_KEY_ID',
              help='AWS access key ID (or set AWS_ACCESS_KEY_ID env var)')
@click.option('--aws-secret-access-key', default=None, envvar='AWS_SECRET_ACCESS_KEY',
              help='AWS secret access key (or set AWS_SECRET_ACCESS_KEY env var)')
@click.option('--aws-region', default='us-east-1', envvar='AWS_DEFAULT_REGION',
              help='AWS region (or set AWS_DEFAULT_REGION env var)')
@click.option('--azure-account-name', default=None, envvar='AZURE_STORAGE_ACCOUNT',
              help='Azure storage account name (or set AZURE_STORAGE_ACCOUNT env var)')
@click.option('--azure-account-key', default=None, envvar='AZURE_STORAGE_KEY',
              help='Azure storage account key (or set AZURE_STORAGE_KEY env var)')
@click.option('--azure-connection-string', default=None, envvar='AZURE_STORAGE_CONNECTION_STRING',
              help='Azure storage connection string (or set AZURE_STORAGE_CONNECTION_STRING env var)')
def analyze(location, data_source, output, format, aws_access_key_id, 
           aws_secret_access_key, aws_region, azure_account_name,
           azure_account_key, azure_connection_string):
    """Analyze files at the specified location."""
    
    # Prepare storage configuration
    storage_config = {}
    if aws_access_key_id:
        storage_config['aws_access_key_id'] = aws_access_key_id
    if aws_secret_access_key:
        storage_config['aws_secret_access_key'] = aws_secret_access_key
    if aws_region:
        storage_config['region_name'] = aws_region
    if azure_account_name:
        storage_config['azure_account_name'] = azure_account_name
    if azure_account_key:
        storage_config['azure_account_key'] = azure_account_key
    if azure_connection_string:
        storage_config['azure_connection_string'] = azure_connection_string
    
    # Initialize application
    app = ExternalFileDetectorApp(storage_config)
    
    try:
        # Analyze location
        click.echo(f"Analyzing location: {location}")
        results = app.analyze_location(location, data_source)
        
        # Display summary
        click.echo(f"\nAnalysis completed!")
        click.echo(f"Files found: {results['files_found']}")
        
        if results['files_found'] > 0:
            click.echo(f"Total size: {results['summary']['total_size']:,} bytes")
            click.echo("File types:")
            for file_type, count in results['summary']['file_types'].items():
                click.echo(f"  {file_type}: {count}")
        
        # Export results if output specified
        if output:
            app.export_results(results, output, format)
            click.echo(f"\nResults exported to: {output}")
        else:
            # Display results to console
            if format == 'json':
                click.echo("\nResults (JSON):")
                click.echo(json.dumps(results, indent=2, default=str))
            else:
                click.echo("\nGenerated SQL DDL:")
                for file_result in results['files']:
                    if 'error' in file_result:
                        click.echo(f"-- Error analyzing {file_result['file_path']}: {file_result['error']}")
                    else:
                        click.echo(f"-- File: {file_result['file_path']}")
                        click.echo(file_result['sql_ddl'])
                        click.echo()
        
        if 'error' in results:
            click.echo(f"Warning: {results['error']}", err=True)
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise SystemExit(1)


@main.command()
@click.argument('files', nargs=-1, required=True)
@click.option('--data-source', '-d', default=None,
              help='Name of the external data source for SQL DDL')
@click.option('--output', '-o', default=None,
              help='Output file path for results')
@click.option('--format', '-f', default='sql', type=click.Choice(['sql', 'json']),
              help='Output format')
def analyze_files(files, data_source, output, format):
    """Analyze specific files."""
    
    app = ExternalFileDetectorApp()
    
    try:
        results = app.analyze_files(list(files), data_source)
        
        click.echo(f"Analyzed {len(results)} files")
        
        # Export or display results
        if output:
            # Convert to same format as analyze command
            export_data = {
                'location': 'multiple_files',
                'files_found': len(results),
                'files': results
            }
            app.export_results(export_data, output, format)
            click.echo(f"Results exported to: {output}")
        else:
            if format == 'json':
                click.echo(json.dumps(results, indent=2, default=str))
            else:
                for result in results:
                    if 'error' in result:
                        click.echo(f"-- Error analyzing {result['file_path']}: {result['error']}")
                    else:
                        click.echo(f"-- File: {result['file_path']}")
                        click.echo(result['sql_ddl'])
                        click.echo()
    
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise SystemExit(1)


@main.command()
@click.argument('name')
@click.argument('storage_type', type=click.Choice(['s3', 'azure', 'local']))
@click.argument('location')
@click.option('--credential', default=None,
              help='Name of the database credential to use')
def generate_data_source(name, storage_type, location, credential):
    """Generate CREATE EXTERNAL DATA SOURCE statement."""
    
    app = ExternalFileDetectorApp()
    
    try:
        ddl = app.generate_data_source_ddl(name, storage_type, location, credential)
        click.echo(ddl)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise SystemExit(1)


@main.command()
def supported_types():
    """List supported file types."""
    
    app = ExternalFileDetectorApp()
    types = app.get_supported_file_types()
    
    click.echo("Supported file types:")
    for file_type in sorted(types):
        click.echo(f"  {file_type}")


@main.command()
@click.argument('location')
@click.option('--aws-access-key-id', default=None, envvar='AWS_ACCESS_KEY_ID')
@click.option('--aws-secret-access-key', default=None, envvar='AWS_SECRET_ACCESS_KEY')
@click.option('--aws-region', default='us-east-1', envvar='AWS_DEFAULT_REGION')
@click.option('--azure-account-name', default=None, envvar='AZURE_STORAGE_ACCOUNT')
@click.option('--azure-account-key', default=None, envvar='AZURE_STORAGE_KEY')
@click.option('--azure-connection-string', default=None, envvar='AZURE_STORAGE_CONNECTION_STRING')
def list_files(location, aws_access_key_id, aws_secret_access_key, aws_region,
               azure_account_name, azure_account_key, azure_connection_string):
    """List files at the specified location."""
    
    from .storage_handlers import StorageFactory
    
    # Prepare storage configuration
    storage_config = {}
    if aws_access_key_id:
        storage_config['aws_access_key_id'] = aws_access_key_id
    if aws_secret_access_key:
        storage_config['aws_secret_access_key'] = aws_secret_access_key
    if aws_region:
        storage_config['region_name'] = aws_region
    if azure_account_name:
        storage_config['azure_account_name'] = azure_account_name
    if azure_account_key:
        storage_config['azure_account_key'] = azure_account_key
    if azure_connection_string:
        storage_config['azure_connection_string'] = azure_connection_string
    
    try:
        storage_handler = StorageFactory.create_handler(location, **storage_config)
        files = storage_handler.list_files(location)
        
        click.echo(f"Files found at {location}:")
        for file_path in files:
            click.echo(f"  {file_path}")
        
        click.echo(f"\nTotal files: {len(files)}")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise SystemExit(1)


@main.command()
@click.option('--host', '-h', default='127.0.0.1', help='Host to bind to')
@click.option('--port', '-p', default=5000, type=int, help='Port to listen on')
@click.option('--debug', is_flag=True, help='Enable debug mode')
def web(host, port, debug):
    """Launch the web UI."""
    from .web_ui import run_web_ui
    run_web_ui(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()