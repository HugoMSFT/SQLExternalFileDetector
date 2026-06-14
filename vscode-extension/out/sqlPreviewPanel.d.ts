import * as vscode from 'vscode';
import { DDLResult } from './pythonBridge';
export declare class SqlPreviewPanel {
    static currentPanel: SqlPreviewPanel | undefined;
    private static readonly viewType;
    private readonly panel;
    private disposables;
    static show(extensionUri: vscode.Uri, ddlResult: DDLResult, fileName: string, platform: string): SqlPreviewPanel;
    private constructor();
    private openInEditor;
    update(ddlResult: DDLResult, fileName: string, platform: string): void;
    private getHtml;
    dispose(): void;
}
//# sourceMappingURL=sqlPreviewPanel.d.ts.map