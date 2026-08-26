"""
Page Object 模块
"""
from .workbench_page import WorkbenchPage, METRIC_CATEGORIES, WARNING_CARDS
from .patient_page import PatientPage
from .followup_page import FollowupPage

__all__ = [
    "WorkbenchPage",
    "METRIC_CATEGORIES",
    "WARNING_CARDS",
    "PatientPage",
    "FollowupPage",
]
