import sys
sys.path.insert(0, '.')

from app.core.database import init_db, engine
from app.core.logger import setup_logger

setup_logger()

print("Testing init_db...")
try:
    init_db()
    print("init_db succeeded")
except Exception as e:
    print(f"init_db failed: {e}")
    import traceback
    traceback.print_exc()

# Check tables
from sqlalchemy import inspect
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"Tables in database: {tables}")