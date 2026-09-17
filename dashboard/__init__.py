"""
API Sentinel Dashboard Package
"""

from dashboard.app import app, get_active_report, set_active_report

__all__ = ["app", "get_active_report", "set_active_report"]
