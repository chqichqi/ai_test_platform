"""
Inspect SQLAlchemy model metadata
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect
from app.core.config import settings
from app.core.models.web_ui_test import WebUIElementSelector

engine = create_engine(settings.DATABASE_URL)
inspector = inspect(engine)

# Check table columns
print("=== Table columns ===")
columns = inspector.get_columns('web_ui_element_selector')
for col in columns:
    print(f"{col['name']}: type={col['type']}, nullable={col.get('nullable', '?')}, default={col.get('default', '?')}")
    if 'foreign_keys' in col:
        print(f"  Foreign keys: {col['foreign_keys']}")

print("\n=== Foreign keys ===")
fks = inspector.get_foreign_keys('web_ui_element_selector')
for fk in fks:
    print(fk)

print("\n=== Model column details ===")
for column in WebUIElementSelector.__table__.columns:
    print(f"{column.name}: {column.type}")
    print(f"  Foreign keys: {column.foreign_keys}")
    print(f"  References: {[fk.target_fullname for fk in column.foreign_keys]}")
    if column.foreign_keys:
        for fk in column.foreign_keys:
            print(f"    FK: {fk.target_fullname}")

print("\n=== Model relationships ===")
for rel in WebUIElementSelector.__mapper__.relationships:
    print(f"{rel.key}: {rel}")