import feedparser
from bs4 import BeautifulSoup
from flask import jsonify
import random
import re  # 導入正則表達式
import sqlite3
import requests
import uuid
from datetime import datetime  # 確保是這樣寫，而不是 import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message
from email.header import Header # 導入編碼處理工具
from database import init_db
import csv
import io
from flask import Response
import google.generativeai as genai
import json
from datetime import date
import os
from urllib.parse import urljoin, urlparse  # 用來處理相對路徑圖片
from flask import jsonify
from collections import defaultdict

# --- 1. 初始化 Flask 實例 ---
app = Flask(__name__)
app.secret_key = "trip_secret_key"

# --- 2. 配置 Email 設定 (請勿更動左邊的字串名稱) ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True

# 🔴 請確保這裡填入的是你的 Gmail 地址
app.config['MAIL_USERNAME'] = 'caijiayu0416@gmail.com'

# 🔴 請填入你產生的 16 位應用程式密碼 (去掉空格)
app.config['MAIL_PASSWORD'] = 'vdvzclcuoyssytmi' 

# 🟢 設定預設寄件者名稱 (這能徹底解決 ASCII 電腦名稱報錯問題)
app.config['MAIL_DEFAULT_SENDER'] = ('FinSync Alert System', 'caijiayu0416@gmail.com')

# --- 3. 初始化 Mail 物件 (只初始化一次) ---
mail = Mail(app)

# 4. 執行資料庫初始化與其他配置
init_db() 
# 設定你的 API Key
# 將下方字串換成你剛剛複製的那串金鑰
# 設定你的 API Key


def get_ai_model():
    """強制使用穩定版 v1 端點，避開 404 錯誤"""
    try:
        # 指定使用 v1 版本而不是 v1beta
        genai.configure(api_key="AIzaSyB_6dLiYab4mmZmWzE-y7ZoNAQzuHfbJFM")
        # 這裡改用 gemini-1.5-flash-latest 
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash'
        )
        return model
    except Exception as e:
        print(f"模型初始化失敗: {e}")
        return None

# 初始化一個全域 model 備用
model = get_ai_model()

# 取得目前 app.py 所在的絕對路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "trip_tracker.db")

# 🟢 改成這段新的：
def get_db_connection():
    # 這裡的名稱必須跟 database.py 裡面的 init_db 檔案名稱「一模一樣」
    conn = sqlite3.connect('trip_tracker.db', timeout=20) 
    conn.row_factory = sqlite3.Row
    return conn

def sync_recurring_to_calendar(uid):
    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # 1. 清理孤兒事件 (對應已刪除的規則)
        cur.execute("""
            DELETE FROM calendar_events 
            WHERE user_id = ? AND recurring_task_id IS NOT NULL 
            AND recurring_task_id NOT IN (SELECT id FROM recurring_tasks)
        """, (uid,)) 

        tasks = cur.execute("SELECT * FROM recurring_tasks WHERE user_id = ?", (uid,)).fetchall()
        current_year = datetime.now().year
        
        for task in tasks:
            # 🟢 取得規則的起始年月 (例如 "2026-02")
            task_start_month = task['created_at'][:7] if task['created_at'] else "1970-01"
            
            # 確保 day 是整數
            try:
                day_val = int(task['day_of_period']) if task['day_of_period'] else 1
            except:
                day_val = 1

            for m in range(1, 13):
                # 🔴 必須先定義 event_month，才能在下面的 if 中比對！
                event_month = f"{current_year}-{m:02d}"
                
                # 🟢 核心判定：如果日曆格子的月份 < 規則起始月份，就跳過
                if event_month < task_start_month:
                    continue

                # 定義完整日期
                event_date = f"{current_year}-{m:02d}-{day_val:02d}"

                # 檢查是否已存在 (不論是正常還是 DELETED)
                exists = cur.execute("""
                    SELECT 1 FROM calendar_events 
                    WHERE recurring_task_id = ? AND event_date = ?
                """, (task['id'], event_date)).fetchone()
                
                if not exists:
                    event_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO calendar_events (id, user_id, event_date, type, category, content, amount, note, recurring_task_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (event_id, uid, event_date, task['type'], task['category'], 
                         task['content'], task['amount'], '🔄 系統自動排程', task['id']))
        
        conn.commit()
    except Exception as e:
        # 這裡會印出具體的錯誤行號，方便偵錯
        import traceback
        traceback.print_exc() 
        print(f"❌ 同步失敗: {e}")
    finally:
        conn.close()

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('calendar_page'))
    return redirect(url_for('login'))

# 1. 確保你有這個用來「顯示頁面」的函數
@app.route('/travel-planner')
def travel_planner():
    return render_template('travel_planner.html')

# 2. 這是你原本處理 Gemini AI 的函數 (維持不變)
@app.route('/generate-travel-plan', methods=['POST'])
def generate_travel_plan():
    # 0. 檢查登入狀態
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"status": "error", "message": "請先登入後再生成計畫"})

    try:
        data = request.json
        dest = data.get('destination')
        days = data.get('days')
        date = data.get('date')

        prompt = f"""
        請針對前往 {dest} 旅遊 {days} 天（日期：{date}）生成建議。
        請嚴格以 JSON 格式回傳，包含：
        "packing_list" (陣列), "customs" (陣列), "weather_forecast" (字串), "outfit_suggestion" (字串)。
        不要包含任何 Markdown 標籤或其餘文字。
        """

        models_to_try = ["models/gemini-2.0-flash", "models/gemini-flash-latest"]
        
        last_error = ""
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                
                if response and response.text:
                    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                    if json_match:
                        res_data = json.loads(json_match.group(0))
                        
                        # 🟢 關鍵步驟：存入資料庫
                        try:
                            conn = sqlite3.connect("trip_tracker.db", timeout=20)
                            conn.execute("""
                                INSERT INTO trips (user_id, destination, days, start_date, plan_json) 
                                VALUES (?, ?, ?, ?, ?)
                            """, (user_id, dest, days, date, json.dumps(res_data, ensure_ascii=False)))
                            conn.commit()
                            conn.close()
                            print(f"✅ 計畫已成功儲存至資料庫 (User: {user_id})")
                        except sqlite3.Error as db_err:
                            print(f"⚠️ 資料庫寫入失敗但 AI 生成成功: {db_err}")

                        return jsonify({
                            "status": "success", 
                            "data": res_data
                        })
            except Exception as e:
                last_error = str(e)
                continue

        return jsonify({"status": "error", "message": f"AI 無法回應: {last_error}"})

    except Exception as e:
        return jsonify({"status": "error", "message": f"系統異常: {str(e)}"})
        
