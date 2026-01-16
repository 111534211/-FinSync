import sqlite3

def init_db():
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    
    print("🚀 開始初始化完整的資料庫結構...")

    # 1. 使用者表
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, email TEXT)''')

    # 2. 萬年曆事件表
    cur.execute('''CREATE TABLE IF NOT EXISTS calendar_events (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            event_date TEXT,
            type TEXT,      
            category TEXT,
            content TEXT,
            amount REAL DEFAULT 0,
            note TEXT,
            recurring_task_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')

    # 3. 成員表
    cur.execute('''CREATE TABLE IF NOT EXISTS members 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 name TEXT, 
                 user_id INTEGER,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')
    # 4. 費用表
    cur.execute('''CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    description TEXT, 
                    amount REAL, 
                    payer_name TEXT, 
                    date TEXT DEFAULT CURRENT_TIMESTAMP, 
                    note TEXT,
                    currency TEXT DEFAULT 'TWD',
                    foreign_amount REAL DEFAULT 0,
                    folder_id INTEGER)''') # 🟢 這裡可以直接加上 folder_id

    # 5. 分帳細節表
    cur.execute('''CREATE TABLE IF NOT EXISTS split_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    expense_id INTEGER, 
                    member_name TEXT, 
                    FOREIGN KEY(expense_id) REFERENCES expenses(id))''')

    # 6. 固定記帳任務表
    # --- 修正後的第 6 部分：固定記帳任務表 ---
    cur.execute('''CREATE TABLE IF NOT EXISTS recurring_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,           
            category TEXT,
            amount REAL,
            frequency TEXT DEFAULT 'monthly', 
            month_of_year INTEGER DEFAULT 1,
            day_of_period INTEGER, 
            content TEXT,
            last_processed TEXT,
            created_at DATE DEFAULT (date('now')), -- 🟢 新增：預設存入今天日期 (YYYY-MM-DD)
            FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    try:
        cur.execute("ALTER TABLE recurring_tasks ADD COLUMN created_at DATE DEFAULT (date('now'))")
    except sqlite3.OperationalError: pass

    # 7. 旅遊行程資料夾表 (確保在關閉連線前執行)
    cur.execute('''CREATE TABLE IF NOT EXISTS travel_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    folder_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id))''')

    # 🟢 補丁區：確保舊資料表升級 (必須在 conn.close 之前！)
    try:
        cur.execute("ALTER TABLE calendar_events ADD COLUMN recurring_task_id INTEGER")
    except sqlite3.OperationalError: pass

    try:
        cur.execute("ALTER TABLE expenses ADD COLUMN folder_id INTEGER")
    except sqlite3.OperationalError: pass



    # 8. 旅遊行程/AI 建議表 (trips 與 travel_history)
    cur.execute('''CREATE TABLE IF NOT EXISTS trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    destination TEXT NOT NULL,
                    days INTEGER,
                    start_date TEXT,
                    plan_json TEXT, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id))''')

    # 🟢 增加這一段，解決你之前的報錯
    cur.execute('''CREATE TABLE IF NOT EXISTS travel_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    destination TEXT,
                    date TEXT,
                    plan_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id))''')


    # 🧹 清理與提交
    cur.execute("DELETE FROM calendar_events WHERE note = '🔄 系統自動排程'")
    
    conn.commit()
    conn.close() # 🚩 這是最後一步，關閉後就不能再 execute 了
    print("✅ 資料庫初始化成功！")


if __name__ == "__main__":
    init_db()