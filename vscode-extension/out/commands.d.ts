import * as vscode from 'vscode';
import { PythonBridge } from './pythonBridge';
import { AnalyzedFilesProvider } from './treeDataProvider';
export declare function registerCommands(context: vscode.ExtensionContext, bridge: PythonBridge, treeProvider: AnalyzedFilesProvider, platformProvider: {
    refresh(): void;
}): void;
//# sourceMappingURL=commands.d.ts.map