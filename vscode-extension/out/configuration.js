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
exports.PLATFORM_LABELS = void 0;
exports.getConfig = getConfig;
const vscode = __importStar(require("vscode"));
function getConfig() {
    const cfg = vscode.workspace.getConfiguration('externalFileDetection');
    return {
        pythonPath: cfg.get('pythonPath', 'python'),
        targetPlatform: cfg.get('targetPlatform', 'sql_server_2022'),
        defaultDataSource: cfg.get('defaultDataSource', 'MyExternalDataSource'),
        defaultSchema: cfg.get('defaultSchema', 'dbo'),
        defaultFileFormat: cfg.get('defaultFileFormat', ''),
        credentialName: cfg.get('credentialName', ''),
        includeBestPractices: cfg.get('includebestPractices', true),
        maxPreviewRows: cfg.get('maxPreviewRows', 100),
    };
}
exports.PLATFORM_LABELS = {
    sql_server_2019: 'SQL Server 2019',
    sql_server_2022: 'SQL Server 2022',
    sql_server_2025: 'SQL Server 2025',
    azure_sql_database: 'Azure SQL Database',
    azure_sql_managed_instance: 'Azure SQL Managed Instance',
    fabric_sql_database: 'Microsoft Fabric SQL Database',
};
//# sourceMappingURL=configuration.js.map