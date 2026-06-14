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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const pythonBridge_1 = require("./pythonBridge");
const treeDataProvider_1 = require("./treeDataProvider");
const commands_1 = require("./commands");
const sqlPreviewPanel_1 = require("./sqlPreviewPanel");
let outputChannel;
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('External File Detection');
    context.subscriptions.push(outputChannel);
    const bridge = new pythonBridge_1.PythonBridge(outputChannel);
    const treeProvider = new treeDataProvider_1.AnalyzedFilesProvider();
    const platformProvider = new treeDataProvider_1.PlatformInfoProvider();
    // Register tree views
    context.subscriptions.push(vscode.window.registerTreeDataProvider('efd.analyzedFiles', treeProvider), vscode.window.registerTreeDataProvider('efd.platformInfo', platformProvider));
    // Register all commands
    (0, commands_1.registerCommands)(context, bridge, treeProvider, platformProvider);
    // Refresh platform view when configuration changes
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration('externalFileDetection')) {
            platformProvider.refresh();
        }
    }));
    // Status bar item showing current platform
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
    statusBarItem.command = 'efd.setPlatform';
    updateStatusBar(statusBarItem);
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration('externalFileDetection.targetPlatform')) {
            updateStatusBar(statusBarItem);
        }
    }));
    // Clean up webview on deactivate
    context.subscriptions.push({
        dispose: () => {
            sqlPreviewPanel_1.SqlPreviewPanel.currentPanel?.dispose();
        },
    });
    outputChannel.appendLine('External File Detection extension activated');
}
function updateStatusBar(item) {
    const platform = vscode.workspace
        .getConfiguration('externalFileDetection')
        .get('targetPlatform', 'sql_server_2022');
    const shortLabels = {
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
function deactivate() {
    // Cleanup handled by disposables
}
//# sourceMappingURL=extension.js.map