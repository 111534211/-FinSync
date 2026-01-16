from flask import Blueprint, render_template, request, jsonify, session
from datetime import datetime

calendar_bp = Blueprint('calendar', __name__)

# 模擬資料庫 (實務建議存入 SQLite)
events_db = {}

@calendar_bp.route('/calendar')
def calendar_home():
    if 'user_id' not in session:
        return """<script>alert('請先登入'); window.location='/login';</script>"""
    return render_template('calendar_home.html')

@calendar_bp.route('/api/get_events', methods=['GET'])
def get_events():
    date_str = request.args.get('date')
    if not date_str:
        # 回傳所有資料供日曆渲染小圖示
        return jsonify(events_db)
    return jsonify(events_db.get(date_str, []))

@calendar_bp.route('/api/add_event', methods=['POST'])
def add_event():
    data = request.get_json()
    date_str = data.get('date')
    content = data.get('content', '').strip()
    
    if not date_str or not content:
        return jsonify({"status": "error", "message": "內容不能為空"}), 400

    if date_str not in events_db:
        events_db[date_str] = []
    
    new_item = {
        "id": str(datetime.now().timestamp()),
        "type": data.get('type'),
        "content": content,
        "amount": float(data.get('amount', 0)) if data.get('type') != 'todo' else 0
    }
    events_db[date_str].append(new_item)
    return jsonify({"status": "success"})

@calendar_bp.route('/api/delete_event', methods=['POST'])
def delete_event():
    data = request.get_json()
    date_str = data.get('date')
    event_id = data.get('id')
    if date_str in events_db:
        events_db[date_str] = [e for e in events_db[date_str] if e['id'] != event_id]
    return jsonify({"status": "success"})