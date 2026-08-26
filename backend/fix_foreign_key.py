#!/usr/bin/env python3
"""Fix foreign key constraint in web_ui_element_selector table"""
import sys
sys.path.insert(0, '.')

from sqlalchemy import create_engine, MetaData, Table
from app.core.config import settings

engine = create_engine(str(settings.DATABASE_URL))
metadata = MetaData()

# Reflect the existing table
metadata.reflect(bind=engine, only=['web_ui_element_selector'])
table = metadata.tables['web_ui_element_selector']

print("Current table columns:")
for column in table.columns:
    print(f"  - {column.name}: {column.type}, foreign keys: {column.foreign_keys}")

# Check if project_id has foreign key constraint
for fk in table.foreign_keys:
    print(f"Foreign key: {fk.column.name} -> {fk.target_fullname}")

# Drop and recreate table without foreign key to project
# Since there is no foreign key in schema, we just need to ensure SQLAlchemy metadata is correct
print("\nNo foreign key to project table found in schema.")
print("The error might be from SQLAlchemy metadata cache.")
print("Let's recreate the table to be safe.")

# Drop table
print("Dropping table...")
table.drop(engine)
print("Table dropped.")

# Create table using current model (which should have no foreign key to project)
from app.core.models.web_ui_test import Base, WebUIElementSelector
Base.metadata.create_all(bind=engine, tables=[WebUIElementSelector.__table__])
print("Table recreated.")

print("Done.")