@app.route('/financial-tips')
def financial_tips():
    if 'user_id' not in session:
        return redirect('/login')

    # 1. 避免當掉暫時顯示
    quotes_pool = [
        {"text": "投資自己，是回報率最高的投資。", "author": "華倫·巴菲特"},
        {"text": "你不理財，財不理你。", "author": "民間諺語"},
        {"text": "複利的威力比原子彈還可怕。", "author": "愛因斯坦"},
        {"text": "結餘 ＝ 收入 － 儲蓄，而不是剩下的才存。", "author": "理財金律"},
        {"text": "買入那些讓你感到舒適的資產，而不是興奮的資產。", "author": "伯格"},
        {"text": "自由的代價是自律。", "author": "赫胥黎"},
        {"text": "最好的投資時機是十年前，其次是現在。", "author": "非洲諺語"},
        {"text": "財富不是你賺了多少，而是你留下了多少。", "author": "羅伯特·清崎"},
        {"text": "細小的漏洞也能淹沒整艘大船，注意小額開支。", "author": "富蘭克林"},
        {"text": "耐心是投資中最重要的特質。", "author": "查理·蒙格"}
    ]
    # 每次刷新隨機抓取一則
    selected_quote = random.choice(quotes_pool)

    # 2. YouTube API 抓取 9 部影片
    keywords = ["理財心得", "存錢思維", "投資心法", "被動收入", "致富習慣"]
    target_topic = random.choice(keywords)
    
    videos = []
    try:
        url = f"https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': target_topic,
            'type': 'video',
            'videoEmbeddable': 'true',  # 🟢 只抓取允許在外部網頁播放的影片
            'maxResults': 9,
            'relevanceLanguage': 'zh-Hant',
            'key': YOUTUBE_API_KEY
        }
        res = requests.get(url, params=params).json()
        
        # 清空舊列表重新填充
        videos = [] 
        if 'items' in res:
            for item in res['items']:
                videos.append({
                    "title": item['snippet']['title'],
                    "id": item['id']['videoId'],
                    "thumbnail": item['snippet']['thumbnails']['high']['url'] # 🟢 抓取封面圖
                })
        else:
            # 備用清單
            videos = [{"title": "巴菲特理財建議", "id": "Yv_v0L-36jU"}]
    except Exception as e:
        print(f"YouTube API Error: {e}")
        videos = [{"title": "理財基礎觀念", "id": "Yv_v0L-36jU"}]

    # 將隨機抓取的名言傳給前端
    return render_template('tips.html', 
                           quote_text=selected_quote['text'], 
                           quote_author=selected_quote['author'], 
                           videos=videos, 
                           topic=target_topic)

# --- 新增：讓瀏覽器可以開啟 AI 助手網頁的路由 ---
@app.route('/ai_assistant')
def ai_assistant():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    return render_template('ai_assistant.html')

