import sqlite3

def fix_database_v2():
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    
    try:
        # 1. 改用簡單的 '2024-01-01' 作為預設常數，避免 SQLite 報錯
        print("🛠️ 正在嘗試新增 created_at 欄位...")
        cur.execute("ALTER TABLE recurring_tasks ADD COLUMN created_at TEXT DEFAULT '2024-01-01'")
        conn.commit()
        print("✅ 欄位新增成功！")
        
        # 2. 將現有舊資料的日期更新為今天（可選）
        cur.execute("UPDATE recurring_tasks SET created_at = date('now') WHERE created_at = '2024-01-01'")
        conn.commit()
        print("✅ 舊資料日期已初始化。")
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⚠️ 欄位已存在，無需重複新增。")
        else:
            print(f"❌ 發生錯誤: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database_v2()