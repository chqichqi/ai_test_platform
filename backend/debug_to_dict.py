#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app.core.database import SessionLocal
from app.core.models.web_ui_test import WebUITestCase

db = SessionLocal()
try:
    # Get the latest web ui test case
    web_ui_case = db.query(WebUITestCase).order_by(WebUITestCase.created_at.desc()).first()
    if web_ui_case:
        print("WebUITestCase found:", web_ui_case.id)
        data = web_ui_case.to_dict()
        print("Keys:", list(data.keys()))
        if 'test_case' in data:
            val = data['test_case']
            print("test_case value:", val)
            print("test_case type:", type(val))
            if hasattr(val, '__dict__'):
                print("val attributes:", dir(val))
    else:
        print("No WebUITestCase found")
finally:
    db.close()