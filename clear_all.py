import os
import sqlite3

# 1. Дерекқордан барлық қатысушыларды өшіру
conn = sqlite3.connect("raffle.db")
cursor = conn.cursor()
cursor.execute("DELETE FROM participants")
conn.commit()
conn.close()
print("✅ Барлық қатысушы деректері өшірілді.")

# 2. Файлдарды өшіру (папкаларды емес)
folders = ["files", "exports"]
for folder in folders:
    if os.path.exists(folder):
        file_list = os.listdir(folder)
        for file in file_list:
            file_path = os.path.join(folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        print(f"🧹 Файлдар тазартылды: {folder}/")
    else:
        print(f"ℹ️ Папка жоқ: {folder}/")