# 2. 這是行程規劃 API：後台處理邏輯
def verify_address(address):
    if not address or len(address) < 2:
        return False
        
    try:
        # 增加 addressdetails=1 取得詳細資訊
        url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1&addressdetails=1"
        headers = {'User-Agent': 'TravelAssistant/1.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        
        if len(data) > 0:
            place = data[0]
            # 增加權重判斷：如果比分(importance)太低，通常是亂抓的
            # 或者檢查是否為具體類別 (如：place, city, tourism)
            importance = place.get('importance', 0)
            if importance < 0.3: # 重要度太低，判定為找不到明確地點
                return False
            return True
        return False
    except:
        return True


@app.route('/api/ai_financial_advice')
def ai_financial_advice():
    if 'user_id' not in session:
        return jsonify({"error": "請先登入"}), 401

    db = None
    data_summary = ""
    try:
        db = sqlite3.connect('trip_tracker.db')
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        
        # 1. 抓取當月統計 (確保與你的資料表欄位一致)
        this_month = datetime.now().strftime('%Y-%m')
        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM calendar_events 
            WHERE type = 'expense' AND strftime('%Y-%m', replace(event_date, '/', '-')) = ?
            GROUP BY category
        """, (this_month,))
        categories = cursor.fetchall()
        
        data_summary = "\n".join([f"- {c['category']}: ${c['total']}" for c in categories])
        
        if not data_summary:
            return jsonify({"advice": "💡 本月目前沒有支出紀錄，AI 暫時無法分析。請先去萬年曆記帳吧！"})

        # 2. API 設定
        KEY = "AIzaSyB_6dLiYab4mmZmWzE-y7ZoNAQzuHfbJFM"
        prompt = f"你是一位專業的理財顧問。以下是我本月的支出然後全部都是台幣：\n{data_summary}\n請用繁體中文給予200字左右的建議，我應該怎麼調整我的花費或是我可以怎麼做?不要說金額直接根據我的數據給建議越多越好。"
        
        # 嘗試模型清單 (按優先順序)
        models_to_try = ["gemini-1.5-flash", "gemini-pro", "gemini-flash-latest"]
        last_error = ""

        for model_name in models_to_try:
            try:
                api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={KEY}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                
                response = requests.post(api_url, json=payload, timeout=10)
                res_data = response.json()

                if 'candidates' in res_data:
                    ai_text = res_data['candidates'][0]['content']['parts'][0]['text']
                    return jsonify({"advice": ai_text})
                else:
                    last_error = res_data.get('error', {}).get('message', '未知錯誤')
                    print(f"⚠️ 模型 {model_name} 失敗: {last_error}")
            except Exception as e:
                print(f"⚠️ 嘗試 {model_name} 時發生異常: {e}")
                continue

        # 如果所有模型都失敗
        return jsonify({"error": f"AI 暫時無法回應。最後一個錯誤：{last_error}"}), 500

    except Exception as e:
        print(f"❌ 嚴重故障: {str(e)}")
        return jsonify({"error": f"系統異常：{str(e)}"}), 500
    finally:
        if db: db.close()
        
@app.route('/api/generate_itinerary', methods=['POST'])
def generate_itinerary():
    data = request.json
    destination = data.get('destination', '').strip()

    # --- 新增地址驗證 ---
    if not verify_address(destination):
        return jsonify({
            "status": "error", 
            "message": f"找不到地址「{destination}」，請輸入更具體的城市或景點名稱。"
        }), 400
        
@app.route('/api/ai_plan_trip', methods=['POST'])
def ai_plan_trip():
    data = request.json
    dest = data.get('dest', '').strip()
    days = int(data.get('days', 3))
    start_date_str = data.get('start_date')

    if not verify_address(dest):
        return jsonify({"status": "error", "message": f"找不到地點「{dest}」"}), 400

    try:
        KEY = "AIzaSyB_6dLiYab4mmZmWzE-y7ZoNAQzuHfbJFM"
        
        # 🟢 關鍵修正：使用清單中有的 gemini-2.0-flash，並配合 v1beta
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={KEY}"        
        prompt = (
            f"你是一個專業導遊。幫我規劃「{dest}」的行程。\n"
            f"出發日期是：{start_date_str}\n"
            f"總天數：{days} 天。\n"
            f"【規則】：必須從 {start_date_str} 開始順延，每天一筆資料。\n"
            f"只輸出純 JSON 陣列，格式：[{{\"date\": \"YYYY-MM-DD\", \"content\": \"景點描述\", \"category\": \"旅遊\"}}]"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        response = requests.post(api_url, json=payload, timeout=25)
        res_data = response.json()

        # 檢查 API 是否報錯
        if "error" in res_data:
            return jsonify({"status": "error", "message": f"API 錯誤: {res_data['error']['message']}"}), 500

        # 解析回傳內容
        if 'candidates' in res_data:
            res_text = res_data['candidates'][0]['content']['parts'][0]['text']
            # 清洗並解析 JSON
            json_match = re.search(r'\[.*\]', res_text, re.DOTALL)
            final_text = json_match.group(0) if json_match else res_text
            itinerary_data = json.loads(final_text)
        
            # 如果 AI 生成的天數超過使用者選的天數，只截取前面的部分
            if len(itinerary_data) > days:
                itinerary_data = itinerary_data[:days]
                
            return jsonify(itinerary_data)
    
        else:
            return jsonify({"status": "error", "message": "AI 未能產生成果"}), 500

    except Exception as e:
        print(f"❌ 嚴重錯誤: {str(e)}")
        return jsonify({"status": "error", "message": f"系統異常：{str(e)}"}), 500
    
# 支援 UUID 字串刪除的萬能 API
@app.route('/api/delete_event', methods=['POST'])
def delete_calendar_event():
    if 'user_id' not in session: 
        return jsonify({"status": "error", "message": "未登入"}), 401
    
    data = request.get_json()
    e_id = data.get('id')
    uid = session['user_id']

    if not e_id:
        return jsonify({"status": "error", "message": "缺少 ID"}), 400

    conn = get_db_connection()
    try:
        # 🟢 核心修正：不使用 DELETE，而是標記為 DELETED
        # 這樣該 ID 依然存在於資料庫中，sync_recurring_to_calendar 就不會重複新增
        cursor = conn.execute(
            """
            UPDATE calendar_events 
            SET note = 'DELETED' 
            WHERE id = ? AND user_id = ?
            """, 
            (str(e_id).strip(), uid)
        )
        conn.commit()
        
        if cursor.rowcount > 0:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "找不到該筆行程"}), 404
    except Exception as e:
        print(f"❌ 標記刪除失敗: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# 3. 這是記帳解析 API：後台處理邏輯
@app.route('/api/ai_parse_expense', methods=['POST'])
def ai_parse_expense():
    user_input = request.json.get('text', '').strip()
    if not user_input:
        return jsonify({"error": "請輸入文字"}), 400

    # 1. 強化 Prompt，要求 AI 不要廢話
    prompt = (
        f"將以下文字轉換為記帳 JSON 格式：\n「{user_input}」\n"
        f"必須包含以下欄位：\n"
        f"- category: 類別 (如：食物, 交通, 購物)\n"
        f"- content: 項目內容\n"
        f"- amount: 數字金額\n"
        f"【注意】：只回傳 JSON 內容，嚴禁包含 ```json 等任何標籤或解釋。"
    )

    try:
        # 2. 呼叫 Flash 模型 (注意：如果剛才測試失敗，這裡可改為 'gemini-1.5-flash')
        active_model = genai.GenerativeModel('gemini-flash-latest')
        response = active_model.generate_content(prompt)
        
        if not response.text:
            raise Exception("AI 沒有產生任何結果")

        res_text = response.text.strip()
        print(f"DEBUG - AI Raw Response: {res_text}") # 方便你在終端機檢查 AI 說了什麼

        # 3. 強化 JSON 提取 (比 re.sub 更安全的方法)
        # 尋找第一個 { 和最後一個 } 之間的內容
        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if json_match:
            clean_json = json_match.group(0)
        else:
            clean_json = res_text

        # 4. 解析並回傳
        parsed_data = json.loads(clean_json)
        return jsonify(parsed_data)

    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失敗: {res_text}")
        return jsonify({"error": "AI 回傳格式不正確，請再試一次"}), 500
    except Exception as e:
        print(f"❌ 記帳解析故障: {str(e)}")
        return jsonify({"error": f"系統忙碌中: {str(e)}"}), 500
    
    
# --- 2. 萬年曆專用 API ---
@app.route('/calendar')
def calendar_page():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    
    # 1. 執行你的同步邏輯
    sync_recurring_to_calendar(user_id) 
    
    # 2. 🟢 從資料庫抓取屬於這個使用者的行程
    conn = sqlite3.connect("trip_tracker.db", timeout=20)
    conn.row_factory = sqlite3.Row
    # 假設你的行程表叫 trips，且有 user_id 欄位
    trips = conn.execute("SELECT * FROM trips WHERE user_id = ?", (user_id,)).fetchall()
    
    # 3. 🟢 抓取 AI 旅遊建議的歷史紀錄 (如果有的話)
    travel_plans = conn.execute("SELECT * FROM trips WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    
    # 4. 將資料傳給 HTML
    return render_template('calendar_home.html', trips=trips, travel_plans=travel_plans)
    
@app.route('/api/analysis_data')
def analysis_data():
    if 'user_id' not in session:
        return jsonify({"error": "未登入"}), 401
    
    uid = session['user_id']
    req_year = request.args.get('year')
    req_month = request.args.get('month')
    
    if req_year and req_month:
        target_month = f"{req_year}-{str(req_month).zfill(2)}"
    else:
        target_month = datetime.now().strftime('%Y-%m')

    db = None
    try:
        db = get_db_connection()
        db.row_factory = sqlite3.Row
        cursor = db.cursor()

        # 1. 摘要數據 (改用 LIKE 並連動 target_month)
        cursor.execute("""
            SELECT 
                IFNULL(SUM(CASE WHEN type = 'income' THEN ABS(amount) ELSE 0 END), 0) as total_inc,
                IFNULL(SUM(CASE WHEN type = 'expense' THEN ABS(amount) ELSE 0 END), 0) as total_exp
            FROM calendar_events 
            WHERE user_id = ? 
              AND (event_date LIKE ? OR replace(event_date, '/', '-') LIKE ?)
              AND (IFNULL(note, '') NOT LIKE '%DELETED%')
        """, (uid, f"{target_month}%", f"{target_month}%"))
        res = cursor.fetchone()
        t_inc, t_exp = (res['total_inc'], res['total_exp']) if res else (0, 0)

        # 2. 分類佔比 (連動 target_month)
        cursor.execute("""
            SELECT category, SUM(ABS(amount)) as total
            FROM calendar_events 
            WHERE user_id = ? AND type = 'expense' 
              AND (event_date LIKE ? OR replace(event_date, '/', '-') LIKE ?)
              AND (IFNULL(note, '') NOT LIKE '%DELETED%')
            GROUP BY category
        """, (uid, f"{target_month}%", f"{target_month}%"))
        category_distribution = [dict(r) for r in cursor.fetchall()]

        # 3. 趨勢圖 (維持近六個月，不需要連動)
        cursor.execute("""
            SELECT strftime('%Y-%m', replace(event_date, '/', '-')) as month_label,
                   SUM(CASE WHEN type = 'expense' THEN ABS(amount) ELSE 0 END) as expense,
                   SUM(CASE WHEN type = 'income' THEN ABS(amount) ELSE 0 END) as income
            FROM calendar_events
            WHERE user_id = ? 
              AND (IFNULL(note, '') NOT LIKE '%DELETED%')
            GROUP BY month_label ORDER BY month_label DESC LIMIT 6
        """, (uid,))
        trend = [dict(r) for r in cursor.fetchall()]
        trend.reverse()

        # 4. 支出排行 Top 5 (修正未命名問題)
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN IFNULL(content, '') = '' THEN category 
                    ELSE content 
                END as display_name,
                category, 
                SUM(ABS(amount)) as total
            FROM calendar_events
            WHERE user_id = ? 
              AND type = 'expense'
              AND (IFNULL(note, '') NOT LIKE '%DELETED%')
              AND (event_date LIKE ? OR replace(event_date, '/', '-') LIKE ?)
            GROUP BY display_name, category
            ORDER BY total DESC
            LIMIT 5
        """, (uid, f"{target_month}%", f"{target_month}%"))
        top_expenses = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT 
                f.id, 
                f.folder_name, 
                COUNT(e.id) as item_count, 
                IFNULL(SUM(ABS(e.amount)), 0) as total_amount
            FROM travel_folders f
            LEFT JOIN expenses e ON f.id = e.folder_id
            WHERE f.user_id = ?
            GROUP BY f.id, f.folder_name
            ORDER BY f.created_at DESC
        """, (uid,))
        folder_summaries = [dict(r) for r in cursor.fetchall()]

        # 🟢 5. 旅遊資料夾小卡數據 (確保這段會執行)
        cursor.execute("""
            SELECT f.id, f.folder_name, COUNT(e.id) as item_count, 
                   IFNULL(SUM(ABS(e.amount)), 0) as total_amount
            FROM travel_folders f
            LEFT JOIN expenses e ON f.id = e.folder_id
            WHERE f.user_id = ?
            GROUP BY f.id, f.folder_name
            ORDER BY f.created_at DESC
        """, (uid,))
        folder_summaries = [dict(r) for r in cursor.fetchall()]

        # 🟢 最終統一回傳所有資料
        return jsonify({
            "summary": {
                "total_inc": t_inc, "total_exp": t_exp,
                "balance": t_inc - t_exp, "target_month": target_month
            },
            "category_distribution": category_distribution,
            "trend": trend,
            "top_expenses": top_expenses,
            "folder_summaries": folder_summaries # 這樣前端才收得到資料
        })

    except Exception as e:
        print(f"❌ Analysis API 崩潰: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if db: db.close()

@app.route('/api/get_news')
def get_news():
    rss_url = "https://news.google.com/rss/search?q=台灣+旅遊+景點&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    try:
        feed = feedparser.parse(rss_url)
        results = []
        
        for entry in feed.entries[:8]:
            title = entry.title.split(' - ')[0]
            link = entry.link
            source = entry.source.get('title', '旅遊快報')
            image_url = None
            
            # --- 策略 1：深度解析 summary 並精確排除 Google 預設圖 ---
            if 'summary' in entry:
                summary_soup = BeautifulSoup(entry.summary, 'html.parser')
                img_tags = summary_soup.find_all('img')
                
                for img in img_tags:
                    src = img.get('src', '')
                    # 🚀 排除邏輯加強：排除 Google 域名的圖片與常見 Logo 關鍵字
                    if "google" in src.lower() or "favicon" in src.lower() or "logo" in src.lower():
                        continue
                    
                    # 排除尺寸太小的圖片 (有些追蹤像素只有 1x1)
                    width = img.get('width', '0')
                    height = img.get('height', '0')
                    if width == '1' or height == '1':
                        continue

                    if src.startswith('http') or src.startswith('//'):
                        image_url = src
                        break

            # --- 策略 2：如果 summary 沒圖，強制抓取原站 OpenGraph 圖 ---
            if not image_url:
                try:
                    h = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Referer': 'https://news.google.com/'
                    }
                    # 增加超時時間到 2.5 秒，給原站更多反應時間
                    r = requests.get(link, timeout=2.5, headers=h, allow_redirects=True)
                    s = BeautifulSoup(r.text, 'html.parser')
                    
                    # 尋找 og:image (這是新聞分享時的大圖)
                    og = s.find('meta', property='og:image') or s.find('meta', name='twitter:image')
                    if og and og.get('content'):
                        image_url = og.get('content')
                except Exception as e:
                    print(f"抓取 {source} 原圖失敗: {e}")

            # --- 策略 3：若以上皆失敗，才用 Unsplash 旅遊圖替代 (確保畫面漂亮) ---
            if not image_url:
                image_url = f"https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800&q=80&sig={random.randint(1, 1000)}"

            results.append({
                "title": title,
                "link": link,
                "source_id": source,
                "image_url": image_url
            })
            
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})
        
# --- 1. 這是儲存/編輯用的 API ---
@app.route('/api/save_event', methods=['POST'])
def save_event():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    
    data = request.get_json()
    e_id = data.get('id')
    date_str = data.get('date')
    e_type = data.get('type', 'expense')
    category = data.get('category', '其他')
    content = str(data.get('content', '')).strip() # 抓取並去空白
    amount_raw = data.get('amount')
    note = data.get('note', '')
    uid = session['user_id']

    # 🔴 防呆 1：檢查內容是否為空
    if not content:
        return jsonify({"status": "error", "message": "請輸入項目描述內容！"}), 400

    # 🔴 防呆 2：檢查日期
    if not date_str:
        return jsonify({"status": "error", "message": "日期不可為空！"}), 400

    # 🔴 防呆 3：檢查金額格式與數值
    # 🔴 修正：移除「請填寫金額」的 400 報錯
    try:
        if amount_raw is None or str(amount_raw).strip() == "":
            final_amt = 0 # 改為自動補 0
        else:
            final_amt = float(amount_raw)
            
        # 如果是 todo 類型，金額可以是 0，如果是 expense 才檢查 > 0 (選做)
        # if e_type == 'expense' and final_amt <= 0: ... 
            
    except (ValueError, TypeError):
        final_amt = 0 # 格式錯誤也補 0

    conn = get_db_connection()
    try:
        # 判斷是編輯還是新增
        if e_id and str(e_id).strip() != "" and str(e_id) != "undefined":
            # 編輯模式
            conn.execute("""
                UPDATE calendar_events 
                SET event_date=?, category=?, content=?, amount=?, note=? 
                WHERE id=? AND user_id=?
            """, (date_str, category, content, final_amt, note, str(e_id), uid))
        else:
            # 新增模式
            new_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO calendar_events (
                    id, user_id, event_date, type, category, 
                    content, amount, note, recurring_task_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_id, uid, date_str, e_type, category, 
                content, final_amt, note, None
            ))
        
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"❌ 儲存失敗具體原因: {e}") 
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

# --- 2. 讀取資料 API (這是讓日曆顯示數字的關鍵) ---
@app.route('/api/get_events')
def get_events():
    if 'user_id' not in session:
        return jsonify([])
    
    uid = session['user_id']
    sync_recurring_to_calendar(uid) 
    
    target_date = request.args.get('date')
    conn = get_db_connection()
    # 💡 關鍵：設定 row_factory，這樣可以用 row['欄位名'] 存取
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    if target_date:
        # 1. 右側詳細清單
        rows = cursor.execute("""
            SELECT id, type, category, content, amount, note, event_date 
            FROM calendar_events 
            WHERE user_id = ? AND event_date = ? 
            AND (note != 'DELETED' OR note IS NULL)
        """, (uid, target_date)).fetchall()
        
        # 轉換為摘要清單格式
        result = [dict(row) for row in rows]
        
    else:
        # 2. 日曆格子統計
        rows = cursor.execute("""
            SELECT 
                event_date as start,
                SUM(CASE WHEN type = 'expense' AND (note != 'DELETED' OR note IS NULL) THEN amount ELSE 0 END) as total_exp,
                SUM(CASE WHEN type = 'income' AND (note != 'DELETED' OR note IS NULL) THEN amount ELSE 0 END) as total_inc,
                MAX(CASE WHEN type = 'todo' AND (note != 'DELETED' OR note IS NULL) THEN 1 ELSE 0 END) as has_todo
            FROM calendar_events 
            WHERE user_id = ? 
            GROUP BY event_date
        """, (uid,)).fetchall()

        result = []
        for row in rows:
            result.append({
                "start": row['start'],
                "display": "block",  
                "extendedProps": {
                    "total_exp": row['total_exp'],
                    "total_inc": row['total_inc'],
                    "has_todo": row['has_todo']
                }
            })

    conn.close()
    return jsonify(result) # 👈 確保這行在 if/else 外面，一定會執行

@app.route('/api/save_recurring_fixed', methods=['POST'])
def save_recurring_fixed():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "未登入"}), 401
    
    data = request.json
    uid = session['user_id']
    start_date = data.get('start_date') # 這是前端傳來的 activeDate (如 2026-02-15)
    
    # 擷取該日期的月份起點 (例如變為 2026-02-01)
    # 這樣同步函式就知道從 2 月開始往後填
    created_at_val = start_date if start_date else datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO recurring_tasks 
            (user_id, type, category, content, amount, day_of_period, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (uid, data['type'], data['category'], data['content'], 
              data['amount'], data['day_of_month'], created_at_val))
        conn.commit()
        
        # 🟢 儲存完立刻跑一次同步
        sync_recurring_to_calendar(uid)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        conn.close()


# 🟢 專門處理「花費清單」的刪除 (對應 HTML 裡的 /delete/xxx)
# 將 <id> 改為 <int:id> 確保它是數字
@app.route('/delete/<int:id>')
def delete_expense(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    try:
        # 刪除關聯資料
        cur.execute("DELETE FROM split_details WHERE expense_id = ?", (id,))
        cur.execute("DELETE FROM expenses WHERE id = ?", (id,))
        conn.commit()
        flash("紀錄已成功刪除", "success")
    except Exception as e:
        conn.rollback()
        flash(f"刪除失敗: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/export_csv')
def export_csv():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    # 抓取該使用者的所有支出紀錄 (假設你有分使用者，若無則抓全部)
    expenses = conn.execute("SELECT description, amount, payer_name, note, currency FROM expenses").fetchall()
    conn.close()

    # 建立記憶體中的 CSV 檔案
    output = io.StringIO()
    writer = csv.writer(output)
    # 寫入標題列
    writer.writerow(['項目描述', '金額(TWD)', '付款人', '備註', '幣別'])
    
    for row in expenses:
        writer.writerow([row['description'], row['amount'], row['payer_name'], row['note'], row['currency']])

    # 設定回應頭，讓瀏覽器下載檔案
    output.seek(0)
    return Response(
        output.getvalue().encode('utf-8-sig'), # 使用 utf-8-sig 確保 Excel 開啟不亂碼
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=expenses_backup.csv"}
    )

# --- 🟢 匯入 CSV ---
@app.route('/import_csv', methods=['POST'])
def import_csv():
    if 'file' not in request.files:
        flash("未選取檔案", "danger")
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file and file.filename.endswith('.csv'):
        # 使用 utf-8-sig 處理 Excel 產生的 BOM
        content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(content)
        csv_input = csv.DictReader(stream)
        
        conn = get_db_connection()
        try:
            for row in csv_input:
                # 確保這些 Key (如 '項目描述') 與 export_csv 寫入的完全相同
                conn.execute("""
                    INSERT INTO expenses (description, amount, payer_name, note, currency) 
                    VALUES (?, ?, ?, ?, ?)""", 
                    (row.get('項目描述'), row.get('金額(TWD)'), row.get('付款人'), row.get('備註'), row.get('幣別')))
            conn.commit()
            flash("CSV 資料匯入成功！", "success")
        except Exception as e:
            flash(f"匯入失敗: {e}", "danger")
        finally:
            conn.close()
            
    return redirect(url_for('index'))

# --- 3. 註冊與登入邏輯 (完全保留你的防呆與正規表達式) ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        # 基本驗證
        if not username or not email or not password:
            flash("所有欄位均為必填！", "danger")
        elif not re.match(email_regex, email):
            flash("Email 格式不正確，請檢查！", "danger")
        elif len(password) < 6:
            flash("密碼強度不足，至少需要 6 位字元！", "danger")
        else:
            conn = None  # 初始化連線變數
            try:
                # 1. 加入 timeout 解決 database is locked 問題
                conn = sqlite3.connect("trip_tracker.db", timeout=20)
                cur = conn.cursor()
                
                # 2. 執行寫入
                cur.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                           (username, password, email))
                conn.commit()
                
                flash("註冊成功！現在可以登入了。", "success")
                return redirect(url_for('login'))
                
            except sqlite3.IntegrityError:
                # 這是針對資料表 UNIQUE 限制（如帳號重複）的處理
                flash("帳號或 Email 已經有人使用過囉！", "warning")
            except sqlite3.OperationalError as e:
                # 這是針對資料庫鎖定的額外捕捉
                flash(f"資料庫暫時繁忙（Locked），請稍後再試。", "danger")
                print(f"Database Error: {e}")
            finally:
                # 3. ⚠️ 關鍵：無論如何都要關閉連線，釋放資料庫鎖
                if conn:
                    conn.close()
                    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash("帳號與密碼為必填欄位", "warning")
            return redirect(url_for('login'))

        conn = sqlite3.connect("trip_tracker.db")
        conn.row_factory = sqlite3.Row # 建議加入這行，這樣可以用名稱存取欄位
        cur = conn.cursor()
        
        # 🟢 修正：SQL 增加 email 欄位
        cur.execute("SELECT id, username, email FROM users WHERE username = ? AND password = ?", (username, password))
        user = cur.fetchone()
        conn.close()
        
        if user:
            session.clear()
            # 因為使用了 row_factory，這裡可以用名稱存取，更不容易出錯
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_email'] = user['email']  # 🟢 新增：將 Email 存入 Session
            
            flash(f"歡迎回來，{user['username']}！", "success")
            return redirect(url_for('calendar_page'))
        else:
            flash("帳號或密碼不正確，請重新檢查。", "danger")
            return redirect(url_for('login'))
            
    return render_template('login.html')

# --- 4. 記帳主頁與相關功能 (完全保留你的所有邏輯) ---
@app.route('/index')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid = session['user_id']

    # 1. 自動檢查固定項目
    sync_recurring_to_calendar(uid)

    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 2. 抓取成員 (保持順序)
    cur.execute("SELECT name FROM members ORDER BY id ASC")
    db_members = [row[0] for row in cur.fetchall()]
    
    # 3. 🟢 新增：抓取旅遊小卡 (資料夾) 及其花費總計
    # 我們在這裡用 LEFT JOIN 算出每個資料夾目前的累積花費，方便你「參考之前花多少」
    cur.execute("""
        SELECT f.id, f.folder_name, 
               IFNULL(SUM(e.amount), 0) as total_amount,
               COUNT(e.id) as item_count
        FROM travel_folders f
        LEFT JOIN expenses e ON f.id = e.folder_id
        WHERE f.user_id = ?
        GROUP BY f.id, f.folder_name
        ORDER BY f.id DESC
    """, (uid,))
    folders = [dict(row) for row in cur.fetchall()]
    
    # 4. 抓取所有花費明細
    cur.execute("SELECT id, description, amount, payer_name, note, currency, foreign_amount, folder_id FROM expenses")
    expenses_raw = cur.fetchall()
    
    balances = {m: 0.0 for m in db_members}
    detailed_expenses = []
    
    for exp in expenses_raw:
        # 注意：這裡多抓了 folder_id
        eid, desc, amt, payer, note, curr, f_amt, f_id = exp
        
        cur.execute("SELECT member_name FROM split_details WHERE expense_id = ?", (eid,))
        splitters = [r[0] for r in cur.fetchall()] 
        
        if splitters:
            share = amt / len(splitters)
            if payer in balances: balances[payer] += amt
            for s in splitters:
                if s in balances: balances[s] -= share
        
        detailed_expenses.append({
            'id': eid, 'desc': desc, 'amt': amt, 'payer': payer, 
            'note': note, 'splitters': "、".join(splitters),
            'currency': curr, 'f_amt': f_amt,
            'folder_id': f_id  # 讓前端知道這筆帳屬於哪個小卡
        })
        
    conn.close()
    
    # 5. 將 folders 傳遞給模板
    return render_template('index.html', 
                           expenses=detailed_expenses, 
                           members=db_members, 
                           balances=balances,
                           folders=folders) # 👈 關鍵：傳送小卡資料
                           
from datetime import datetime
import uuid
import sqlite3

@app.route('/add', methods=['POST'])
def add():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    uid = session['user_id']
    desc = request.form.get('description', '').strip()
    amount_twd = request.form.get('amount', '0')
    payer = request.form.get('payer')
    splitters = request.form.getlist('splitters')
    folder_id = request.form.get('folder_id')
    new_folder_name = request.form.get('new_folder_name', '').strip()
    
    # 匯率資訊與日期
    currency = request.form.get('currency', 'TWD')
    foreign_amt = request.form.get('foreign_amount', '0')
    note = request.form.get('note', '')
    date = request.form.get('date') # 新增日期欄位

    # 🚨 旅遊記帳專用防呆：必須有資料夾
    if folder_id == "" and not new_folder_name:
        flash("❌ 請選擇或新增一個「旅遊行程」資料夾！", "danger")
        return redirect(url_for('index'))

    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    
    try:
        # 1. 處理資料夾邏輯
        target_folder_id = None
        if folder_id == "NEW" and new_folder_name:
            cur.execute("INSERT INTO travel_folders (user_id, folder_name) VALUES (?, ?)", (uid, new_folder_name))
            target_folder_id = cur.lastrowid
        else:
            target_folder_id = folder_id

        # 2. 存入消費主表 (包含外幣、台幣、日期與資料夾 ID)
        cur.execute("""
            INSERT INTO expenses (description, amount, payer_name, note, currency, foreign_amount, folder_id, date) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
            (desc, amount_twd, payer, note, currency, foreign_amt, target_folder_id, date))
        
        eid = cur.lastrowid
        
        # 3. 存入分帳明細 (誰要攤這筆錢)
        for s in splitters:
            cur.execute("INSERT INTO split_details (expense_id, member_name) VALUES (?, ?)", (eid, s))
                
        conn.commit()
        flash(f"✅ 成功記錄至行程！", "success")
    except Exception as e:
        conn.rollback()
        flash(f"❌ 儲存失敗: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('index'))



@app.route('/api/settle/<int:folder_id>')
def settle(folder_id):
    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 抓取該行程所有消費明細
    expenses = cur.execute("SELECT id, amount, payer_name FROM expenses WHERE folder_id = ?", (folder_id,)).fetchall()
    
    balances = {} # 每個人的錢包結餘

    for exp in expenses:
        amt = exp['amount']
        payer = exp['payer_name']
        
        # 墊錢的人 = 錢包增加 (應收)
        balances[payer] = balances.get(payer, 0) + amt
        
        # 抓取這筆錢有哪些人分攤
        splitters = cur.execute("SELECT member_name FROM split_details WHERE expense_id = ?", (exp['id'],)).fetchall()
        if splitters:
            share = amt / len(splitters)
            for s in splitters:
                name = s['member_name']
                # 分攤的人 = 錢包減少 (應付)
                balances[name] = balances.get(name, 0) - share

    # 演算法：將錢包正負抵銷
    debtors = []   # 欠錢的人
    creditors = [] # 該收錢的人
    
    for name, bal in balances.items():
        if bal < -0.1: # 考慮四捨五入誤差
            debtors.append({'name': name, 'amount': abs(bal)})
        elif bal > 0.1:
            creditors.append({'name': name, 'amount': bal})

    plan = []
    d_idx = 0
    c_idx = 0
    
    while d_idx < len(debtors) and c_idx < len(creditors):
        d = debtors[d_idx]
        c = creditors[c_idx]
        payment = min(d['amount'], c['amount'])
        
        plan.append({
            'from': d['name'],
            'to': c['name'],
            'amount': round(payment)
        })
        
        d['amount'] -= payment
        c['amount'] -= payment
        
        if d['amount'] < 0.1: d_idx += 1
        if c['amount'] < 0.1: c_idx += 1

    return jsonify({
        'summary': {k: round(v) for k, v in balances.items()},
        'plan': plan
    })

@app.route('/delete_folder/<int:folder_id>')
def delete_folder(folder_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    try:
        # 1. 刪除該行程內所有的分帳明細 (外鍵最底層)
        cur.execute("""
            DELETE FROM split_details WHERE expense_id IN 
            (SELECT id FROM expenses WHERE folder_id = ?)
        """, (folder_id,))
        
        # 2. 刪除該行程內所有的消費紀錄
        cur.execute("DELETE FROM expenses WHERE folder_id = ?", (folder_id,))
        
        # 3. 刪除行程資料夾本人
        cur.execute("DELETE FROM travel_folders WHERE id = ? AND user_id = ?", (folder_id, session['user_id']))
        
        conn.commit()
        flash("✅ 行程已完整刪除", "success")
    except Exception as e:
        conn.rollback()
        print(f"❌ 刪除資料夾失敗: {e}")
        flash(f"刪除失敗: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/get_settlement/<int:folder_id>')
def get_settlement(folder_id):
    # 1. 從資料庫抓取該行程的所有支出
    # 確保你的資料庫欄位名稱正確：amount, payer_name, splitters
    expenses = db.execute('''
        SELECT amount, payer_name, splitters 
        FROM expenses 
        WHERE folder_id = ?
    ''', (folder_id,)).fetchall()
    
    # 2. 計算每個人的淨值 (Net Balance)
    # 淨值 = 幫大家墊的錢 - 自己應付的錢
    balances = {} 

    for exp in expenses:
        amt = exp['amount']
        payer = exp['payer_name']
        # 將字串 "張三, 李四" 轉為清單
        splitters = [s.strip() for s in exp['splitters'].split(',')]
        share = amt / len(splitters)
        
        # 墊錢的人增加資產
        balances[payer] = balances.get(payer, 0) + amt
        
        # 每個分攤的人減少資產 (包含墊錢者自己)
        for s in splitters:
            balances[s] = balances.get(s, 0) - share

    # 3. 將人分為：應收款項 (Creditors) 與 應付款項 (Debtors)
    debtors = []   # 欠錢的人 (淨值為負)
    creditors = [] # 該領錢的人 (淨值為正)
    
    for name, bal in balances.items():
        if bal < -0.5: # 忽略極小誤差
            debtors.append({'name': name, 'amount': abs(bal)})
        elif bal > 0.5:
            creditors.append({'name': name, 'amount': bal})

    # 4. 媒合還錢路徑
    transactions = []
    d_idx, c_idx = 0, 0
    
    while d_idx < len(debtors) and c_idx < len(creditors):
        d = debtors[d_idx]
        c = creditors[c_idx]
        
        # 取兩者之間的最小值進行轉帳
        payment = min(d['amount'], c['amount'])
        transactions.append({
            'from': d['name'],
            'to': c['name'],
            'amount': round(payment)
        })
        
        d['amount'] -= payment
        c['amount'] -= payment
        
        if d['amount'] < 0.5: d_idx += 1
        if c['amount'] < 0.5: c_idx += 1
            
    return jsonify(transactions)

@app.route('/edit_expense/<int:expense_id>', methods=['POST'])
def edit_expense(expense_id):
    # 1. 取得所有欄位
    folder_id = request.form.get('folder_id')
    date = request.form.get('date')
    description = request.form.get('description', '').strip()
    amount_twd = request.form.get('amount')
    payer = request.form.get('payer')
    splitters = request.form.getlist('splitters')
    
    # 🚨 重點：取得外幣資訊
    currency = request.form.get('currency', 'TWD')
    foreign_amt = request.form.get('foreign_amount', '0')
    note = request.form.get('note', '')

    # --- 後端防呆檢查 ---
    if not all([folder_id, date, description, amount_twd, payer]) or not splitters:
        flash("❌ 錯誤：所有欄位皆為必填，且至少需選擇一位分攤成員。", "danger")
        return redirect(url_for('edit_page_view', eid=expense_id))
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    
    try:
        # 2. 更新消費主表 (包含台幣、外幣、日期)
        cur.execute("""
            UPDATE expenses 
            SET folder_id=?, date=?, description=?, amount=?, payer_name=?, 
                currency=?, foreign_amount=?, note=?
            WHERE id=?
        """, (folder_id, date, description, amount_twd, payer, 
              currency, foreign_amt, note, expense_id))

        # 3. 更新分帳明細 (先刪除舊的，再插入新的)
        # 這是解決「誰該給誰多少」數據錯誤的關鍵
        cur.execute("DELETE FROM split_details WHERE expense_id=?", (expense_id,))
        for s in splitters:
            cur.execute("INSERT INTO split_details (expense_id, member_name) VALUES (?, ?)", (expense_id, s))

        conn.commit()
        flash("✅ 支出記錄與分帳明細已更新！", "success")
    except Exception as e:
        conn.rollback()
        flash(f"❌ 更新失敗: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('index'))

# --- A. 顯示編輯頁面 (GET) ---
@app.route('/edit_page_view/<int:eid>')
def edit_page_view(eid):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row  # 這行很重要，讓你可以用 e['amount'] 取值
    cur = conn.cursor()
    
    # 1. 抓取支出主資料
    cur.execute("SELECT * FROM expenses WHERE id = ?", (eid,))
    expense = cur.fetchone()
    
    # 2. 抓取這筆支出原本的分攤成員
    cur.execute("SELECT member_name FROM split_details WHERE expense_id = ?", (eid,))
    selected_splitters = [row[0] for row in cur.fetchall()]
    
    # 3. 抓取所有成員 (供 Checkbox 勾選)
    cur.execute("SELECT name FROM members WHERE user_id = ?", (session['user_id'],))
    all_members = [r[0] for r in cur.fetchall()]
    
    # 4. 抓取所有資料夾 (供下拉選單)
    cur.execute("SELECT id, folder_name FROM travel_folders WHERE user_id = ?", (session['user_id'],))
    folders = cur.fetchall()
    
    conn.close()
    
    if not expense: return "找不到該筆資料", 404

    return render_template("edit.html", e=expense, members=all_members, 
                           selected_splitters=selected_splitters, folders=folders)

@app.route('/get_expenses/<int:folder_id>')
def get_folder_expenses(folder_id):
    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 這裡的 e.* 包含了 payer_name 欄位
    query = """
        SELECT e.*, GROUP_CONCAT(s.member_name, ', ') as splitters
        FROM expenses e
        LEFT JOIN split_details s ON e.id = s.expense_id
        WHERE e.folder_id = ?
        GROUP BY e.id
        ORDER BY e.date DESC, e.id DESC
    """
    try:
        expenses = cur.execute(query, (folder_id,)).fetchall()
        # 轉換成 JSON 給前端
        return jsonify([dict(ix) for ix in expenses])
    except Exception as e:
        print(f"❌ 讀取資料夾明細失敗: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/add_member', methods=['POST'])
def add_member():
    if 'user_id' not in session: return redirect(url_for('login'))
    name = request.form.get('member_name', '').strip()
    if name:
        try:
            conn = sqlite3.connect("trip_tracker.db")
            cur = conn.cursor()
            # 存入時務必帶上目前登入者的 ID
            cur.execute("INSERT INTO members (name, user_id) VALUES (?, ?)", (name, session['user_id']))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            flash("成員名稱已重複", "warning")
    return redirect(url_for('index'))

@app.route('/delete_member/<name>')
def delete_member(name):
    uid = session['user_id']
    conn = get_db_connection()
    # 檢查該成員是否還有未清帳務
    # ... 如果有，建議 flash "請先刪除該成員的相關紀錄再移除成員"
    conn.execute("DELETE FROM members WHERE name = ? AND user_id = ?", (name, uid))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/update_record/<int:eid>', methods=['POST'])
def update_record(eid):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # 取得表單資料
    desc = request.form.get('description')
    amount = request.form.get('amount')
    payer = request.form.get('payer')
    note = request.form.get('note')
    date = request.form.get('date')
    folder_id = request.form.get('folder_id') # 取得修改後的資料夾
    splitters = request.form.getlist('splitters') # 取得勾選的分攤人
    
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    
    try:
        # 1. 更新主表紀錄
        cur.execute("""
            UPDATE expenses 
            SET description=?, amount=?, payer_name=?, note=?, date=?, folder_id=?
            WHERE id=?
        """, (desc, amount, payer, note, date, folder_id, eid))
        
        # 2. 更新分攤明細 (先刪除舊的再插入新的，最乾淨)
        cur.execute("DELETE FROM split_details WHERE expense_id = ?", (eid,))
        for s in splitters:
            cur.execute("INSERT INTO split_details (expense_id, member_name) VALUES (?, ?)", (eid, s))
            
        conn.commit()
        flash("✅ 紀錄已成功更新", "success")
    except Exception as ex:
        conn.rollback()
        flash(f"❌ 更新失敗: {ex}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('index'))

@app.route('/edit/<int:eid>', methods=['POST'])
def edit(eid):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # 1. 取得所有資料並去除空格
    desc = request.form.get('description', '').strip()
    amount_twd = request.form.get('amount', '0')
    payer = request.form.get('payer')
    splitters = request.form.getlist('splitters')
    folder_id = request.form.get('folder_id')
    currency = request.form.get('currency', 'TWD')
    foreign_amt = request.form.get('foreign_amount', '0')
    date = request.form.get('date')

    # 🚨 強力防呆：檢查所有必要資料是否齊全
    if not all([desc, amount_twd, payer, splitters, folder_id, date]):
        flash("❌ 編輯失敗：所有欄位皆為必填，且至少需選擇一位分攤者！", "danger")
        return redirect(url_for('index'))

    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    try:
        # 更新主表 (包含外幣資訊)
        cur.execute("""
            UPDATE expenses 
            SET description=?, amount=?, payer_name=?, currency=?, foreign_amount=?, folder_id=?, date=?
            WHERE id=? """, (desc, amount_twd, payer, currency, foreign_amt, folder_id, date, eid))
        
        # 更新分帳明細：先刪除舊的，再插入新的
        cur.execute("DELETE FROM split_details WHERE expense_id=?", (eid,))
        for s in splitters:
            cur.execute("INSERT INTO split_details (expense_id, member_name) VALUES (?, ?)", (eid, s))
            
        conn.commit()
        flash("✅ 資料已成功更新！", "success")
    except Exception as e:
        conn.rollback()
        flash(f"❌ 更新失敗: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/get_rate/<base_code>')
def get_rate(base_code):
    url = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/{base_code}"
    response = requests.get(url)
    data = response.json()
    if data["result"] == "success":
        return {
            "rate": data["conversion_rates"]["TWD"],
            "update_time": data["time_last_update_utc"]
        }
    return {"error": "API 錯誤"}, 400

@app.route('/logout')
def logout():
    session.clear()
    flash("您已安全登出", "success")
    return redirect(url_for('login'))

@app.route('/analysis')
def analysis():
    """跳轉到分析頁面"""
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    return render_template('analysis.html')

from datetime import datetime

@app.route('/api/send_budget_warning', methods=['POST'])
def send_warning():
    if 'user_id' not in session: 
        return jsonify({"status": "error", "message": "請先登入"}), 401
    
    data = request.get_json()
    exp = data.get('exp', 0)
    limit = data.get('budget', 0)
    current_month = datetime.now().strftime('%Y-%m') # 🌟 修正：確保 current_month 有定義

    # 🌟 核心邏輯：檢查「月份」且「預算金額」是否與上次發信時相同
    # 如果預算改了（例如從 20000 改成 15000），則允許再次發信
    last_limit = session.get('last_alert_limit')
    last_month = session.get('last_alert_month')

    if last_month == current_month and last_limit == limit:
        return jsonify({"status": "skipped", "message": "此預算額度已發送過提醒"})

    user_email = session.get('user_email')
    if not user_email:
        return jsonify({"status": "error", "message": "找不到註冊郵件"}), 400

    try:
        subject_text = f"FinSync 預算超標警告 ({current_month})"
        msg = Message(
            subject=subject_text,
            sender=app.config.get('MAIL_DEFAULT_SENDER'),
            recipients=[user_email]
        )
        
        user_name = session.get('username', '使用者')
        msg.body = f"您好 {user_name}：\n\n您本月的支出 (${exp:,.0f}) 已超過預算上限 (${limit:,.0f})，請注意開支管理。"
        msg.charset = 'utf-8'

        mail.send(msg)
        
        # 🌟 成功後，記住這次發信的月份與預算金額
        session['last_alert_month'] = current_month
        session['last_alert_limit'] = limit 
        
        return jsonify({"status": "sent"})
        
    except Exception as e:
        print(f"❌ SMTP 發信失敗詳情: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
# def diagnose_api():
#     KEY = "AIzaSyB_6dLiYab4mmZmWzE-y7ZoNAQzuHfbJFM"
#     url = f"https://generativelanguage.googleapis.com/v1beta/models?key={KEY}"
#     res = requests.get(url)
#     models = res.json()
#     print("--- 你的 API Key 可用模型清單 ---")
#     if 'models' in models:
#         for m in models['models']:
#             print(m['name'])
#     else:
#         print(f"無法取得清單，錯誤訊息: {models}")
#     print("--------------------------------")

# diagnose_api()

# 3. API: 固定記帳管理 (原生 SQLite 版本)
@app.route('/api/recurring_tasks', methods=['GET', 'POST'])
def handle_recurring():
    if 'user_id' not in session:
        return jsonify({"error": "請先登入"}), 401
        
    conn = sqlite3.connect("trip_tracker.db")
    conn.row_factory = sqlite3.Row
    
    if request.method == 'POST':
        try:
            data = request.json
            # 確保資料都有抓到，給予預設值防止崩潰
            u_id = session['user_id']
            t_type = data.get('type', 'expense')
            cat = data.get('category', '其他')
            amt = data.get('amount', 0)
            freq = data.get('frequency', 'monthly')
            month = data.get('month', 1)
            day = data.get('day', 1)
            
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO recurring_tasks 
                (user_id, type, category, amount, frequency, month_of_year, day_of_period, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (u_id, t_type, cat, amt, freq, month, day, "自動化設定"))
            conn.commit()
            return jsonify({"status": "success", "message": "已儲存固定項目"})
        except Exception as e:
            # 🟢 這裡會在你的終端機印出到底是哪個欄位出錯
            print(f"❌ 資料庫寫入失敗: {str(e)}") 
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            conn.close()
    
    else: # GET 請求
        tasks = conn.execute("SELECT * FROM recurring_tasks WHERE user_id = ?", (session['user_id'],)).fetchall()
        conn.close()
        return jsonify([dict(t) for t in tasks])

# 確保這個名稱在整個 app.py 只有這一個！
@app.route('/delete_recurring_task/<int:task_id>', methods=['POST'])
def delete_recurring_task_final(task_id):
    if 'user_id' not in session:
        return {"status": "error", "message": "未登入"}, 401
        
    conn = sqlite3.connect("trip_tracker.db")
    cur = conn.cursor()
    try:
        # 1. 斬草除根：刪除「規則本體」，這樣同步函式就再也找不到它了
        cur.execute("DELETE FROM recurring_tasks WHERE id = ? AND user_id = ?", (task_id, session['user_id']))
        
        # 2. 清理分身：刪除日曆上所有由這個規則產生的事件
        cur.execute("DELETE FROM calendar_events WHERE recurring_task_id = ?", (task_id,))
        
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        conn.close()

def debug_reset_table():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 1. 先看看現在有什麼表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"🔍 目前資料庫裡的表有: {[t['name'] for t in tables]}")
        
        # 2. 強制清空
        cursor.execute("DELETE FROM calendar_events")
        print(f"💥 內部清理成功，影響行數: {cursor.rowcount}")
        conn.commit()

# # 在啟動 Flask 前執行它
# debug_reset_table()

def cleanup_orphan_events():
    """清理那些規則已被刪除，但紀錄還殘留在日曆上的自動化項目"""
    conn = get_db_connection()
    try:
        # 刪除條件：
        # 1. 有 recurring_task_id 
        # 2. 但這個 ID 在 recurring_tasks 表中已經找不到了
        conn.execute("""
            DELETE FROM calendar_events 
            WHERE recurring_task_id IS NOT NULL 
            AND recurring_task_id NOT IN (SELECT id FROM recurring_tasks)
        """)
        conn.commit()
        print("✅ 孤兒紀錄清理完畢！")
    except Exception as e:
        print(f"❌ 清理失敗: {e}")
    finally:
        conn.close()

# 你可以手動執行一次，或在程式啟動時呼叫它
# cleanup_orphan_events()

def repair_database_typos():
    conn = get_db_connection()
    # 1. 把空的 content 補上類別名稱
    conn.execute("UPDATE calendar_events SET content = category WHERE content IS NULL OR content = ''")
    
    # 2. 把負數的支出轉為正數 (因為 type='expense' 已經代表支出了)
    conn.execute("UPDATE calendar_events SET amount = ABS(amount) WHERE type = 'expense' AND amount < 0")
    
    conn.commit()
    conn.close()
    print("✅ 資料庫文字與金額修復完成！")

# 在 if __name__ == '__main__': 之前呼叫一次即可
# repair_database_typos()


if __name__ == '__main__':

    app.run(debug=True)
