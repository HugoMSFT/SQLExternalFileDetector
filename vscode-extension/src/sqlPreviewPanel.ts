import * as vscode from 'vscode';
import { DDLResult } from './pythonBridge';
import { PLATFORM_LABELS } from './configuration';

export class SqlPreviewPanel {
    public static currentPanel: SqlPreviewPanel | undefined;
    private static readonly viewType = 'efd.sqlPreview';

    private readonly panel: vscode.WebviewPanel;
    private disposables: vscode.Disposable[] = [];

    public static show(
        extensionUri: vscode.Uri,
        ddlResult: DDLResult,
        fileName: string,
        platform: string,
    ): SqlPreviewPanel {
        const column = vscode.ViewColumn.Beside;

        if (SqlPreviewPanel.currentPanel) {
            SqlPreviewPanel.currentPanel.update(ddlResult, fileName, platform);
            SqlPreviewPanel.currentPanel.panel.reveal(column);
            return SqlPreviewPanel.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            SqlPreviewPanel.viewType,
            `SQL: ${fileName}`,
            column,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [extensionUri],
            },
        );

        SqlPreviewPanel.currentPanel = new SqlPreviewPanel(panel, ddlResult, fileName, platform);
        return SqlPreviewPanel.currentPanel;
    }

    private constructor(
        panel: vscode.WebviewPanel,
        ddlResult: DDLResult,
        fileName: string,
        platform: string,
    ) {
        this.panel = panel;
        this.update(ddlResult, fileName, platform);

        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

        this.panel.webview.onDidReceiveMessage(
            (message: { command: string; sql?: string }) => {
                switch (message.command) {
                    case 'copy':
                        if (message.sql) {
                            vscode.env.clipboard.writeText(message.sql);
                            vscode.window.showInformationMessage('SQL copied to clipboard');
                        }
                        break;
                    case 'openInEditor':
                        if (message.sql) {
                            this.openInEditor(message.sql);
                        }
                        break;
                }
            },
            null,
            this.disposables,
        );
    }

    private async openInEditor(sql: string): Promise<void> {
        const doc = await vscode.workspace.openTextDocument({
            content: sql,
            language: 'sql',
        });
        await vscode.window.showTextDocument(doc, vscode.ViewColumn.Active);
    }

    public update(ddlResult: DDLResult, fileName: string, platform: string): void {
        this.panel.title = `SQL: ${fileName}`;
        this.panel.webview.html = this.getHtml(ddlResult, fileName, platform);
    }

    private getHtml(ddlResult: DDLResult, fileName: string, platform: string): string {
        const platformLabel = PLATFORM_LABELS[platform] || platform;
        const nonce = getNonce();

        const statementSections = Object.entries(ddlResult.statements)
            .map(([key, sql]) => {
                const title = formatStatementTitle(key);
                const escapedSql = escapeHtml(sql);
                return `
                <div class="section">
                    <div class="section-header">
                        <h3>${escapeHtml(title)}</h3>
                        <div class="actions">
                            <button class="btn" onclick="copySQL('${escapeAttr(key)}')" title="Copy to clipboard">
                                <span class="codicon">&#x2398;</span> Copy
                            </button>
                            <button class="btn" onclick="openInEditor('${escapeAttr(key)}')" title="Open in SQL editor">
                                <span class="codicon">&#x270E;</span> Open in Editor
                            </button>
                        </div>
                    </div>
                    <pre class="sql-code" id="sql-${escapeAttr(key)}"><code>${escapedSql}</code></pre>
                </div>`;
            })
            .join('\n');

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
    <style nonce="${nonce}">
        :root {
            --bg: var(--vscode-editor-background);
            --fg: var(--vscode-editor-foreground);
            --border: var(--vscode-panel-border);
            --btn-bg: var(--vscode-button-background);
            --btn-fg: var(--vscode-button-foreground);
            --btn-hover: var(--vscode-button-hoverBackground);
            --code-bg: var(--vscode-textCodeBlock-background);
            --header-bg: var(--vscode-sideBarSectionHeader-background);
        }

        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--fg);
            background: var(--bg);
            padding: 16px;
            margin: 0;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }

        .header h2 { margin: 0; }

        .badge {
            background: var(--btn-bg);
            color: var(--btn-fg);
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.85em;
        }

        .section {
            margin-bottom: 20px;
            border: 1px solid var(--border);
            border-radius: 4px;
            overflow: hidden;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            background: var(--header-bg);
        }

        .section-header h3 {
            margin: 0;
            font-size: 0.95em;
        }

        .actions { display: flex; gap: 6px; }

        .btn {
            background: var(--btn-bg);
            color: var(--btn-fg);
            border: none;
            padding: 4px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.85em;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .btn:hover { background: var(--btn-hover); }

        .sql-code {
            margin: 0;
            padding: 12px;
            background: var(--code-bg);
            overflow-x: auto;
            font-family: var(--vscode-editor-font-family);
            font-size: var(--vscode-editor-font-size);
            line-height: 1.5;
            white-space: pre;
            tab-size: 4;
        }

        .copy-all {
            margin-top: 16px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h2>${escapeHtml(fileName)}</h2>
        <span class="badge">${escapeHtml(platformLabel)}</span>
    </div>

    ${statementSections}

    <div class="copy-all">
        <button class="btn" onclick="copyAll()">Copy All Statements</button>
        <button class="btn" onclick="openAllInEditor()">Open All in Editor</button>
    </div>

    <script nonce="${nonce}">
        const vscode = acquireVsCodeApi();

        const statements = ${JSON.stringify(ddlResult.statements)};

        function copySQL(key) {
            vscode.postMessage({ command: 'copy', sql: statements[key] });
        }

        function openInEditor(key) {
            vscode.postMessage({ command: 'openInEditor', sql: statements[key] });
        }

        function copyAll() {
            const all = Object.values(statements).join('\\n\\nGO\\n\\n');
            vscode.postMessage({ command: 'copy', sql: all });
        }

        function openAllInEditor() {
            const all = Object.values(statements).join('\\n\\nGO\\n\\n');
            vscode.postMessage({ command: 'openInEditor', sql: all });
        }
    </script>
</body>
</html>`;
    }

    public dispose(): void {
        SqlPreviewPanel.currentPanel = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            const d = this.disposables.pop();
            if (d) { d.dispose(); }
        }
    }
}

function getNonce(): string {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttr(text: string): string {
    return text.replace(/['"\\]/g, '\\$&');
}

function formatStatementTitle(key: string): string {
    const map: Record<string, string> = {
        create_table: 'CREATE TABLE',
        external_table: 'CREATE EXTERNAL TABLE',
        external_file_format: 'CREATE EXTERNAL FILE FORMAT',
        openrowset: 'OPENROWSET',
        bulk_insert: 'BULK INSERT',
        copy_into: 'COPY INTO',
        json_functions: 'JSON Functions (OPENJSON)',
        for_json_path: 'FOR JSON PATH',
        best_practices: 'Best Practices',
        credential_setup: 'Credential & Data Source Setup',
        complete_ddl: 'Complete DDL Script',
    };
    return map[key] || key.replace(/_/g, ' ').toUpperCase();
}
