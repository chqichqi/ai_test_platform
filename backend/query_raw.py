import sqlite3

conn = sqlite3.connect('data/ai_agent_test.db')
cursor = conn.cursor()
cursor.execute("SELECT id, title, test_type FROM test_case WHERE id = ?", ('ef32c563-527d-4beb-93a4-4079add6d903',))
row = cursor.fetchone()
if row:
    print(f"ID: {row[0]}")
    print(f"Title: {row[1]}")
    print(f"Test type: {row[2]}")
else:
    print("Not found")
conn.close()