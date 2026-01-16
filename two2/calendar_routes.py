import sqlite3, requests, uuid, random
from flask import Blueprint, render_template, request, jsonify, session

calendar_bp = Blueprint('calendar', __name__)
NEWS_API_KEY = "pub_d14ba91d8e3a4ec68c350a1cf837b174"

def get_db():
    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row
    return conn

@calendar_bp.route('/api/get_events')
def get_events():
    date_str = request.args.get('date')
    conn = get_db()
    
    if date_str:
        # 右側清單：回傳該日詳細資料 (包含 category 和 note)
        order_sql = "CASE WHEN type='expense' THEN 1 WHEN type='income' THEN 2 ELSE 3 END"
        rows = conn.execute(f"SELECT * FROM calendar_events WHERE event_date = ? ORDER BY {order_sql}", (date_str,)).fetchall()
    else:
        # 日曆主體：按日期分組計算總額 (這是讓日曆格子顯示 -$100 的關鍵)
        rows = conn.execute("""
            SELECT 
                event_date as start,
                SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as total_exp,
                SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as total_inc,
                MAX(CASE WHEN type='todo' THEN 1 ELSE 0 END) as has_todo
            FROM calendar_events 
            GROUP BY event_date
        """).fetchall()
        
    conn.close()
    return jsonify([dict(row) for row in rows])

@calendar_bp.route('/api/save_event', methods=['POST'])
def save_event():
    try:
        data = request.get_json()
        if not data.get('content'): 
            return jsonify({"status":"error","message":"描述內容不能為空"}), 400
        
        conn = get_db()
        # 🟢 這裡要加入 category 和 note
        category = data.get('category', '其他')
        content = data.get('content')
        amount = data.get('amount', 0)
        note = data.get('note', '')
        
        if data.get('id'): # 🟡 編輯
            conn.execute("""
                UPDATE calendar_events 
                SET category=?, content=?, amount=?, note=? 
                WHERE id=?
            """, (category, content, amount, note, data['id']))
        else: # 🟢 新增
            conn.execute("""
                INSERT INTO calendar_events (id, event_date, type, category, content, amount, note) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), data['date'], data['type'], category, content, amount, note))
            
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@calendar_bp.route('/api/get_news')
def get_news():
    # 增加隨機性，讓使用者每次進來看到的新聞順序不同
    url = f"https://newsdata.io/api/1/news?apikey={NEWS_API_KEY}&q=travel&language=zh"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        results = data.get("results", [])
        random.shuffle(results) # 洗牌
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})