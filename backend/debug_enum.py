#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app.core.models.web_ui_test import BrowserType, ViewportSize
from sqlalchemy import create_engine, Column, String, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# Simulate the column definition
class TestTable(Base):
    __tablename__ = 'test_enum'
    id = Column(String(36), primary_key=True)
    browser = Column(Enum(BrowserType, name='browser_type_enum', create_type=True))
    viewport = Column(Enum(ViewportSize, name='viewport_size_enum', create_type=True))

# Create engine and table
engine = create_engine('sqlite:///:memory:', echo=True)
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Test 1: assign enum member
print("Testing with BrowserType.CHROME (enum member)")
obj = TestTable(id='1', browser=BrowserType.CHROME, viewport=ViewportSize.DESKTOP_1920x1080)
session.add(obj)
try:
    session.commit()
    print("Success")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    session.rollback()

# Test 2: assign string value
print("\nTesting with browser='chrome' (string)")
obj2 = TestTable(id='2', browser='chrome', viewport='1920x1080')
session.add(obj2)
try:
    session.commit()
    print("Success")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    session.rollback()

# Check column properties
print("\nColumn details:")
print(f"Browser column type: {TestTable.browser.type}")
print(f"Browser column type.enum_class: {TestTable.browser.type.enum_class}")
print(f"Browser column type.enums: {TestTable.browser.type.enums}")
print(f"Browser column type._enums: {TestTable.browser.type._enums}")

# Check enum members
print("\nBrowserType members:")
for member in BrowserType:
    print(f"  {member.name} = {member.value}")

# Check ViewportSize members
print("\nViewportSize members:")
for member in ViewportSize:
    print(f"  {member.name} = {member.value}")