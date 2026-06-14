import * as vscode from 'vscode';
export interface AnalysisResult {
    file_path: string;
    file_name: string;
    file_type: string;
    metadata: Record<string, unknown>;
}
export interface FolderAnalysisResult {
    folder: string;
    files: AnalysisResult[];
    count: number;
}
export interface DDLResult {
    statements: Record<string, string>;
    table_name: string;
    error?: string;
}
export interface PreviewResult {
    columns?: string[];
    rows?: unknown[][];
    data?: Record<string, unknown>[];
    row_count?: number;
    error?: string;
}
export declare class PythonBridge {
    private outputChannel;
    constructor(outputChannel: vscode.OutputChannel);
    private exec;
    private findPackageRoot;
    analyzeFile(filePath: string): Promise<AnalysisResult>;
    analyzeFolder(folderPath: string): Promise<FolderAnalysisResult>;
    generateDDL(params: {
        metadata: Record<string, unknown>;
        table_name: string;
        schema_name?: string;
        data_source?: string;
        file_format?: string;
        location?: string;
        target_platform?: string;
        credential_name?: string;
    }): Promise<DDLResult>;
    generateAll(params: {
        metadata: Record<string, unknown>;
        table_name: string;
        schema_name?: string;
        data_source?: string;
        file_format?: string;
        location?: string;
        target_platform?: string;
    }): Promise<DDLResult>;
    previewData(filePath: string, maxRows?: number): Promise<PreviewResult>;
    getSupportedTypes(): Promise<{
        types: Array<{
            extension: string;
            name: string;
        }>;
    }>;
}
//# sourceMappingURL=pythonBridge.d.ts.map