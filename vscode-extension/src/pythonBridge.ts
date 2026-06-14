import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as path from 'path';
import { getConfig } from './configuration';

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

export class PythonBridge {
    private outputChannel: vscode.OutputChannel;

    constructor(outputChannel: vscode.OutputChannel) {
        this.outputChannel = outputChannel;
    }

    private async exec(command: string, args?: string): Promise<unknown> {
        const config = getConfig();
        const pythonPath = config.pythonPath;

        const cmdArgs = ['-m', 'external_file_detection.vscode_bridge', command];
        if (args) {
            cmdArgs.push(args);
        }

        this.outputChannel.appendLine(`[Bridge] ${pythonPath} ${cmdArgs.join(' ')}`);

        return new Promise((resolve, reject) => {
            const proc = spawn(pythonPath, cmdArgs, {
                cwd: this.findPackageRoot(),
                env: { ...process.env },
                stdio: ['pipe', 'pipe', 'pipe'],
            });

            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data: Buffer) => {
                stdout += data.toString();
            });

            proc.stderr.on('data', (data: Buffer) => {
                stderr += data.toString();
            });

            proc.on('close', (code: number | null) => {
                if (stderr) {
                    this.outputChannel.appendLine(`[Bridge stderr] ${stderr}`);
                }

                if (code !== 0) {
                    reject(new Error(`Python bridge exited with code ${code}: ${stderr || stdout}`));
                    return;
                }

                try {
                    const result = JSON.parse(stdout);
                    if (result.error) {
                        reject(new Error(result.error));
                    } else {
                        resolve(result);
                    }
                } catch {
                    reject(new Error(`Failed to parse bridge output: ${stdout.substring(0, 500)}`));
                }
            });

            proc.on('error', (err: Error) => {
                reject(new Error(
                    `Failed to start Python: ${err.message}. ` +
                    `Make sure '${pythonPath}' is available and external_file_detection is installed.`
                ));
            });
        });
    }

    private findPackageRoot(): string {
        // Try to find the external_file_detection package root relative to this extension
        const extensionPath = path.resolve(__dirname, '..');
        const projectRoot = path.resolve(extensionPath, '..');
        return projectRoot;
    }

    async analyzeFile(filePath: string): Promise<AnalysisResult> {
        return await this.exec('analyze_file', filePath) as AnalysisResult;
    }

    async analyzeFolder(folderPath: string): Promise<FolderAnalysisResult> {
        return await this.exec('analyze_folder', folderPath) as FolderAnalysisResult;
    }

    async generateDDL(params: {
        metadata: Record<string, unknown>;
        table_name: string;
        schema_name?: string;
        data_source?: string;
        file_format?: string;
        location?: string;
        target_platform?: string;
        credential_name?: string;
    }): Promise<DDLResult> {
        const config = getConfig();
        const fullParams = {
            schema_name: config.defaultSchema,
            data_source: config.defaultDataSource,
            file_format: config.defaultFileFormat,
            target_platform: config.targetPlatform,
            credential_name: config.credentialName,
            ...params,
        };
        return await this.exec('generate_ddl', JSON.stringify(fullParams)) as DDLResult;
    }

    async generateAll(params: {
        metadata: Record<string, unknown>;
        table_name: string;
        schema_name?: string;
        data_source?: string;
        file_format?: string;
        location?: string;
        target_platform?: string;
    }): Promise<DDLResult> {
        const config = getConfig();
        const fullParams = {
            schema_name: config.defaultSchema,
            data_source: config.defaultDataSource,
            file_format: config.defaultFileFormat,
            target_platform: config.targetPlatform,
            ...params,
        };
        return await this.exec('generate_all', JSON.stringify(fullParams)) as DDLResult;
    }

    async previewData(filePath: string, maxRows?: number): Promise<PreviewResult> {
        const args = maxRows
            ? JSON.stringify({ file_path: filePath, max_rows: maxRows })
            : filePath;
        return await this.exec('preview_data', args) as PreviewResult;
    }

    async getSupportedTypes(): Promise<{ types: Array<{ extension: string; name: string }> }> {
        return await this.exec('supported_types') as { types: Array<{ extension: string; name: string }> };
    }
}
