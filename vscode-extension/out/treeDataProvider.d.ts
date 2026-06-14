import * as vscode from 'vscode';
import { AnalysisResult } from './pythonBridge';
export interface StoredAnalysis {
    result: AnalysisResult;
    timestamp: number;
}
type TreeNode = AnalyzedFileItem | MetadataItem;
export declare class AnalyzedFilesProvider implements vscode.TreeDataProvider<TreeNode> {
    private _onDidChangeTreeData;
    readonly onDidChangeTreeData: vscode.Event<void | TreeNode | undefined>;
    private analyzedFiles;
    refresh(): void;
    addResult(result: AnalysisResult): void;
    addResults(results: AnalysisResult[]): void;
    removeResult(filePath: string): void;
    clear(): void;
    getResult(filePath: string): AnalysisResult | undefined;
    getAllResults(): AnalysisResult[];
    getTreeItem(element: TreeNode): vscode.TreeItem;
    getChildren(element?: TreeNode): TreeNode[];
}
export declare class AnalyzedFileItem extends vscode.TreeItem {
    readonly filePath: string;
    readonly stored: StoredAnalysis;
    constructor(filePath: string, stored: StoredAnalysis, collapsibleState: vscode.TreeItemCollapsibleState);
}
declare class MetadataItem extends vscode.TreeItem {
    constructor(label: string, value: string, iconId?: string);
}
export declare class PlatformInfoProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData;
    readonly onDidChangeTreeData: vscode.Event<void | vscode.TreeItem | undefined>;
    refresh(): void;
    getTreeItem(element: vscode.TreeItem): vscode.TreeItem;
    getChildren(): vscode.TreeItem[];
}
export {};
//# sourceMappingURL=treeDataProvider.d.ts.map