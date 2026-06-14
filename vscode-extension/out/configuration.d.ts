export interface EfdConfig {
    pythonPath: string;
    targetPlatform: string;
    defaultDataSource: string;
    defaultSchema: string;
    defaultFileFormat: string;
    credentialName: string;
    includeBestPractices: boolean;
    maxPreviewRows: number;
}
export declare function getConfig(): EfdConfig;
export declare const PLATFORM_LABELS: Record<string, string>;
//# sourceMappingURL=configuration.d.ts.map