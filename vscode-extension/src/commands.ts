import * as vscode from 'vscode';
import * as path from 'path';
import { PythonBridge, AnalysisResult } from './pythonBridge';
import { AnalyzedFilesProvider, AnalyzedFileItem } from './treeDataProvider';
import { SqlPreviewPanel } from './sqlPreviewPanel';
import { getConfig, PLATFORM_LABELS } from './configuration';

export function registerCommands(
    context: vscode.ExtensionContext,
    bridge: PythonBridge,
    treeProvider: AnalyzedFilesProvider,
    platformProvider: { refresh(): void },
): void {
    // Analyze a single file
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.analyzeFile', async (uri?: vscode.Uri) => {
            const filePath = await resolveFilePath(uri);
            if (!filePath) { return; }

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Analyzing file...' },
                async () => {
                    try {
                        const result = await bridge.analyzeFile(filePath);
                        treeProvider.addResult(result);
                        vscode.window.showInformationMessage(
                            `Analyzed: ${result.file_name} (${result.file_type.toUpperCase()})`
                        );
                    } catch (err) {
                        vscode.window.showErrorMessage(`Analysis failed: ${errorMessage(err)}`);
                    }
                },
            );
        }),
    );

    // Analyze a folder
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.analyzeFolder', async (uri?: vscode.Uri) => {
            let folderPath: string | undefined;

            if (uri) {
                folderPath = uri.fsPath;
            } else {
                const picked = await vscode.window.showOpenDialog({
                    canSelectFiles: false,
                    canSelectFolders: true,
                    canSelectMany: false,
                    openLabel: 'Analyze Folder',
                });
                folderPath = picked?.[0]?.fsPath;
            }

            if (!folderPath) { return; }

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Scanning folder...' },
                async () => {
                    try {
                        const result = await bridge.analyzeFolder(folderPath!);
                        if (result.files.length === 0) {
                            vscode.window.showInformationMessage('No supported files found in folder.');
                            return;
                        }
                        treeProvider.addResults(result.files);
                        vscode.window.showInformationMessage(
                            `Found ${result.count} file(s) in ${path.basename(folderPath!)}`
                        );
                    } catch (err) {
                        vscode.window.showErrorMessage(`Folder scan failed: ${errorMessage(err)}`);
                    }
                },
            );
        }),
    );

    // Generate DDL for a file
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.generateDDL', async (itemOrUri?: AnalyzedFileItem | vscode.Uri) => {
            const result = await resolveAnalysisResult(itemOrUri, bridge, treeProvider);
            if (!result) { return; }

            const tableName = sanitizeTableName(result.file_name);

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Generating SQL DDL...' },
                async () => {
                    try {
                        const config = getConfig();
                        const ddl = await bridge.generateDDL({
                            metadata: result.metadata,
                            table_name: tableName,
                            location: result.file_path,
                        });
                        SqlPreviewPanel.show(
                            context.extensionUri,
                            ddl,
                            result.file_name,
                            config.targetPlatform,
                        );
                    } catch (err) {
                        vscode.window.showErrorMessage(`DDL generation failed: ${errorMessage(err)}`);
                    }
                },
            );
        }),
    );

    // Generate all statement types
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.generateAllStatements', async (item?: AnalyzedFileItem) => {
            const result = await resolveAnalysisResult(item, bridge, treeProvider);
            if (!result) { return; }

            const tableName = sanitizeTableName(result.file_name);

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Generating all SQL statements...' },
                async () => {
                    try {
                        const config = getConfig();
                        const ddl = await bridge.generateAll({
                            metadata: result.metadata,
                            table_name: tableName,
                            location: result.file_path,
                        });
                        SqlPreviewPanel.show(
                            context.extensionUri,
                            ddl,
                            result.file_name,
                            config.targetPlatform,
                        );
                    } catch (err) {
                        vscode.window.showErrorMessage(`Generation failed: ${errorMessage(err)}`);
                    }
                },
            );
        }),
    );

    // Preview file data
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.previewData', async (itemOrUri?: AnalyzedFileItem | vscode.Uri) => {
            let filePath: string | undefined;

            if (itemOrUri instanceof AnalyzedFileItem) {
                filePath = itemOrUri.filePath;
            } else {
                filePath = await resolveFilePath(itemOrUri);
            }

            if (!filePath) { return; }

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Loading preview...' },
                async () => {
                    try {
                        const config = getConfig();
                        const preview = await bridge.previewData(filePath!, config.maxPreviewRows);
                        const doc = await vscode.workspace.openTextDocument({
                            content: JSON.stringify(preview, null, 2),
                            language: 'json',
                        });
                        await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
                    } catch (err) {
                        vscode.window.showErrorMessage(`Preview failed: ${errorMessage(err)}`);
                    }
                },
            );
        }),
    );

    // Set target platform
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.setPlatform', async () => {
            const items = Object.entries(PLATFORM_LABELS).map(([value, label]) => ({
                label,
                value,
                picked: value === getConfig().targetPlatform,
            }));

            const picked = await vscode.window.showQuickPick(items, {
                placeHolder: 'Select target SQL platform',
            });

            if (picked) {
                await vscode.workspace
                    .getConfiguration('externalFileDetection')
                    .update('targetPlatform', picked.value, vscode.ConfigurationTarget.Workspace);
                platformProvider.refresh();
                vscode.window.showInformationMessage(`Platform set to ${picked.label}`);
            }
        }),
    );

    // Clear results
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.clearResults', () => {
            treeProvider.clear();
        }),
    );

    // Refresh tree
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.refreshTree', () => {
            treeProvider.refresh();
        }),
    );

    // Copy SQL to clipboard
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.copySQL', async (item?: AnalyzedFileItem) => {
            const result = await resolveAnalysisResult(item, bridge, treeProvider);
            if (!result) { return; }

            const tableName = sanitizeTableName(result.file_name);

            try {
                const ddl = await bridge.generateDDL({
                    metadata: result.metadata,
                    table_name: tableName,
                    location: result.file_path,
                });

                const allSql = Object.values(ddl.statements).join('\n\nGO\n\n');
                await vscode.env.clipboard.writeText(allSql);
                vscode.window.showInformationMessage('SQL DDL copied to clipboard');
            } catch (err) {
                vscode.window.showErrorMessage(`Copy failed: ${errorMessage(err)}`);
            }
        }),
    );

    // Remove analyzed file
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.removeAnalyzedFile', (item?: AnalyzedFileItem) => {
            if (item) {
                treeProvider.removeResult(item.filePath);
            }
        }),
    );

    // Export results
    context.subscriptions.push(
        vscode.commands.registerCommand('efd.exportResults', async () => {
            const allResults = treeProvider.getAllResults();
            if (allResults.length === 0) {
                vscode.window.showInformationMessage('No analyzed files to export.');
                return;
            }

            const saveUri = await vscode.window.showSaveDialog({
                defaultUri: vscode.Uri.file('external_file_ddl.sql'),
                filters: {
                    'SQL Files': ['sql'],
                    'JSON Files': ['json'],
                },
            });

            if (!saveUri) { return; }

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Exporting...' },
                async () => {
                    try {
                        const isSql = saveUri.fsPath.endsWith('.sql');
                        const parts: string[] = [];

                        for (const result of allResults) {
                            const tableName = sanitizeTableName(result.file_name);
                            const ddl = await bridge.generateDDL({
                                metadata: result.metadata,
                                table_name: tableName,
                                location: result.file_path,
                            });

                            if (isSql) {
                                parts.push(`-- ============================================`);
                                parts.push(`-- File: ${result.file_name}`);
                                parts.push(`-- Type: ${result.file_type}`);
                                parts.push(`-- ============================================`);
                                parts.push(Object.values(ddl.statements).join('\n\nGO\n\n'));
                                parts.push('\nGO\n');
                            } else {
                                parts.push(JSON.stringify({ file: result, ddl }, null, 2));
                            }
                        }

                        const content = isSql ? parts.join('\n') : `[${parts.join(',\n')}]`;
                        const encoder = new TextEncoder();
                        await vscode.workspace.fs.writeFile(saveUri, encoder.encode(content));
                        vscode.window.showInformationMessage(`Exported ${allResults.length} file(s) to ${path.basename(saveUri.fsPath)}`);
                    } catch (err) {
                        vscode.window.showErrorMessage(`Export failed: ${errorMessage(err)}`);
                    }
                },
            );
        }),
    );
}

