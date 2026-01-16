import sqlite3, os
# 強制抓絕對路徑
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trip_tracker.db")
conn = sqlite3.connect(path)
conn.execute("DELETE FROM calendar_events")
conn.commit()
print("💥 已清空資料表，且現在同步已關閉，資料不會復活")
conn.close()

