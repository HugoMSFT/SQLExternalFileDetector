/* ============================================================
   External File Detection – Web UI JavaScript
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
    // ---------- DOM refs ----------
    const tabs        = document.querySelectorAll(".tab");
    const tabContents = document.querySelectorAll(".tab-content");
    const themeToggle = document.getElementById("themeToggle");

    // Upload tab
    const dropZone         = document.getElementById("dropZone");
    const fileInput        = document.getElementById("fileInput");
    const fileList         = document.getElementById("fileList");
    const analyzeUploadBtn = document.getElementById("analyzeUploadBtn");
    const uploadDataSource = document.getElementById("uploadDataSource");

    // Path tab
    const analyzePathBtn = document.getElementById("analyzePathBtn");

    // Manual tab
    const manualFileType      = document.getElementById("manualFileType");
    const csvOptions          = document.getElementById("csvOptions");
    const addColumnBtn        = document.getElementById("addColumnBtn");
    const columnsContainer    = document.getElementById("columnsContainer");
    const generateManualBtn   = document.getElementById("generateManualDdlBtn");

    // Data Source tab
    const generateDsBtn = document.getElementById("generateDsBtn");

    // Results
    const resultsSection = document.getElementById("resultsSection");
    const summaryCards   = document.getElementById("summaryCards");
    const fileResults    = document.getElementById("fileResults");
    const sqlOutput      = document.getElementById("sqlOutput");
    const sqlCode        = document.getElementById("sqlCode");
    const copyBtn        = document.getElementById("copyResultsBtn");
    const downloadBtn    = document.getElementById("downloadSqlBtn");
    const clearBtn       = document.getElementById("clearResultsBtn");

    // Loading
    const loadingOverlay = document.getElementById("loadingOverlay");

    let selectedFiles = [];
    let currentSql = "";

    // ---------- Theme ----------
    const savedTheme = localStorage.getItem("efd-theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);

    themeToggle.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("efd-theme", next);
    });

    // ---------- Tabs ----------
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tabContents.forEach(tc => tc.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
        });
    });

    // ---------- File Upload ----------
    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", e => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));

    dropZone.addEventListener("drop", e => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener("change", () => handleFiles(fileInput.files));

    function handleFiles(files) {
        selectedFiles = Array.from(files);
        renderFileList();
        analyzeUploadBtn.disabled = selectedFiles.length === 0;
    }

    function renderFileList() {
        if (selectedFiles.length === 0) {
            fileList.hidden = true;
            return;
        }
        fileList.hidden = false;
        fileList.innerHTML = selectedFiles.map((f, i) => `
            <div class="file-item">
                <div class="file-item-info">
                    <span>${escapeHtml(f.name)}</span>
                    <span class="file-item-size">${formatBytes(f.size)}</span>
                </div>
                <button class="btn-icon" data-index="${i}" title="Remove">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
        `).join("");

        fileList.querySelectorAll(".btn-icon").forEach(btn => {
            btn.addEventListener("click", () => {
                selectedFiles.splice(parseInt(btn.dataset.index), 1);
                renderFileList();
                analyzeUploadBtn.disabled = selectedFiles.length === 0;
            });
        });
    }

    // ---------- Analyze Upload ----------
    analyzeUploadBtn.addEventListener("click", async () => {
        if (selectedFiles.length === 0) return;

        const formData = new FormData();
        selectedFiles.forEach(f => formData.append("files", f));
        formData.append("data_source", uploadDataSource.value);

        showLoading(true);
        try {
            const resp = await fetch("/api/analyze-upload", { method: "POST", body: formData });
            const data = await resp.json();

            if (!resp.ok) {
                toast(data.error || "Analysis failed", "error");
                return;
            }

            displayUploadResults(data);
            toast(`Analyzed ${data.total} file(s) successfully`, "success");
        } catch (err) {
            toast("Network error: " + err.message, "error");
        } finally {
            showLoading(false);
        }
    });

    function displayUploadResults(data) {
        const results = data.results || [];
        let allSql = "";

        // Summary
        summaryCards.hidden = false;
        document.getElementById("summaryFiles").textContent = results.length;
        const totalSize = results.reduce((sum, r) =>
            sum + (r.metadata?.file_size || 0), 0);
        document.getElementById("summarySize").textContent = formatBytes(totalSize);
        const types = new Set(results.map(r => r.metadata?.file_type).filter(Boolean));
        document.getElementById("summaryTypes").textContent = types.size;

        // File accordion
        fileResults.innerHTML = "";
        results.forEach(r => {
            allSql += `-- File: ${r.file_name}\n`;
            if (r.success && r.sql_ddl) {
                allSql += r.sql_ddl + "\n\n";
            } else {
                allSql += `-- Error: ${r.error || "Unknown error"}\n\n`;
            }
            fileResults.appendChild(createFileResultElement(r));
        });

        currentSql = allSql;
        sqlCode.textContent = allSql;
        sqlOutput.hidden = false;
        resultsSection.hidden = false;
        resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ---------- Analyze Path ----------
    analyzePathBtn.addEventListener("click", async () => {
        const path = document.getElementById("analyzePath").value.trim();
        if (!path) { toast("Please enter a path", "error"); return; }

        const body = {
            path,
            data_source: document.getElementById("pathDataSource").value,
            aws_access_key_id: document.getElementById("awsKey").value || undefined,
            aws_secret_access_key: document.getElementById("awsSecret").value || undefined,
            aws_region: document.getElementById("awsRegion").value || undefined,
            azure_account_name: document.getElementById("azureAccount").value || undefined,
            azure_account_key: document.getElementById("azureKey").value || undefined,
            azure_connection_string: document.getElementById("azureConnStr").value || undefined,
        };

        showLoading(true);
        try {
            const resp = await fetch("/api/analyze-path", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (!resp.ok) {
                toast(data.error || "Analysis failed", "error");
                return;
            }

            displayPathResults(data);
            toast(`Found ${data.files_found || 0} file(s)`, "success");
        } catch (err) {
            toast("Network error: " + err.message, "error");
        } finally {
            showLoading(false);
        }
    });

    function displayPathResults(data) {
        const files = data.files || [];
        let allSql = `-- Location: ${data.location || "N/A"}\n-- Files found: ${data.files_found || 0}\n\n`;

        summaryCards.hidden = false;
        document.getElementById("summaryFiles").textContent = data.files_found || 0;
        document.getElementById("summarySize").textContent = formatBytes(data.summary?.total_size || 0);
        const typeCount = Object.keys(data.summary?.file_types || {}).length;
        document.getElementById("summaryTypes").textContent = typeCount;

        fileResults.innerHTML = "";
        files.forEach(r => {
            const name = r.file_path || "unknown";
            allSql += `-- File: ${name}\n`;
            if (r.sql_ddl) {
                allSql += r.sql_ddl + "\n\n";
            } else if (r.error) {
                allSql += `-- Error: ${r.error}\n\n`;
            }
            fileResults.appendChild(createFileResultElement({
                file_name: name,
                metadata: r.metadata,
                sql_ddl: r.sql_ddl,
                table_name: r.table_name,
                success: !r.error,
                error: r.error,
            }));
        });

        currentSql = allSql;
        sqlCode.textContent = allSql;
        sqlOutput.hidden = false;
        resultsSection.hidden = false;
        resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ---------- Manual DDL ----------
    manualFileType.addEventListener("change", () => {
        csvOptions.style.display = ["csv", "text"].includes(manualFileType.value) ? "flex" : "none";
    });

    addColumnBtn.addEventListener("click", () => {
        const row = document.createElement("div");
        row.className = "column-row";
        row.innerHTML = `
            <input type="text" placeholder="Column name" class="col-name">
            <select class="col-type">
                <option value="int64">INT (BIGINT)</option>
                <option value="int32">INT</option>
                <option value="float64">FLOAT</option>
                <option value="object" selected>NVARCHAR(MAX)</option>
                <option value="bool">BIT</option>
                <option value="datetime64[ns]">DATETIME2</option>
                <option value="date">DATE</option>
            </select>
            <button class="btn btn-icon btn-danger remove-col" title="Remove column">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;
        columnsContainer.appendChild(row);
        attachRemoveHandlers();
    });

    function attachRemoveHandlers() {
        columnsContainer.querySelectorAll(".remove-col").forEach(btn => {
            btn.onclick = () => {
                if (columnsContainer.children.length > 1) {
                    btn.closest(".column-row").remove();
                } else {
                    toast("At least one column is required", "error");
                }
            };
        });
    }
    attachRemoveHandlers();

    generateManualBtn.addEventListener("click", async () => {
        const columns = [];
        columnsContainer.querySelectorAll(".column-row").forEach(row => {
            const name = row.querySelector(".col-name").value.trim();
            const type = row.querySelector(".col-type").value;
            if (name) columns.push({ name, type });
        });

        if (columns.length === 0) { toast("Add at least one column", "error"); return; }

        const body = {
            file_type: manualFileType.value,
            table_name: document.getElementById("manualTableName").value || "ext_table",
            data_source: document.getElementById("manualDataSource").value || undefined,
            location: document.getElementById("manualLocation").value || "",
            columns,
            delimiter: document.getElementById("manualDelimiter").value || ",",
            has_header: document.getElementById("manualHasHeader").checked,
            encoding: document.getElementById("manualEncoding").value,
        };

        showLoading(true);
        try {
            const resp = await fetch("/api/generate-ddl", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (!resp.ok) { toast(data.error || "Generation failed", "error"); return; }

            currentSql = data.sql_ddl;
            summaryCards.hidden = true;
            fileResults.innerHTML = "";
            sqlCode.textContent = currentSql;
            sqlOutput.hidden = false;
            resultsSection.hidden = false;
            resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
            toast("DDL generated successfully", "success");
        } catch (err) {
            toast("Network error: " + err.message, "error");
        } finally {
            showLoading(false);
        }
    });

    // ---------- Data Source DDL ----------
    generateDsBtn.addEventListener("click", async () => {
        const name = document.getElementById("dsName").value.trim();
        const storageType = document.getElementById("dsType").value;
        const location = document.getElementById("dsLocation").value.trim();

        if (!name) { toast("Please enter a data source name", "error"); return; }
        if (!location) { toast("Please enter a location", "error"); return; }

        const body = {
            name,
            storage_type: storageType,
            location,
            credential: document.getElementById("dsCredential").value || undefined,
        };

        showLoading(true);
        try {
            const resp = await fetch("/api/generate-data-source", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (!resp.ok) { toast(data.error || "Generation failed", "error"); return; }

            currentSql = data.sql_ddl;
            summaryCards.hidden = true;
            fileResults.innerHTML = "";
            sqlCode.textContent = currentSql;
            sqlOutput.hidden = false;
            resultsSection.hidden = false;
            resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
            toast("Data source DDL generated", "success");
        } catch (err) {
            toast("Network error: " + err.message, "error");
        } finally {
            showLoading(false);
        }
    });

    // ---------- Result Actions ----------
    copyBtn.addEventListener("click", async () => {
        if (!currentSql) return;
        try {
            await navigator.clipboard.writeText(currentSql);
            toast("Copied to clipboard", "success");
        } catch {
            // Fallback
            const ta = document.createElement("textarea");
            ta.value = currentSql;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            ta.remove();
            toast("Copied to clipboard", "success");
        }
    });

    downloadBtn.addEventListener("click", () => {
        if (!currentSql) return;
        const blob = new Blob([currentSql], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "external_file_detection.sql";
        a.click();
        URL.revokeObjectURL(url);
        toast("Download started", "info");
    });

    clearBtn.addEventListener("click", () => {
        resultsSection.hidden = true;
        summaryCards.hidden = true;
        fileResults.innerHTML = "";
        sqlCode.textContent = "";
        currentSql = "";
    });

    // ---------- Helpers ----------
    function createFileResultElement(result) {
        const el = document.createElement("div");
        el.className = "file-result";

        const type = result.metadata?.file_type || "unknown";
        const badgeClass = "badge-" + type;

        const header = document.createElement("div");
        header.className = "file-result-header";
        header.innerHTML = `
            <span>${escapeHtml(result.file_name || "")}</span>
            <span class="file-result-badge ${badgeClass}">${type}</span>
        `;
        header.addEventListener("click", () => el.classList.toggle("open"));

        const body = document.createElement("div");
        body.className = "file-result-body";

        let bodyHtml = "";

        if (result.metadata) {
            const m = result.metadata;
            bodyHtml += `<div class="metadata-grid">`;
            if (m.file_size != null)    bodyHtml += `<div class="metadata-item"><strong>Size</strong>${formatBytes(m.file_size)}</div>`;
            if (m.row_count != null)    bodyHtml += `<div class="metadata-item"><strong>Rows</strong>${m.row_count.toLocaleString()}</div>`;
            if (m.column_count != null) bodyHtml += `<div class="metadata-item"><strong>Columns</strong>${m.column_count}</div>`;
            if (m.delimiter)            bodyHtml += `<div class="metadata-item"><strong>Delimiter</strong><code>${escapeHtml(m.delimiter)}</code></div>`;
            if (m.encoding)             bodyHtml += `<div class="metadata-item"><strong>Encoding</strong>${m.encoding}</div>`;
            if (m.has_header)           bodyHtml += `<div class="metadata-item"><strong>Header</strong>Yes</div>`;
            if (m.compression)          bodyHtml += `<div class="metadata-item"><strong>Compression</strong>${m.compression}</div>`;
            bodyHtml += `</div>`;

            // Schema table
            if (m.schema && m.schema.length > 0) {
                bodyHtml += `<table class="schema-table"><thead><tr><th>Column</th><th>Detected Type</th></tr></thead><tbody>`;
                m.schema.forEach(col => {
                    const [name, dtype] = Array.isArray(col) ? col : [col.name, col.type];
                    bodyHtml += `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(dtype)}</td></tr>`;
                });
                bodyHtml += `</tbody></table>`;
            }
        }

        if (result.error) {
            bodyHtml += `<p style="color: var(--danger); margin-top: 0.5rem;">Error: ${escapeHtml(result.error)}</p>`;
        }

        if (result.sql_ddl) {
            bodyHtml += `<div class="sql-output" style="margin-top:0.75rem"><pre><code>${escapeHtml(result.sql_ddl)}</code></pre></div>`;
        }

        body.innerHTML = bodyHtml;
        el.appendChild(header);
        el.appendChild(body);
        return el;
    }

    function showLoading(show) {
        loadingOverlay.hidden = !show;
    }

    function toast(message, type = "info") {
        const container = document.getElementById("toastContainer");
        const t = document.createElement("div");
        t.className = `toast toast-${type}`;
        t.textContent = message;
        container.appendChild(t);
        setTimeout(() => {
            t.style.opacity = "0";
            t.style.transition = "opacity 0.3s";
            setTimeout(() => t.remove(), 300);
        }, 3000);
    }

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return "0 B";
        const units = ["B", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + " " + units[i];
    }

    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = String(str);
        return div.innerHTML;
    }
});
