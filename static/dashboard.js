/**
 * API Sentinel Developer Dashboard Client Controller
 * Real-Time Telemetry, Schema Drift Monitoring & Dynamic Polling
 */

(function () {
    let lastReportDataJson = "";
    let isPolling = false;
    let pollIntervalId = null;

    // Helper: Escape HTML
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Method badge styling
    function getMethodBadgeClass(method) {
        const m = (method || "").toUpperCase();
        switch (m) {
            case "GET":
                return "bg-primary-container text-on-primary-container";
            case "POST":
                return "bg-emerald-600 text-white";
            case "PUT":
                return "bg-amber-600 text-white";
            case "DELETE":
                return "bg-error text-white";
            case "PATCH":
                return "bg-purple-600 text-white";
            default:
                return "bg-secondary text-white";
        }
    }

    // Status badge styling
    function getStatusBadge(status) {
        const s = (status || "").toUpperCase();
        if (s === "PASSED") {
            return `<span class="bg-secondary-container text-on-secondary-container px-2 py-0.5 rounded text-xs font-bold border border-secondary/20 flex items-center gap-1 w-fit"><span class="material-symbols-outlined text-[12px]">check_circle</span>PASSED</span>`;
        } else if (s === "WARNING") {
            return `<span class="bg-tertiary-container text-on-tertiary-container px-2 py-0.5 rounded text-xs font-bold border border-tertiary/20 flex items-center gap-1 w-fit"><span class="material-symbols-outlined text-[12px]">warning</span>WARNING</span>`;
        } else {
            return `<span class="bg-error-container text-on-error-container px-2 py-0.5 rounded text-xs font-bold border border-error/20 flex items-center gap-1 w-fit"><span class="material-symbols-outlined text-[12px]">error</span>FAILED</span>`;
        }
    }

    // Severity text styling
    function getSeverityFormatted(severity) {
        const sev = (severity || "NONE").toUpperCase();
        if (sev === "ERROR" || sev === "CRITICAL") {
            return `<span class="text-error font-semibold font-code-md">${escapeHtml(sev)}</span>`;
        } else if (sev === "WARNING") {
            return `<span class="text-tertiary font-semibold font-code-md">${escapeHtml(sev)}</span>`;
        } else if (sev === "INFO") {
            return `<span class="text-primary font-code-md">${escapeHtml(sev)}</span>`;
        }
        return `<span class="text-on-surface-variant font-code-md">NONE</span>`;
    }

    // Filter application
    function applyFilters() {
        const searchInput = document.getElementById("global-search-input");
        const methodSelect = document.getElementById("filter-method");
        const statusSelect = document.getElementById("filter-status");
        const tableBody = document.getElementById("endpoint-table-rows");

        if (!tableBody) return;

        const query = (searchInput ? searchInput.value : "").toLowerCase().trim();
        const selectedMethod = methodSelect ? methodSelect.value.toUpperCase() : "ALL";
        const selectedStatus = statusSelect ? statusSelect.value.toUpperCase() : "ALL";

        const rows = tableBody.querySelectorAll("tr.endpoint-row");
        let visibleCount = 0;

        rows.forEach(row => {
            const endpoint = (row.dataset.endpoint || "").toLowerCase();
            const method = (row.dataset.method || "").toUpperCase();
            const status = (row.dataset.status || "").toUpperCase();

            const matchesSearch = !query || endpoint.includes(query) || method.includes(query);
            const matchesMethod = selectedMethod === "ALL" || method === selectedMethod;
            const matchesStatus = selectedStatus === "ALL" || status === selectedStatus;

            if (matchesSearch && matchesMethod && matchesStatus) {
                row.style.display = "";
                visibleCount++;
            } else {
                row.style.display = "none";
            }
        });

        const noResultsRow = document.getElementById("no-results-row");
        if (noResultsRow) {
            noResultsRow.style.display = visibleCount === 0 ? "" : "none";
        }
    }

    // Render / Update DOM from active report JSON
    function updateDashboardUI(report) {
        if (!report) return;

        const results = report.results || [];
        const total = report.summary ? report.summary.total_endpoints : results.length;
        const passed = report.summary ? report.summary.passed_endpoints : results.filter(r => (r.validation_status || "").toUpperCase() === "PASSED").length;
        const warning = report.summary ? report.summary.warning_count : results.filter(r => (r.validation_status || "").toUpperCase() === "WARNING").length;
        const failed = report.summary ? report.summary.failed_endpoints : results.filter(r => (r.validation_status || "").toUpperCase() === "FAILED").length;
        const passRate = total > 0 ? Math.round((passed / total) * 100) + "%" : "—";
        const driftIssues = failed + warning;

        // Update KPI counters
        const elTotal = document.getElementById("metric-total");
        const elPassed = document.getElementById("metric-passed");
        const elWarning = document.getElementById("metric-warning");
        const elFailed = document.getElementById("metric-failed");
        const elPassRate = document.getElementById("metric-pass-rate");
        const elDrift = document.getElementById("metric-drift");

        if (elTotal) elTotal.textContent = total;
        if (elPassed) elPassed.textContent = passed;
        if (elWarning) elWarning.textContent = warning;
        if (elFailed) elFailed.textContent = failed;
        if (elPassRate) elPassRate.textContent = passRate;
        if (elDrift) elDrift.textContent = driftIssues;

        // Update Donut Chart
        const elDonutWheel = document.getElementById("donut-chart-wheel");
        const elDonutTotal = document.getElementById("donut-total-count");
        const elDonutCrit = document.getElementById("donut-crit-count");
        const elDonutWarn = document.getElementById("donut-warn-count");
        const elDonutPass = document.getElementById("donut-pass-count");

        if (elDonutTotal) elDonutTotal.textContent = driftIssues;
        if (elDonutCrit) elDonutCrit.textContent = failed;
        if (elDonutWarn) elDonutWarn.textContent = warning;
        if (elDonutPass) elDonutPass.textContent = passed;

        if (elDonutWheel) {
            if (driftIssues > 0) {
                const failPct = Math.round((failed / driftIssues) * 100);
                const warnPct = Math.round((warning / driftIssues) * 100);
                elDonutWheel.style.background = `conic-gradient(from 0deg, #ba1a1a 0% ${failPct}%, #943700 ${failPct}% ${failPct + warnPct}%, #c3c6d7 ${failPct + warnPct}% 100%)`;
            } else {
                elDonutWheel.style.background = "#c3c6d7";
            }
        }

        // Update Table Rows
        const tableBody = document.getElementById("endpoint-table-rows");
        if (tableBody) {
            let html = "";
            results.forEach((res, idx) => {
                const method = (res.method || "GET").toUpperCase();
                const endpoint = res.endpoint || "/";
                const statusCode = res.status_code || 200;
                const status = (res.validation_status || "PASSED").toUpperCase();
                const severity = res.severity || "NONE";
                const timestamp = res.timestamp ? res.timestamp.replace("T", " ").substring(0, 19) : new Date().toISOString().substring(0, 19);

                html += `
                <tr class="data-table-row hover:bg-surface-container transition-colors endpoint-row"
                    data-endpoint="${escapeHtml(endpoint)}"
                    data-method="${escapeHtml(method)}"
                    data-status="${escapeHtml(status)}"
                    data-severity="${escapeHtml(severity)}">
                  <td class="py-3 pr-4">
                    <span class="${getMethodBadgeClass(method)} px-2 py-0.5 rounded text-xs font-bold">${escapeHtml(method)}</span>
                  </td>
                  <td class="py-3 pr-4 text-on-surface font-semibold font-code-md">${escapeHtml(endpoint)}</td>
                  <td class="py-3 pr-4 text-on-surface-variant font-code-md">${statusCode}</td>
                  <td class="py-3 pr-4">
                    ${getStatusBadge(status)}
                  </td>
                  <td class="py-3 pr-4 text-on-surface-variant">${getSeverityFormatted(severity)}</td>
                  <td class="py-3 pr-4 text-on-surface-variant text-xs font-code-md">${escapeHtml(timestamp)}</td>
                  <td class="py-3">
                    <a href="/endpoint/detail?index=${idx}" class="text-primary hover:underline text-xs font-semibold flex items-center gap-1">
                      Inspect <span class="material-symbols-outlined text-sm">arrow_forward</span>
                    </a>
                  </td>
                </tr>`;
            });

            html += `
            <tr id="no-results-row" style="display: ${results.length === 0 ? "" : "none"};">
              <td colspan="7" class="text-center py-8 text-on-surface-variant">
                ${results.length === 0 ? "No endpoint validation telemetry captured yet. Send requests to see live updates!" : "No endpoint validation results match the selected filters."}
              </td>
            </tr>`;

            tableBody.innerHTML = html;
            applyFilters();
        }

        // Update last updated clock
        const elLastUpdated = document.getElementById("last-updated-text");
        if (elLastUpdated) {
            const now = new Date();
            elLastUpdated.textContent = now.toTimeString().split(" ")[0];
        }
    }

    // Fetch report from server
    async function fetchReport(force = false) {
        try {
            const res = await fetch("/api/report", { cache: "no-store" });
            if (!res.ok) return;
            const text = await res.text();
            if (force || text !== lastReportDataJson) {
                lastReportDataJson = text;
                const data = JSON.parse(text);
                updateDashboardUI(data);
            }
        } catch (err) {
            // Silently handle transient connection loss
            console.debug("Live sync polling error:", err);
        }
    }

    // Start live polling loop
    function startRealTimePolling() {
        if (isPolling) return;
        isPolling = true;
        fetchReport(true);
        pollIntervalId = setInterval(() => {
            fetchReport(false);
        }, 1500);
    }

    document.addEventListener("DOMContentLoaded", () => {
        // Wire search and filter inputs
        const searchInput = document.getElementById("global-search-input");
        const methodSelect = document.getElementById("filter-method");
        const statusSelect = document.getElementById("filter-status");

        if (searchInput) searchInput.addEventListener("input", applyFilters);
        if (methodSelect) methodSelect.addEventListener("change", applyFilters);
        if (statusSelect) statusSelect.addEventListener("change", applyFilters);

        // Manual Refresh Button
        const refreshBtn = document.getElementById("btn-manual-refresh");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", async () => {
                refreshBtn.classList.add("opacity-50");
                await fetchReport(true);
                setTimeout(() => refreshBtn.classList.remove("opacity-50"), 300);
            });
        }

        // Clear History Button
        const clearBtn = document.getElementById("btn-clear-report");
        if (clearBtn) {
            clearBtn.addEventListener("click", async () => {
                if (confirm("Clear all recorded validation history in dashboard?")) {
                    try {
                        await fetch("/api/report/clear", { method: "POST" });
                        await fetchReport(true);
                    } catch (e) {
                        console.error("Failed to clear report:", e);
                    }
                }
            });
        }

        // Start live polling
        startRealTimePolling();
    });
})();
