#!/usr/bin/env python3
import sqlite3
import os

def list_tables():
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'ai_agent_test.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return []
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("Tables in database:")
    for table in tables:
        print(f"  - {table[0]}")
        
        # Show column names
        cursor.execute(f"PRAGMA table_info({table[0]})")
        columns = cursor.fetchall()
        print(f"    Columns: {[col[1] for col in columns]}")
    
    conn.close()
    return tables

if __name__ == "__main__":
    list_tables()