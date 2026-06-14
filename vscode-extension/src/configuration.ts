import * as vscode from 'vscode';

export interface EfdConfig {
    pythonPath: string;
    targetPlatform: string;
    defaultDataSource: string;
    defaultSchema: string;
    defaultFileFormat: string;
    credentialName: string;
    includeBestPractices: boolean;
    maxPreviewRows: number;
}

export function getConfig(): EfdConfig {
    const cfg = vscode.workspace.getConfiguration('externalFileDetection');
    return {
        pythonPath: cfg.get<string>('pythonPath', 'python'),
        targetPlatform: cfg.get<string>('targetPlatform', 'sql_server_2022'),
        defaultDataSource: cfg.get<string>('defaultDataSource', 'MyExternalDataSource'),
        defaultSchema: cfg.get<string>('defaultSchema', 'dbo'),
        defaultFileFormat: cfg.get<string>('defaultFileFormat', ''),
        credentialName: cfg.get<string>('credentialName', ''),
        includeBestPractices: cfg.get<boolean>('includebestPractices', true),
        maxPreviewRows: cfg.get<number>('maxPreviewRows', 100),
    };
}

export const PLATFORM_LABELS: Record<string, string> = {
    sql_server_2019: 'SQL Server 2019',
    sql_server_2022: 'SQL Server 2022',
    sql_server_2025: 'SQL Server 2025',
    azure_sql_database: 'Azure SQL Database',
    azure_sql_managed_instance: 'Azure SQL Managed Instance',
    fabric_sql_database: 'Microsoft Fabric SQL Database',
};
