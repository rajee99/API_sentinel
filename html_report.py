"""
API Sentinel - HTML & JSON Report Generator
Generates standalone HTML dashboard reports and exports JSON reports from ValidationReport objects.
"""

import json
import os
from typing import Optional, Union
from jinja2 import Template
from api_sentinel.validation_report import AggregateReport

HTML_TEMPLATE_STRING = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Sentinel - Developer Report</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root {
            --bg-main: #0f172a;
            --bg-sidebar: #0b1120;
            --bg-card: #1e293b;
            --bg-card-hover: #2d3d54;
            --border-color: #334155;
            --border-subtle: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-blue: #3b82f6;
            --status-pass: #22c55e;
            --status-pass-bg: rgba(34, 197, 94, 0.1);
            --status-warn: #f59e0b;
            --status-warn-bg: rgba(245, 158, 11, 0.1);
            --status-fail: #ef4444;
            --status-fail-bg: rgba(239, 68, 68, 0.1);
            --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
            --font-mono: 'Fira Code', monospace;
            --radius-md: 8px;
            --radius-lg: 12px;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            background-color: var(--bg-main);
            color: var(--text-primary);
            font-family: var(--font-sans);
            font-size: 14px;
            line-height: 1.5;
            min-height: 100vh;
        }

        header {
            height: 56px;
            background-color: var(--bg-sidebar);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 1.5rem;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            font-weight: 700;
            font-size: 1.1rem;
            color: var(--text-primary);
        }

        .brand-logo { color: var(--accent-blue); display: flex; align-items: center; }

        .container {
            max-width: 1320px;
            margin: 0 auto;
            padding: 1.75rem 1.5rem;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .kpi-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 1.25rem;
        }

        .kpi-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-secondary);
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .kpi-value {
            font-size: 2rem;
            font-weight: 700;
            margin-top: 0.5rem;
        }

        .val-total { color: var(--accent-blue); }
        .val-passed { color: var(--status-pass); }
        .val-warning { color: var(--status-warn); }
        .val-failed { color: var(--status-fail); }

        .filters-toolbar {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 1rem;
            margin-bottom: 1.5rem;
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }

        .filter-control {
            background-color: var(--bg-main);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.45rem 0.75rem;
            border-radius: var(--radius-md);
            font-size: 0.85rem;
            outline: none;
        }

        .table-panel {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            overflow: hidden;
        }

        table { width: 100%; border-collapse: collapse; text-align: left; }

        th {
            background-color: rgba(11, 17, 32, 0.6);
            color: var(--text-secondary);
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            padding: 0.85rem 1.25rem;
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 0.9rem 1.25rem;
            border-bottom: 1px solid var(--border-subtle);
            font-size: 0.875rem;
        }

        tr:last-child td { border-bottom: none; }
        tr:hover td { background-color: rgba(255, 255, 255, 0.02); }

        .badge-method {
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            font-weight: 600;
        }

        .method-get { background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); }
        .method-post { background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.3); }
        .method-put { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
        .method-delete { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }

        .badge-status {
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .status-passed { background-color: var(--status-pass-bg); color: var(--status-pass); border: 1px solid rgba(34, 197, 94, 0.3); }
        .status-warning { background-color: var(--status-warn-bg); color: var(--status-warn); border: 1px solid rgba(245, 158, 11, 0.3); }
        .status-failed { background-color: var(--status-fail-bg); color: var(--status-fail); border: 1px solid rgba(239, 68, 68, 0.3); }

        .btn-inspect {
            background-color: var(--bg-main);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.35rem 0.75rem;
            border-radius: var(--radius-md);
            cursor: pointer;
            font-size: 0.8rem;
        }

        .btn-inspect:hover { border-color: var(--accent-blue); color: var(--accent-blue); }

        .modal-backdrop {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(11, 17, 32, 0.85); display: none;
            justify-content: center; align-items: center; z-index: 100;
        }

        .modal {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            width: 90%; max-width: 900px; max-height: 85vh;
            display: flex; flex-direction: column; overflow: hidden;
        }

        .modal-header {
            padding: 1.1rem 1.5rem; border-bottom: 1px solid var(--border-color);
            display: flex; justify-content: space-between; align-items: center;
        }

        .modal-body { padding: 1.5rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.25rem; }

        .code-panel {
            background-color: var(--bg-main); border: 1px solid var(--border-color);
            border-radius: var(--radius-md); padding: 1rem; font-family: var(--font-mono); font-size: 0.825rem;
        }
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <span class="brand-logo"><i data-lucide="shield-alert"></i></span>
            <span>API Sentinel Report</span>
        </div>
        <div style="font-size:0.85rem; color: var(--text-secondary);">Generated: {{ report_data.timestamp }}</div>
    </header>

    <div class="container">
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-header">Total Endpoints</div>
                <div class="kpi-value val-total">{{ report_data.summary.total_endpoints }}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">Passed Endpoints</div>
                <div class="kpi-value val-passed">{{ report_data.summary.passed_endpoints }}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">Warning Count</div>
                <div class="kpi-value val-warning">{{ report_data.summary.warning_count }}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-header">Failed Endpoints</div>
                <div class="kpi-value val-failed">{{ report_data.summary.failed_endpoints }}</div>
            </div>
        </div>

        <div class="filters-toolbar">
            <input type="text" id="filter-search" class="filter-control" placeholder="Search route..." style="flex:1;">
            <select id="filter-method" class="filter-control">
                <option value="ALL">All Methods</option>
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="DELETE">DELETE</option>
            </select>
            <select id="filter-status" class="filter-control">
                <option value="ALL">All Statuses</option>
                <option value="PASSED">PASSED</option>
                <option value="WARNING">WARNING</option>
                <option value="FAILED">FAILED</option>
            </select>
        </div>

        <div class="table-panel">
            <table>
                <thead>
                    <tr>
                        <th>Method</th>
                        <th>Endpoint</th>
                        <th>Status Code</th>
                        <th>Status</th>
                        <th>Severity</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="endpoint-table-body">
                </tbody>
            </table>
        </div>
    </div>

    <div class="modal-backdrop" id="detail-modal">
        <div class="modal">
            <div class="modal-header">
                <div id="modal-title" style="font-weight:600; display:flex; align-items:center; gap:0.75rem;">Details</div>
                <button onclick="closeModal()" style="background:transparent; border:none; color:var(--text-secondary); font-size:1.25rem; cursor:pointer;">&times;</button>
            </div>
            <div class="modal-body" id="modal-body"></div>
        </div>
    </div>

    <script>
        const reportData = {{ report_json_raw | safe }};

        function renderTable(results) {
            const tbody = document.getElementById('endpoint-table-body');
            tbody.innerHTML = '';

            if (!results || results.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--text-muted); padding: 2rem;">No endpoints match the filters.</td></tr>';
                return;
            }

            results.forEach((res, index) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="badge-method method-${(res.method || 'GET').toLowerCase()}">${res.method}</span></td>
                    <td style="font-family: var(--font-mono);">${res.endpoint}</td>
                    <td style="font-family: var(--font-mono);">${res.status_code || 200}</td>
                    <td><span class="badge-status status-${(res.validation_status || 'PASSED').toLowerCase()}">${res.validation_status}</span></td>
                    <td><span style="font-weight:600;">${res.severity || 'NONE'}</span></td>
                    <td><button class="btn-inspect" onclick="openModal(${index})">Inspect</button></td>
                `;
                tbody.appendChild(tr);
            });
        }

        function applyFilters() {
            const search = document.getElementById('filter-search').value.toLowerCase();
            const method = document.getElementById('filter-method').value;
            const status = document.getElementById('filter-status').value;

            const filtered = (reportData.results || []).filter(item => {
                const matchesSearch = item.endpoint.toLowerCase().includes(search);
                const matchesMethod = method === 'ALL' || item.method === method;
                const matchesStatus = status === 'ALL' || item.validation_status === status;
                return matchesSearch && matchesMethod && matchesStatus;
            });
            renderTable(filtered);
        }

        function openModal(index) {
            const item = (reportData.results || [])[index];
            if (!item) return;

            document.getElementById('modal-title').innerHTML = `
                <span class="badge-method method-${item.method.toLowerCase()}">${item.method}</span>
                <span>${item.endpoint}</span>
            `;

            let diffsHtml = '<div style="color:var(--text-muted);">No schema diff issues logged.</div>';
            if (item.differences && item.differences.length > 0) {
                diffsHtml = item.differences.map(d => `
                    <div style="background-color:var(--bg-main); border:1px solid var(--border-color); padding:0.75rem; border-radius:6px; margin-bottom:0.5rem;">
                        <strong>[${d.severity || 'INFO'}] ${d.issue_type || 'DRIFT'}</strong>: ${d.message || ''}
                    </div>
                `).join('');
            }

            document.getElementById('modal-body').innerHTML = `
                <div>${diffsHtml}</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">
                    <div>
                        <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-secondary); margin-bottom:0.5rem;">Expected Schema</div>
                        <pre class="code-panel">${JSON.stringify(item.expected_schema || {}, null, 2)}</pre>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-secondary); margin-bottom:0.5rem;">Actual Schema</div>
                        <pre class="code-panel">${JSON.stringify(item.actual_schema || {}, null, 2)}</pre>
                    </div>
                </div>
            `;
            document.getElementById('detail-modal').style.display = 'flex';
        }

        function closeModal() { document.getElementById('detail-modal').style.display = 'none'; }

        document.getElementById('filter-search').addEventListener('input', applyFilters);
        document.getElementById('filter-method').addEventListener('change', applyFilters);
        document.getElementById('filter-status').addEventListener('change', applyFilters);

        renderTable(reportData.results || []);
        if (window.lucide) window.lucide.createIcons();
    </script>
</body>
</html>"""


def generate_html_report(report: Union[AggregateReport, dict], output_path: Optional[str] = None) -> str:
    if isinstance(report, AggregateReport):
        report_data = report.to_dict()
    else:
        report_data = report

    report_json_raw = json.dumps(report_data, indent=2)

    template = Template(HTML_TEMPLATE_STRING)
    html_content = template.render(
        report_data=report_data,
        report_json_raw=report_json_raw,
    )

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    return html_content


def export_json_report(report: Union[AggregateReport, dict], output_path: str, indent: int = 2) -> str:
    if isinstance(report, AggregateReport):
        json_content = report.to_json(indent=indent)
    else:
        json_content = json.dumps(report, indent=indent)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_content)

    return json_content
