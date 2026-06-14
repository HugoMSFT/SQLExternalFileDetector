"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerCommands = registerCommands;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const treeDataProvider_1 = require("./treeDataProvider");
const sqlPreviewPanel_1 = require("./sqlPreviewPanel");
const configuration_1 = require("./configuration");
function registerCommands(context, bridge, treeProvider, platformProvider) {
    // Analyze a single file
    context.subscriptions.push(vscode.commands.registerCommand('efd.analyzeFile', async (uri) => {
        const filePath = await resolveFilePath(uri);
        if (!filePath) {
            return;
        }
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Analyzing file...' }, async () => {
            try {
                const result = await bridge.analyzeFile(filePath);
                treeProvider.addResult(result);
                vscode.window.showInformationMessage(`Analyzed: ${result.file_name} (${result.file_type.toUpperCase()})`);
            }
            catch (err) {
                vscode.window.showErrorMessage(`Analysis failed: ${errorMessage(err)}`);
            }
        });
    }));
    // Analyze a folder
    context.subscriptions.push(vscode.commands.registerCommand('efd.analyzeFolder', async (uri) => {
        let folderPath;
        if (uri) {
            folderPath = uri.fsPath;
        }
        else {
            const picked = await vscode.window.showOpenDialog({
                canSelectFiles: false,
                canSelectFolders: true,
                canSelectMany: false,
                openLabel: 'Analyze Folder',
            });
            folderPath = picked?.[0]?.fsPath;
        }
        if (!folderPath) {
            return;
        }
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Scanning folder...' }, async () => {
            try {
                const result = await bridge.analyzeFolder(folderPath);
                if (result.files.length === 0) {
                    vscode.window.showInformationMessage('No supported files found in folder.');
                    return;
                }
                treeProvider.addResults(result.files);
                vscode.window.showInformationMessage(`Found ${result.count} file(s) in ${path.basename(folderPath)}`);
            }
            catch (err) {
                vscode.window.showErrorMessage(`Folder scan failed: ${errorMessage(err)}`);
            }
        });
    }));
    // Generate DDL for a file
    context.subscriptions.push(vscode.commands.registerCommand('efd.generateDDL', async (itemOrUri) => {
        const result = await resolveAnalysisResult(itemOrUri, bridge, treeProvider);
        if (!result) {
            return;
        }
        const tableName = sanitizeTableName(result.file_name);
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Generating SQL DDL...' }, async () => {
            try {
                const config = (0, configuration_1.getConfig)();
                const ddl = await bridge.generateDDL({
                    metadata: result.metadata,
                    table_name: tableName,
                    location: result.file_path,
                });
                sqlPreviewPanel_1.SqlPreviewPanel.show(context.extensionUri, ddl, result.file_name, config.targetPlatform);
            }
            catch (err) {
                vscode.window.showErrorMessage(`DDL generation failed: ${errorMessage(err)}`);
            }
        });
    }));
    // Generate all statement types
    context.subscriptions.push(vscode.commands.registerCommand('efd.generateAllStatements', async (item) => {
        const result = await resolveAnalysisResult(item, bridge, treeProvider);
        if (!result) {
            return;
        }
        const tableName = sanitizeTableName(result.file_name);
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Generating all SQL statements...' }, async () => {
            try {
                const config = (0, configuration_1.getConfig)();
                const ddl = await bridge.generateAll({
                    metadata: result.metadata,
                    table_name: tableName,
                    location: result.file_path,
                });
                sqlPreviewPanel_1.SqlPreviewPanel.show(context.extensionUri, ddl, result.file_name, config.targetPlatform);
            }
            catch (err) {
                vscode.window.showErrorMessage(`Generation failed: ${errorMessage(err)}`);
            }
        });
    }));
    // Preview file data
    context.subscriptions.push(vscode.commands.registerCommand('efd.previewData', async (itemOrUri) => {
        let filePath;
        if (itemOrUri instanceof treeDataProvider_1.AnalyzedFileItem) {
            filePath = itemOrUri.filePath;
        }
        else {
            filePath = await resolveFilePath(itemOrUri);
        }
        if (!filePath) {
            return;
        }
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Loading preview...' }, async () => {
            try {
                const config = (0, configuration_1.getConfig)();
                const preview = await bridge.previewData(filePath, config.maxPreviewRows);
                const doc = await vscode.workspace.openTextDocument({
                    content: JSON.stringify(preview, null, 2),
                    language: 'json',
                });
                await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
            }
            catch (err) {
                vscode.window.showErrorMessage(`Preview failed: ${errorMessage(err)}`);
            }
        });
    }));
    // Set target platform
    context.subscriptions.push(vscode.commands.registerCommand('efd.setPlatform', async () => {
        const items = Object.entries(configuration_1.PLATFORM_LABELS).map(([value, label]) => ({
            label,
            value,
            picked: value === (0, configuration_1.getConfig)().targetPlatform,
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
    }));
    // Clear results
    context.subscriptions.push(vscode.commands.registerCommand('efd.clearResults', () => {
        treeProvider.clear();
    }));
    // Refresh tree
    context.subscriptions.push(vscode.commands.registerCommand('efd.refreshTree', () => {
        treeProvider.refresh();
    }));
    // Copy SQL to clipboard
    context.subscriptions.push(vscode.commands.registerCommand('efd.copySQL', async (item) => {
        const result = await resolveAnalysisResult(item, bridge, treeProvider);
        if (!result) {
            return;
        }
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
        }
        catch (err) {
            vscode.window.showErrorMessage(`Copy failed: ${errorMessage(err)}`);
        }
    }));
    // Remove analyzed file
    context.subscriptions.push(vscode.commands.registerCommand('efd.removeAnalyzedFile', (item) => {
        if (item) {
            treeProvider.removeResult(item.filePath);
        }
    }));
    // Export results
    context.subscriptions.push(vscode.commands.registerCommand('efd.exportResults', async () => {
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
        if (!saveUri) {
            return;
        }
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Exporting...' }, async () => {
            try {
                const isSql = saveUri.fsPath.endsWith('.sql');
                const parts = [];
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
                    }
                    else {
                        parts.push(JSON.stringify({ file: result, ddl }, null, 2));
                    }
                }
                const content = isSql ? parts.join('\n') : `[${parts.join(',\n')}]`;
                const encoder = new TextEncoder();
                await vscode.workspace.fs.writeFile(saveUri, encoder.encode(content));
                vscode.window.showInformationMessage(`Exported ${allResults.length} file(s) to ${path.basename(saveUri.fsPath)}`);
            }
            catch (err) {
                vscode.window.showErrorMessage(`Export failed: ${errorMessage(err)}`);
            }
        });
    }));
}
async function resolveFilePath(uri) {
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
async function resolveAnalysisResult(itemOrUri, bridge, treeProvider) {
    if (itemOrUri instanceof treeDataProvider_1.AnalyzedFileItem) {
        return itemOrUri.stored.result;
    }
    let filePath;
    if (itemOrUri instanceof vscode.Uri) {
        filePath = itemOrUri.fsPath;
    }
    else {
        filePath = await resolveFilePath();
    }
    if (!filePath) {
        return undefined;
    }
    // Check if already analyzed
    const existing = treeProvider.getResult(filePath);
    if (existing) {
        return existing;
    }
    // Analyze on the fly
    try {
        const result = await bridge.analyzeFile(filePath);
        treeProvider.addResult(result);
        return result;
    }
    catch (err) {
        vscode.window.showErrorMessage(`Failed to analyze file: ${errorMessage(err)}`);
        return undefined;
    }
}
function sanitizeTableName(fileName) {
    const withoutExt = fileName.replace(/\.[^.]+$/, '');
    return withoutExt.replace(/[^a-zA-Z0-9_]/g, '_').replace(/^(\d)/, '_$1');
}
function errorMessage(err) {
    if (err instanceof Error) {
        return err.message;
    }
    return String(err);
}
//# sourceMappingURL=commands.js.map