async function resolveFilePath(uri?: vscode.Uri): Promise<string | undefined> {
    if (uri) {
        return uri.fsPath;
    }

    const editor = vscode.window.activeTextEditor;
    if (editor) {
        return editor.document.uri.fsPath;
    }

    const picked = await vscode.window.showOpenDialog({
        canSelectFiles: true,
        canSelectMany: false,
        openLabel: 'Select File to Analyze',
    });

    return picked?.[0]?.fsPath;
}

async function resolveAnalysisResult(
    itemOrUri: AnalyzedFileItem | vscode.Uri | undefined,
    bridge: PythonBridge,
    treeProvider: AnalyzedFilesProvider,
): Promise<AnalysisResult | undefined> {
    if (itemOrUri instanceof AnalyzedFileItem) {
        return itemOrUri.stored.result;
    }

    let filePath: string | undefined;

    if (itemOrUri instanceof vscode.Uri) {
        filePath = itemOrUri.fsPath;
    } else {
        filePath = await resolveFilePath();
    }

    if (!filePath) { return undefined; }

    // Check if already analyzed
    const existing = treeProvider.getResult(filePath);
    if (existing) { return existing; }

    // Analyze on the fly
    try {
        const result = await bridge.analyzeFile(filePath);
        treeProvider.addResult(result);
        return result;
    } catch (err) {
        vscode.window.showErrorMessage(`Failed to analyze file: ${errorMessage(err)}`);
        return undefined;
    }
}

function sanitizeTableName(fileName: string): string {
    const withoutExt = fileName.replace(/\.[^.]+$/, '');
    return withoutExt.replace(/[^a-zA-Z0-9_]/g, '_').replace(/^(\d)/, '_$1');
}

function errorMessage(err: unknown): string {
    if (err instanceof Error) { return err.message; }
    return String(err);
}
