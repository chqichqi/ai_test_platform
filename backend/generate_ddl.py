"""
Generate DDL for WebUIElementSelector
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.schema import CreateTable
from app.core.config import settings
from app.core.models.web_ui_test import WebUIElementSelector
from sqlalchemy import create_engine

engine = create_engine(settings.DATABASE_URL)
table = WebUIElementSelector.__table__
print(str(CreateTable(table).compile(engine)))