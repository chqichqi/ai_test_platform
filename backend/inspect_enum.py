#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app.core.models.web_ui_test import WebUITestCase, BrowserType, ViewportSize
from sqlalchemy import inspect

print("=== WebUITestCase browser column ===")
col = WebUITestCase.__table__.columns['browser']
print(f"Column type: {col.type}")
print(f"Column type.enum_class: {col.type.enum_class}")
print(f"Column type.enums: {col.type.enums}")
print(f"Column type._values_callable: {getattr(col.type, '_values_callable', None)}")
print(f"Column type._object_lookup: {getattr(col.type, '_object_lookup', None)}")
print(f"Column type._value_lookup: {getattr(col.type, '_value_lookup', None)}")

print("\n=== BrowserType enum ===")
for member in BrowserType:
    print(f"  {member.name} = {member.value!r}")

print("\n=== ViewportSize column ===")
col2 = WebUITestCase.__table__.columns['viewport_size']
print(f"Column type: {col2.type}")
print(f"Column type.enum_class: {col2.type.enum_class}")
print(f"Column type.enums: {col2.type.enums}")

print("\n=== ViewportSize enum ===")
for member in ViewportSize:
    print(f"  {member.name} = {member.value!r}")

# Test conversion
print("\n=== Testing conversion ===")
from sqlalchemy import create_engine
from sqlalchemy.sql import column
engine = create_engine('sqlite:///:memory:')
conn = engine.connect()
# Get the dialect
dialect = engine.dialect
# Simulate bind parameter processing
import sqlalchemy as sa
from sqlalchemy import types
import sqlalchemy.sql.sqltypes as sqltypes

enum_type = col.type
print(f"enum_type.python_type: {enum_type.python_type}")
print(f"enum_type._valid_lookup: {getattr(enum_type, '_valid_lookup', None)}")

# Try to process a value
print("\nProcessing BrowserType.CHROME:")
try:
    result = enum_type.process_bind_param(BrowserType.CHROME, dialect)
    print(f"process_bind_param result: {result!r}")
except Exception as e:
    print(f"Error: {e}")

print("\nProcessing 'CHROME' string:")
try:
    result = enum_type.process_bind_param('CHROME', dialect)
    print(f"process_bind_param result: {result!r}")
except Exception as e:
    print(f"Error: {e}")

print("\nProcessing 'chrome' string:")
try:
    result = enum_type.process_bind_param('chrome', dialect)
    print(f"process_bind_param result: {result!r}")
except Exception as e:
    print(f"Error: {e}")