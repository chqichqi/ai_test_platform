#!/usr/bin/env python3
"""Check foreign keys in WebUIElementSelector"""
import sys
sys.path.insert(0, '.')

from app.core.models.web_ui_test import WebUIElementSelector
from sqlalchemy import inspect

print("WebUIElementSelector columns:")
for col in WebUIElementSelector.__table__.columns:
    fks = list(col.foreign_keys)
    if fks:
        print(f"  {col.name}: {col.type} -> {[fk.target_fullname for fk in fks]}")
    else:
        print(f"  {col.name}: {col.type} (no foreign key)")

print("\nWebUIElementSelector foreign keys:")
for fk in WebUIElementSelector.__table__.foreign_keys:
    print(f"  {fk.parent.name} -> {fk.target_fullname}")

print("\nInspecting table...")
from app.core.database import engine
inspector = inspect(engine)
fks = inspector.get_foreign_keys('web_ui_element_selector')
print("Database foreign keys:")
for fk in fks:
    print(f"  {fk}")