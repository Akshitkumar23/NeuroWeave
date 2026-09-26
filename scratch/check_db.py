import sqlite3, os

db_path = 'storage/neuroweave.db'
print('DB exists:', os.path.exists(db_path))
if os.path.exists(db_path):
    print('DB size:', os.path.getsize(db_path), 'bytes')

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in c.fetchall()]
print('Tables:', tables)

for t in tables:
    c.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'  {t}: {c.fetchone()[0]} rows')

if 'reports' in tables:
    c.execute('SELECT session_id, length(content), confidence_score FROM reports ORDER BY rowid DESC LIMIT 5')
    print('Recent reports (session_id, content_len, confidence):')
    for r in c.fetchall():
        print(' ', r)
    c.execute('SELECT content FROM reports ORDER BY rowid DESC LIMIT 1')
    row = c.fetchone()
    if row and row[0]:
        print('Latest report preview (600 chars):')
        print(row[0][:600])
    else:
        print('Latest content: EMPTY')

conn.close()
