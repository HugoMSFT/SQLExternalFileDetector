import * as vscode from 'vscode';
import * as path from 'path';
import { AnalysisResult } from './pythonBridge';

export interface StoredAnalysis {
    result: AnalysisResult;
    timestamp: number;
}

type TreeNode = AnalyzedFileItem | MetadataItem;

export class AnalyzedFilesProvider implements vscode.TreeDataProvider<TreeNode> {
    private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private analyzedFiles: Map<string, StoredAnalysis> = new Map();

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    addResult(result: AnalysisResult): void {
        this.analyzedFiles.set(result.file_path, {
            result,
            timestamp: Date.now(),
        });
        this.refresh();
    }

    addResults(results: AnalysisResult[]): void {
        for (const result of results) {
            this.analyzedFiles.set(result.file_path, {
                result,
                timestamp: Date.now(),
            });
        }
        this.refresh();
    }

    removeResult(filePath: string): void {
        this.analyzedFiles.delete(filePath);
        this.refresh();
    }

    clear(): void {
        this.analyzedFiles.clear();
        this.refresh();
    }

    getResult(filePath: string): AnalysisResult | undefined {
        return this.analyzedFiles.get(filePath)?.result;
    }

    getAllResults(): AnalysisResult[] {
        return Array.from(this.analyzedFiles.values()).map(s => s.result);
    }

    getTreeItem(element: TreeNode): vscode.TreeItem {
        return element;
    }

    getChildren(element?: TreeNode): TreeNode[] {
        if (!element) {
            // Root level — show analyzed files
            return Array.from(this.analyzedFiles.entries()).map(
                ([filePath, stored]) => new AnalyzedFileItem(filePath, stored, vscode.TreeItemCollapsibleState.Collapsed)
            );
        }

        // Children — show metadata properties
        if (!(element instanceof AnalyzedFileItem)) { return []; }

        const metadata = element.stored.result.metadata;
        const items: TreeNode[] = [];

        const addProp = (label: string, value: unknown) => {
            if (value !== undefined && value !== null && value !== '') {
                items.push(new MetadataItem(label, String(value)));
            }
        };

        addProp('Type', element.stored.result.file_type);
        addProp('Encoding', metadata.encoding);
        addProp('Row Count', metadata.row_count);
        addProp('Columns', Array.isArray(metadata.columns) ? (metadata.columns as unknown[]).length : undefined);
        addProp('Delimiter', metadata.delimiter);
        addProp('Has Header', metadata.has_header);
        addProp('File Size', formatFileSize(metadata.file_size as number | undefined));
        addProp('Compression', metadata.compression);

        // Show column details
        if (Array.isArray(metadata.columns)) {
            for (const col of metadata.columns as Array<Record<string, unknown>>) {
                const name = col.name || col.column_name || 'unknown';
                const dtype = col.data_type || col.type || 'unknown';
                const nullable = col.nullable !== false ? '?' : '';
                items.push(new MetadataItem(`  ${name}`, `${dtype}${nullable}`, 'symbol-field'));
            }
        }

        return items;
    }
}

function formatFileSize(bytes: number | undefined): string | undefined {
    if (bytes === undefined || bytes === null) { return undefined; }
    if (bytes < 1024) { return `${bytes} B`; }
    if (bytes < 1024 * 1024) { return `${(bytes / 1024).toFixed(1)} KB`; }
    if (bytes < 1024 * 1024 * 1024) { return `${(bytes / (1024 * 1024)).toFixed(1)} MB`; }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export class AnalyzedFileItem extends vscode.TreeItem {
    constructor(
        public readonly filePath: string,
        public readonly stored: StoredAnalysis,
        collapsibleState: vscode.TreeItemCollapsibleState,
    ) {
        const fileName = path.basename(filePath);
        super(fileName, collapsibleState);

        this.description = stored.result.file_type.toUpperCase();
        this.tooltip = `${filePath}\nType: ${stored.result.file_type}`;
        this.contextValue = 'analyzedFile';
        this.iconPath = getFileIcon(stored.result.file_type);

        this.command = {
            command: 'efd.generateDDL',
            title: 'Generate SQL DDL',
            arguments: [this],
        };
    }
}

class MetadataItem extends vscode.TreeItem {
    constructor(label: string, value: string, iconId?: string) {
        super(`${label}: ${value}`, vscode.TreeItemCollapsibleState.None);
        this.iconPath = new vscode.ThemeIcon(iconId || 'symbol-property');
    }
}

function getFileIcon(fileType: string): vscode.ThemeIcon {
    switch (fileType) {
        case 'csv':
        case 'tsv':
            return new vscode.ThemeIcon('table');
        case 'json':
        case 'jsonl':
        case 'ndjson':
            return new vscode.ThemeIcon('json');
        case 'parquet':
        case 'orc':
            return new vscode.ThemeIcon('file-binary');
        case 'delta':
            return new vscode.ThemeIcon('layers');
        case 'iceberg':
            return new vscode.ThemeIcon('globe');
        case 'xlsx':
        case 'xls':
            return new vscode.ThemeIcon('file-media');
        case 'txt':
            return new vscode.ThemeIcon('file-text');
        default:
            return new vscode.ThemeIcon('file');
    }
}

export class PlatformInfoProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(): vscode.TreeItem[] {
        const cfg = vscode.workspace.getConfiguration('externalFileDetection');
        const platform = cfg.get<string>('targetPlatform', 'sql_server_2022');
        const dataSource = cfg.get<string>('defaultDataSource', 'MyExternalDataSource');
        const schema = cfg.get<string>('defaultSchema', 'dbo');

        const items: vscode.TreeItem[] = [];

        const platformItem = new vscode.TreeItem(`Platform: ${formatPlatform(platform)}`);
        platformItem.iconPath = new vscode.ThemeIcon('server');
        platformItem.command = { command: 'efd.setPlatform', title: 'Change Platform' };
        items.push(platformItem);

        const dsItem = new vscode.TreeItem(`Data Source: ${dataSource}`);
        dsItem.iconPath = new vscode.ThemeIcon('database');
        items.push(dsItem);

        const schemaItem = new vscode.TreeItem(`Schema: ${schema}`);
        schemaItem.iconPath = new vscode.ThemeIcon('symbol-namespace');
        items.push(schemaItem);

        return items;
    }
}

function formatPlatform(platform: string): string {
    const map: Record<string, string> = {
        sql_server_2019: 'SQL Server 2019',
        sql_server_2022: 'SQL Server 2022',
        sql_server_2025: 'SQL Server 2025',
        azure_sql_database: 'Azure SQL Database',
        azure_sql_managed_instance: 'Azure SQL MI',
        fabric_sql_database: 'Fabric SQL DB',
    };
    return map[platform] || platform;
}
