import sqlite3

conn = sqlite3.connect("raffle.db")
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE participants ADD COLUMN participant_id TEXT")
    print("✅ participant_id бағаны сәтті қосылды!")
except sqlite3.OperationalError:
    print("ℹ️ participant_id бағаны бұрыннан бар.")

conn.commit()
conn.close()
