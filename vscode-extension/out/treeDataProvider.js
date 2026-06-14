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
exports.PlatformInfoProvider = exports.AnalyzedFileItem = exports.AnalyzedFilesProvider = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
class AnalyzedFilesProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.analyzedFiles = new Map();
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    addResult(result) {
        this.analyzedFiles.set(result.file_path, {
            result,
            timestamp: Date.now(),
        });
        this.refresh();
    }
    addResults(results) {
        for (const result of results) {
            this.analyzedFiles.set(result.file_path, {
                result,
                timestamp: Date.now(),
            });
        }
        this.refresh();
    }
    removeResult(filePath) {
        this.analyzedFiles.delete(filePath);
        this.refresh();
    }
    clear() {
        this.analyzedFiles.clear();
        this.refresh();
    }
    getResult(filePath) {
        return this.analyzedFiles.get(filePath)?.result;
    }
    getAllResults() {
        return Array.from(this.analyzedFiles.values()).map(s => s.result);
    }
    getTreeItem(element) {
        return element;
    }
    getChildren(element) {
        if (!element) {
            // Root level — show analyzed files
            return Array.from(this.analyzedFiles.entries()).map(([filePath, stored]) => new AnalyzedFileItem(filePath, stored, vscode.TreeItemCollapsibleState.Collapsed));
        }
        // Children — show metadata properties
        if (!(element instanceof AnalyzedFileItem)) {
            return [];
        }
        const metadata = element.stored.result.metadata;
        const items = [];
        const addProp = (label, value) => {
            if (value !== undefined && value !== null && value !== '') {
                items.push(new MetadataItem(label, String(value)));
            }
        };
        addProp('Type', element.stored.result.file_type);
        addProp('Encoding', metadata.encoding);
        addProp('Row Count', metadata.row_count);
        addProp('Columns', Array.isArray(metadata.columns) ? metadata.columns.length : undefined);
        addProp('Delimiter', metadata.delimiter);
        addProp('Has Header', metadata.has_header);
        addProp('File Size', formatFileSize(metadata.file_size));
        addProp('Compression', metadata.compression);
        // Show column details
        if (Array.isArray(metadata.columns)) {
            for (const col of metadata.columns) {
                const name = col.name || col.column_name || 'unknown';
                const dtype = col.data_type || col.type || 'unknown';
                const nullable = col.nullable !== false ? '?' : '';
                items.push(new MetadataItem(`  ${name}`, `${dtype}${nullable}`, 'symbol-field'));
            }
        }
        return items;
    }
}
exports.AnalyzedFilesProvider = AnalyzedFilesProvider;
function formatFileSize(bytes) {
    if (bytes === undefined || bytes === null) {
        return undefined;
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    if (bytes < 1024 * 1024 * 1024) {
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
class AnalyzedFileItem extends vscode.TreeItem {
    constructor(filePath, stored, collapsibleState) {
        const fileName = path.basename(filePath);
        super(fileName, collapsibleState);
        this.filePath = filePath;
        this.stored = stored;
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
exports.AnalyzedFileItem = AnalyzedFileItem;
class MetadataItem extends vscode.TreeItem {
    constructor(label, value, iconId) {
        super(`${label}: ${value}`, vscode.TreeItemCollapsibleState.None);
        this.iconPath = new vscode.ThemeIcon(iconId || 'symbol-property');
    }
}
function getFileIcon(fileType) {
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
class PlatformInfoProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren() {
        const cfg = vscode.workspace.getConfiguration('externalFileDetection');
        const platform = cfg.get('targetPlatform', 'sql_server_2022');
        const dataSource = cfg.get('defaultDataSource', 'MyExternalDataSource');
        const schema = cfg.get('defaultSchema', 'dbo');
        const items = [];
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
exports.PlatformInfoProvider = PlatformInfoProvider;
function formatPlatform(platform) {
    const map = {
        sql_server_2019: 'SQL Server 2019',
        sql_server_2022: 'SQL Server 2022',
        sql_server_2025: 'SQL Server 2025',
        azure_sql_database: 'Azure SQL Database',
        azure_sql_managed_instance: 'Azure SQL MI',
        fabric_sql_database: 'Fabric SQL DB',
    };
    return map[platform] || platform;
}
//# sourceMappingURL=treeDataProvider.js.map