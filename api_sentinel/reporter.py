"""
API Sentinel - Terminal & CMD Output Formatter
Renders real-time schema drift alerts and tables using Rich.
"""

from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from api_sentinel.diff_engine import DriftIssue, DriftSeverity


class SentinelReporter:
    """Rich terminal output reporter for API Sentinel schema drift alerts."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def report_drift(self, issues: List[DriftIssue]):
        """Prints a styled Rich alert panel and table when schema drift is detected."""
        if not issues:
            return

        table = Table(
            title="[bold underline cyan]🛡️ API Sentinel - Schema Drift Detected[/bold underline cyan]",
            show_header=True,
            header_style="bold magenta",
            border_style="dim white",
            expand=True,
        )

        table.add_column("Severity", style="bold", width=10, justify="center")
        table.add_column("Type", style="bold yellow", width=26)
        table.add_column("Location", style="cyan", width=15)
        table.add_column("Method & Path", style="green", width=22)
        table.add_column("Details", style="white")

        for issue in issues:
            severity_style = self._get_severity_style(issue.severity)
            severity_badge = f"[{severity_style}]{issue.severity.value}[/{severity_style}]"
            endpoint = f"[bold]{issue.method}[/bold] {issue.path}"

            details = issue.message
            if issue.expected is not None or issue.actual is not None:
                details += f"\n  [dim]Expected:[/dim] {issue.expected} | [dim]Actual:[/dim] {issue.actual}"

            table.add_row(
                severity_badge,
                issue.issue_type.value,
                issue.location,
                endpoint,
                details,
            )

        panel = Panel(
            table,
            title="[bold red]🚨 API DRIFT WARNING[/bold red]",
            subtitle="[dim]API Sentinel Middleware[/dim]",
            border_style="red",
            expand=True,
        )
        self.console.print(panel)

    def report_clean(self, method: str, path: str, status_code: int):
        """Prints a subtle confirmation when a request matches the OpenAPI spec cleanly."""
        text = Text()
        text.append("🛡️ API Sentinel: ", style="bold green")
        text.append(f"{method.upper()} {path} ", style="bold white")
        text.append(f"[{status_code}] ", style="cyan")
        text.append("Matched OpenAPI Spec strictly", style="dim green")
        self.console.print(text)

    @staticmethod
    def _get_severity_style(severity: DriftSeverity) -> str:
        if severity == DriftSeverity.ERROR:
            return "bold red"
        if severity == DriftSeverity.WARNING:
            return "bold yellow"
        return "bold cyan"
