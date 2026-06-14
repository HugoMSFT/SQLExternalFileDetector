import * as vscode from 'vscode';
import { PythonBridge } from './pythonBridge';
import { AnalyzedFilesProvider, PlatformInfoProvider } from './treeDataProvider';
import { registerCommands } from './commands';
import { SqlPreviewPanel } from './sqlPreviewPanel';

let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext): void {
    outputChannel = vscode.window.createOutputChannel('External File Detection');
    context.subscriptions.push(outputChannel);

    const bridge = new PythonBridge(outputChannel);
    const treeProvider = new AnalyzedFilesProvider();
    const platformProvider = new PlatformInfoProvider();

    // Register tree views
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider('efd.analyzedFiles', treeProvider),
        vscode.window.registerTreeDataProvider('efd.platformInfo', platformProvider),
    );

    // Register all commands
    registerCommands(context, bridge, treeProvider, platformProvider);

    // Refresh platform view when configuration changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('externalFileDetection')) {
                platformProvider.refresh();
            }
        }),
    );

    // Status bar item showing current platform
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
    statusBarItem.command = 'efd.setPlatform';
    updateStatusBar(statusBarItem);
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('externalFileDetection.targetPlatform')) {
                updateStatusBar(statusBarItem);
            }
        }),
    );

    // Clean up webview on deactivate
    context.subscriptions.push({
        dispose: () => {
            SqlPreviewPanel.currentPanel?.dispose();
        },
    });

    outputChannel.appendLine('External File Detection extension activated');
}

function updateStatusBar(item: vscode.StatusBarItem): void {
    const platform = vscode.workspace
        .getConfiguration('externalFileDetection')
        .get<string>('targetPlatform', 'sql_server_2022');

    const shortLabels: Record<string, string> = {
        sql_server_2019: 'SQL 2019',
        sql_server_2022: 'SQL 2022',
        sql_server_2025: 'SQL 2025',
        azure_sql_database: 'Azure SQL DB',
        azure_sql_managed_instance: 'Azure SQL MI',
        fabric_sql_database: 'Fabric SQL',
    };

    item.text = `$(database) ${shortLabels[platform] || platform}`;
    item.tooltip = 'External File Detection: Click to change target platform';
}

export function deactivate(): void {
    // Cleanup handled by disposables
}
