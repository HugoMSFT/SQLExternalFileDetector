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
exports.PythonBridge = void 0;
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
const configuration_1 = require("./configuration");
class PythonBridge {
    constructor(outputChannel) {
        this.outputChannel = outputChannel;
    }
    async exec(command, args) {
        const config = (0, configuration_1.getConfig)();
        const pythonPath = config.pythonPath;
        const cmdArgs = ['-m', 'external_file_detection.vscode_bridge', command];
        if (args) {
            cmdArgs.push(args);
        }
        this.outputChannel.appendLine(`[Bridge] ${pythonPath} ${cmdArgs.join(' ')}`);
        return new Promise((resolve, reject) => {
            const proc = (0, child_process_1.spawn)(pythonPath, cmdArgs, {
                cwd: this.findPackageRoot(),
                env: { ...process.env },
                stdio: ['pipe', 'pipe', 'pipe'],
            });
            let stdout = '';
            let stderr = '';
            proc.stdout.on('data', (data) => {
                stdout += data.toString();
            });
            proc.stderr.on('data', (data) => {
                stderr += data.toString();
            });
            proc.on('close', (code) => {
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
                    }
                    else {
                        resolve(result);
                    }
                }
                catch {
                    reject(new Error(`Failed to parse bridge output: ${stdout.substring(0, 500)}`));
                }
            });
            proc.on('error', (err) => {
                reject(new Error(`Failed to start Python: ${err.message}. ` +
                    `Make sure '${pythonPath}' is available and external_file_detection is installed.`));
            });
        });
    }
    findPackageRoot() {
        // Try to find the external_file_detection package root relative to this extension
        const extensionPath = path.resolve(__dirname, '..');
        const projectRoot = path.resolve(extensionPath, '..');
        return projectRoot;
    }
    async analyzeFile(filePath) {
        return await this.exec('analyze_file', filePath);
    }
    async analyzeFolder(folderPath) {
        return await this.exec('analyze_folder', folderPath);
    }
    async generateDDL(params) {
        const config = (0, configuration_1.getConfig)();
        const fullParams = {
            schema_name: config.defaultSchema,
            data_source: config.defaultDataSource,
            file_format: config.defaultFileFormat,
            target_platform: config.targetPlatform,
            credential_name: config.credentialName,
            ...params,
        };
        return await this.exec('generate_ddl', JSON.stringify(fullParams));
    }
    async generateAll(params) {
        const config = (0, configuration_1.getConfig)();
        const fullParams = {
            schema_name: config.defaultSchema,
            data_source: config.defaultDataSource,
            file_format: config.defaultFileFormat,
            target_platform: config.targetPlatform,
            ...params,
        };
        return await this.exec('generate_all', JSON.stringify(fullParams));
    }
    async previewData(filePath, maxRows) {
        const args = maxRows
            ? JSON.stringify({ file_path: filePath, max_rows: maxRows })
            : filePath;
        return await this.exec('preview_data', args);
    }
    async getSupportedTypes() {
        return await this.exec('supported_types');
    }
}
exports.PythonBridge = PythonBridge;
//# sourceMappingURL=pythonBridge.js.map