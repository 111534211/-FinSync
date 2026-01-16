import os, json, hashlib
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
from datetime import datetime

app = Flask(__name__)
# --- 補上首頁跳轉路由 ---
@app.route("/")
def index():
    # 如果已經登入，去儀表板；沒登入，去登入頁
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

app.secret_key = "wallet_v47_final_fix"

DATA_FILE, USER_FILE = "data.json", "users.json"

def load_j(f):
    if not os.path.exists(f): return []
    try:
        with open(f, "r", encoding="utf-8") as file: return json.load(file)
    except: return []

def save_j(f, d):
    with open(f, "w", encoding="utf-8") as file: json.dump(d, file, ensure_ascii=False, indent=2)

# --- 帳號認證相關路由 ---

@app.route("/login", methods=["GET", "POST"])
def login():
    error_msg = None
    if request.method == "POST":
        u_name, u_pass = request.form.get("username"), request.form.get("password")
        users = load_j(USER_FILE)
        
        # 1. 尋找使用者
        u = next((x for x in users if x["username"] == u_name), None)
        
        if not u:
            error_msg = "no_user"
        else:
            # 2. 驗證密碼
            hashed_pass = hashlib.sha256(u_pass.encode()).hexdigest()
            if u["password"] == hashed_pass:
                session.update({"user_id": u["id"], "username": u["username"]})
                return redirect(url_for("dashboard"))
            else:
                error_msg = "wrong_pass"
                
    return render_template_string(T_AUTH, mode="login", error=error_msg)

@app.route("/register", methods=["GET", "POST"])
def register():
    error_msg = None
    if request.method == "POST":
        u_name, u_pass = request.form.get("username"), request.form.get("password")
        users = load_j(USER_FILE)
        
        # 檢查帳號是否已存在
        if any(x["username"] == u_name for x in users):
            error_msg = "user_exists"
        else:
            # 執行註冊
            new_u = {
                "id": len(users) + 1, 
                "username": u_name, 
                "password": hashlib.sha256(u_pass.encode()).hexdigest(), 
                "budget": 20000
            }
            users.append(new_u)
            save_j(USER_FILE, users)
            session.update({"user_id": new_u["id"], "username": new_u["username"]})
            return redirect(url_for("dashboard"))
            
    return render_template_string(T_AUTH, mode="register", error=error_msg)


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: return redirect(url_for("login"))
    all_e = load_j(DATA_FILE)
    entries = [e for e in all_e if str(e.get("user_id")) == str(session["user_id"])]
    users = load_j(USER_FILE)
    curr_u = next((u for u in users if str(u["id"]) == str(session["user_id"])), {"budget": 20000})
    return render_template_string(T_DASH, user=session["username"], entries=json.dumps(entries), budget=curr_u["budget"])

@app.route("/api/save", methods=["POST"])
def api_save():
    uid, data = session.get("user_id"), load_j(DATA_FILE)
    req = request.json
    eid = str(req.get("id")) if (req.get("id") and req.get("id") != "") else str(datetime.now().timestamp())
    new_e = {
        "id": eid, "user_id": uid, "type": req.get("type"), 
        "category": req.get("category"), "amount": float(req.get("amount") or 0), 
        "date": req.get("date"), "note": req.get("note"), 
        "is_todo": req.get("is_todo", False), "is_travel": req.get("is_travel", False),
        "paid_by": req.get("paid_by", ""), "payers": req.get("payers", [])
    }
    idx = next((i for i, x in enumerate(data) if str(x.get("id")) == eid), None)
    if idx is not None: data[idx] = new_e
    else: data.append(new_e)
    save_j(DATA_FILE, data)
    return jsonify({"status": "success"})

@app.route("/api/delete", methods=["POST"])
def api_delete():
    all_data = load_j(DATA_FILE)
    data = [e for e in all_data if str(e.get("id")) != str(request.json.get("id"))]
    save_j(DATA_FILE, data)
    return jsonify({"status": "success"})

@app.route("/api/update_budget", methods=["POST"])
def update_budget():
    uid, new_b = session.get("user_id"), request.json.get("budget")
    users = load_j(USER_FILE)
    for u in users:
        if str(u["id"]) == str(uid): u["budget"] = int(new_b)
    save_j(USER_FILE, users); return jsonify({"status": "success"})

@app.route("/logout")
def logout():
    session.clear()
    # 這裡加上 status 參數
    return redirect(url_for("login", status="logout_success"))

T_AUTH = """
<!doctype html><html><head><meta charset="utf-8">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
    body { background: #f1f5f9; height: 100vh; display: flex; align-items: center; justify-content: center; }
    .auth-card { background: white; border-radius: 20px; padding: 40px; width: 360px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }
</style></head><body>
<div class="auth-card text-center">
    <h3 class="fw-bold mb-4 text-primary">智匯記 FinSync</h3>
    <form method="post">
        <input type="text" name="username" class="form-control mb-3" placeholder="Username / 帳號" required>
        <input type="password" name="password" class="form-control mb-4" placeholder="Password / 密碼" required>
        <button class="btn btn-primary w-100 fw-bold py-2 mb-3">{{ 'Login / 登入' if mode=='login' else 'Register / 註冊' }}</button>
    </form>
    <a href="{{ '/register' if mode=='login' else '/login' }}" class="text-decoration-none small text-muted">
        {{ '沒有帳號？按此註冊 (Register)' if mode=='login' else '已有帳號？按此登入 (Login)' }}
    </a>
</div>

<script>
    // 每次回到登入頁，就重置「已歡迎過」的標記
    localStorage.removeItem('has_welcomed');

    const error = "{{ error }}";
    const urlParams = new URLSearchParams(window.location.search);
    
    // 1. 處理錯誤訊息
    if (error === "no_user") alert("❌ 找不到此帳號！");
    else if (error === "wrong_pass") alert("🔑 密碼錯誤！");
    else if (error === "user_exists") alert("⚠️ 帳號已存在！");

    // 2. 處理登出成功訊息
    if (urlParams.get('status') === 'logout_success') {
        alert("👋 您已成功登出，再見！");
        window.history.replaceState({}, document.title, window.location.pathname);
    }
</script>
</body></html>
"""

T_DASH = """
<!doctype html><html><head><meta charset="utf-8">
<title>智匯記 FinSync</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
    :root { --expense: #f43f5e; --income: #10b981; --todo: #f59e0b; }
    body { background: #f8fafc; font-family: system-ui; padding-top: 70px; }
    .card { background: white; border-radius: 20px; border: none; box-shadow: 0 4px 10px rgba(0,0,0,0.02); margin-bottom: 20px; }
    .news-fixed-card { position: fixed; bottom: 20px; left: 20px; width: 280px; z-index: 900; background: rgba(255,255,255,0.9); backdrop-filter: blur(10px); border-radius: 12px; border-left: 5px solid #3b82f6; cursor: pointer; transition: 0.3s all; overflow: hidden; max-height: 160px; }
    .news-fixed-card.collapsed { max-height: 45px; }
    .calendar-day { min-height: 100px; border: 0.5px solid #f1f5f9; flex: 0 0 14.28%; cursor: pointer; background: white; position: relative; }
    .day-today { background: #3b82f6 !important; color: white !important; }
    .calendar-day.selected { outline: 2px solid #3b82f6; z-index: 5; }
    .day-val { display: block; font-size: 10px; padding: 1px 4px; border-radius: 4px; margin-top: 2px; }
    .val-inc { color: var(--income); background: #ecfdf5; }
    .val-exp { color: var(--expense); background: #fff1f2; }
    .val-todo { color: var(--todo); font-weight: bold; }
    .lang-btn { cursor: pointer; padding: 2px 12px; border-radius: 15px; font-size: 11px; border: 1px solid #ddd; background: white; }
    .lang-btn.active { background: #3b82f6; color: white; border-color: #3b82f6; }
</style>

<script>


// 1. 從網路獲取最新匯率 (以 TWD 為基準)
async function fetchRates() {
    try {
        const response = await fetch('https://open.er-api.com/v6/latest/TWD');
        const data = await response.json();
        if (data.result === "success") {
            latestRates = data.rates;
            initCurrencyDropdown();
            document.getElementById('rateInfo').innerText = "匯率已更新於 " + new Date().toLocaleTimeString();
        }
    } catch (err) {
        document.getElementById('rateInfo').innerText = "❌ 匯率獲取失敗";
    }
}

// 2. 初始化下拉選單
function initCurrencyDropdown() {
    const selector = document.getElementById('currencySelector');
    if (!selector) return;
    selector.innerHTML = Object.keys(currencyConfigs).map(code => 
        `<option value="${code}">${currencyConfigs[code].name} ${code}</option>`
    ).join('');
}

// 3. 外幣輸入時 -> 計算台幣
function convertFromForeign() {
    const amount = parseFloat(document.getElementById('foreignAmount').value) || 0;
    const code = document.getElementById('currencySelector').value;
    const twdInput = document.getElementById('twdAmount');
    
    if (latestRates[code]) {
        // 公式：外幣 / 匯率 = 台幣 (API 是 1 TWD = X 外幣)
        const res = Math.round(amount / latestRates[code]);
        twdInput.value = res;
        updateRateInfo(code);
    }
}

// 4. 台幣輸入時 -> 反推外幣
function convertFromTWD() {
    const twdVal = parseFloat(document.getElementById('twdAmount').value) || 0;
    const code = document.getElementById('currencySelector').value;
    const foreignInput = document.getElementById('foreignAmount');
    
    if (latestRates[code]) {
        // 公式：台幣 * 匯率 = 外幣
        const res = (twdVal * latestRates[code]).toFixed(2);
        foreignInput.value = res;
        updateRateInfo(code);
    }
}

// 5. 更新匯率小字資訊
function updateRateInfo(code) {
    const rate = latestRates[code];
    const inverse = (1 / rate).toFixed(4); // 1單位外幣等於多少台幣
    document.getElementById('rateInfo').innerHTML = `參考匯率：1 ${code} ≈ ${inverse} TWD`;
}

// 6. 一鍵代入：將計算好的台幣數字填入旅遊記帳表單
function applyToTravelAmt() {
    const val = document.getElementById('twdAmount').value;
    const target = document.getElementById('trAmt');
    if (val && target) {
        target.value = val;
        // 簡單的視覺閃爍回饋
        target.style.transition = "background 0.3s";
        target.style.background = "#fff3cd";
        setTimeout(() => target.style.background = "#f8fafc", 500);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const currentUser = "{{ user }}";
    // 檢查是否有「剛登入」的標記
    if (!localStorage.getItem('has_welcomed')) {
        alert("✨ 登入成功，歡迎回來，" + currentUser + "！");
        localStorage.setItem('has_welcomed', 'true');
    }
    
    // 初始化語系與頁面
    toggleLang('zh'); 
    
    // 初始化年份選擇器 (避免選單空白)
    const ys = document.getElementById('yearSelect');
    if(ys) {
        const curY = new Date().getFullYear();
        for(let i = curY - 5; i <= curY + 5; i++) {
            ys.innerHTML += `<option value="${i}">${i}</option>`;
        }
        ys.value = curY;
    }
});
</script>
</head><body>

<nav class="navbar navbar-expand fixed-top bg-white border-bottom"><div class="container">
    <span class="navbar-brand fw-bold text-primary">智匯記 FinSync</span>
    <div class="ms-auto d-flex align-items-center">
        <div class="me-3">
            <span class="lang-btn" id="b-zh" onclick="toggleLang('zh')">中</span> 
            <span class="lang-btn" id="b-en" onclick="toggleLang('en')">EN</span>
        </div>
        <span class="me-3 fw-bold small text-muted" id="t-welcome"></span>
        <a href="/logout" class="btn btn-sm btn-outline-danger" id="t-logout">Logout</a>
    </div>
</div></nav>

<div class="card news-fixed-card shadow p-3" id="newsBox">
    <div class="d-flex justify-content-between align-items-center mb-1">
        <div class="small text-primary fw-bold">MARKET NEWS</div>
        <button class="btn btn-sm btn-outline-secondary border-0" id="newsToggle">▼</button>
    </div>
    <div id="newsTitle" style="font-size: 13px; font-weight: bold; line-height: 1.4; margin-top: 8px; transition: opacity 0.3s;"></div>
</div>


<div class="container">
    <ul class="nav nav-pills mb-3 gap-2" id="mainTabs">
        <li class="nav-item"><button class="nav-link active rounded-pill px-4" id="t-tab-home" data-bs-toggle="tab" data-bs-target="#home" onclick="refreshUI()"></button></li>
        <li class="nav-item"><button class="nav-link rounded-pill px-4" id="t-tab-report" data-bs-toggle="tab" data-bs-target="#report" onclick="renderReport()"></button></li>
        <li class="nav-item"><button class="nav-link rounded-pill px-4" id="t-tab-travel" data-bs-toggle="tab" data-bs-target="#travel" onclick="renderTravel()"></button></li>
    </ul>

    <div class="tab-content">
        <div class="tab-pane fade show active" id="home">
            <div class="row">
                <div class="col-lg-8"><div class="card p-4">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <select id="yearSelect" class="form-select form-select-sm w-auto" onchange="jumpDate()"></select>
                        <div class="d-flex align-items-center gap-3">
                            <button class="btn btn-light btn-sm" onclick="changeMonth(-1)">◀</button>
                            <h4 id="monthDisplay" class="m-0 fw-bold"></h4>
                            <button class="btn btn-light btn-sm" onclick="changeMonth(1)">▶</button>
                        </div>
                    </div>
                    <div id="calendarGrid" class="row g-0 border rounded overflow-hidden"></div>
                </div></div>
                <div class="col-lg-4"><div class="card p-4" style="padding-bottom: 80px;">
                    <h5 id="detailDate" class="fw-bold mb-3 text-primary border-bottom pb-2"></h5>
                    <div id="detailList" style="min-height: 280px;"></div>
                    <div class="d-grid gap-2 mt-4">
                        <button class="btn btn-primary fw-bold py-2" onclick="openModal('expense')" id="t-add-btn"></button>
                        <button class="btn btn-warning fw-bold text-white py-2" onclick="openModal('todo')" id="t-todo-btn"></button>
                    </div>
                </div>
                </div>
            </div>
        </div>

        <div class="tab-pane fade" id="report">
            <div class="row g-4">
                <div class="col-md-4">
                    <div class="card p-4 mb-3">
                        <div class="d-flex justify-content-between mb-3"><h6 class="fw-bold text-muted m-0" id="t-budget-label"></h6><button class="btn btn-sm btn-link p-0 text-decoration-none" data-bs-toggle="modal" data-bs-target="#budgetModal" id="t-set-btn"></button></div>
                        <div class="progress mb-2" style="height: 12px; border-radius: 10px;"><div id="budgetBar" class="progress-bar"></div></div>
                        <div class="d-flex justify-content-between small fw-bold"><span id="spentLabel"></span><span id="limitLabel"></span></div>
                    </div>
                    <div class="card p-4 mb-3"><h6 class="fw-bold text-muted mb-2" id="t-summary-label"></h6><h2 id="netBalance" class="fw-bold"></h2></div>
                    <div class="card p-4"><h6 class="fw-bold text-muted mb-3" id="t-rank-label"></h6><div id="rankList"></div></div>
                </div>
                <div class="col-md-8"><div class="card p-4 h-100"><h6 class="fw-bold text-muted mb-4" id="t-trend-label"></h6><div style="height: 350px;"><canvas id="trendChart"></canvas></div></div></div>
            </div>
        </div>
        
        <div class="tab-pane fade" id="travel">
    <div class="row g-4">
        <div class="col-md-7">
            <div class="card p-4 mb-3 border-0 shadow-sm">
                <h6 class="fw-bold text-muted mb-3" id="trFormLabel">➕ 新增旅遊花費</h6>
                <input type="hidden" id="trEditId">
                <div class="row g-3">
                    <div class="col-md-4">
                        <label class="small fw-bold" id="t-tr-date">日期</label>
                        <input type="date" id="trDate" class="form-control">
                    </div>
                    <div class="col-md-5">
                        <label class="small fw-bold" id="t-tr-note">項目</label>
                        <input type="text" id="trNote" class="form-control" placeholder="例如：晚餐">
                    </div>
                    <div class="col-md-3">
                        <label class="small fw-bold" id="t-tr-amt">金額</label>
                        <input type="number" id="trAmt" class="form-control" placeholder="0">
                    </div>
                    <div class="col-md-6">
                        <label class="small fw-bold" id="t-tr-paid-by">誰先付錢？</label>
                        <select id="trPaidBy" class="form-select"></select>
                    </div>
                    <div class="col-12">
                        <label class="small fw-bold text-muted mb-2" id="t-tr-split">分攤成員：</label>
                        <div id="payerCheckboxes" class="d-flex flex-wrap gap-2"></div>
                    </div>
                    <div class="col-12 d-flex gap-2">
                        <button id="btnTrSave" class="btn btn-info w-100 text-white fw-bold py-2" onclick="saveTravel()">儲存</button>
                        <button id="btnTrCancel" class="btn btn-light d-none" onclick="resetTrForm()">取消</button>
                    </div>
                </div>
            </div>

            <div class="card p-4 border-0 shadow-sm">
                <h6 class="fw-bold text-muted mb-3" id="t-tr-list">📝 旅遊流水帳</h6>
                <div id="travelLog" style="max-height: 500px; overflow-y: auto;"></div>
            </div>
        </div>

        <div class="col-md-5">
            <div class="card p-4 mb-3 border-0 shadow-sm">
                <h6 class="fw-bold text-muted mb-3" id="t-tr-members">👥 旅伴名單</h6>
                <div class="input-group mb-3">
                    <input type="text" id="newMemberName" class="form-control" placeholder="名稱">
                    <button class="btn btn-primary" onclick="addMember()" id="t-tr-add-m">新增</button>
                </div>
                <div id="memberBadges" class="d-flex flex-wrap gap-2"></div>
            </div>

            <div class="card p-4 mb-3 border-0 shadow-sm bg-light">
                <h6 class="fw-bold text-muted mb-3" id="t-tr-calc">📊 結算結果</h6>
                <div id="settlementList" class="small fw-bold text-primary mb-3"></div>
                <button class="btn btn-outline-primary w-100 fw-bold" onclick="calculateSettlement()" id="t-tr-calc-btn">開始計算</button>
            </div>

            <div class="card p-4 border-0 shadow-sm bg-dark text-white">
                <h6 class="fw-bold mb-3">💱 雙向匯率換算</h6>
                <div class="mb-3">
                    <label class="small text-light text-opacity-75 mb-1">輸入外幣 (Foreign)</label>
                    <div class="input-group">
                        <input type="number" id="foreignAmount" class="form-control border-0 bg-secondary bg-opacity-25 text-white" placeholder="0.00" oninput="convertFromForeign()">
                        <select id="currencySelector" class="form-select border-0 bg-secondary text-white w-auto" onchange="convertFromForeign()" style="flex: 0 0 100px;"></select>
                    </div>
                </div>
                <div class="mb-3">
                    <label class="small text-light text-opacity-75 mb-1">換算台幣 (TWD)</label>
                    <div class="input-group">
                        <span class="input-group-text border-0 bg-secondary bg-opacity-25 text-white">NT$</span>
                        <input type="number" id="twdAmount" class="form-control border-0 bg-secondary bg-opacity-25 text-white" placeholder="0" oninput="convertFromTWD()">
                    </div>
                </div>
                <button class="btn btn-warning w-100 fw-bold text-dark mb-2" onclick="applyToTravelAmt()">代入台幣金額</button>
                <div id="rateInfo" class="text-center" style="font-size: 10px; opacity: 0.6;">載入中...</div>
            </div>
        </div>
    </div>
</div>
        
        
    </div>
</div>




<div class="modal fade" id="budgetModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><div class="modal-content card p-3">
    <div class="modal-header border-0 pb-0"><h5 class="fw-bold" id="t-bm-title"></h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body"><label class="small fw-bold mb-1" id="t-bm-limit"></label><input type="number" id="newBudgetVal" class="form-control" value="{{ budget }}"></div>
    <div class="modal-footer border-0 pt-0"><button class="btn btn-primary w-100 fw-bold" onclick="updateBudget()" id="t-bm-save"></button></div>
</div></div></div>



<div class="modal fade" id="entryModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><div class="modal-content card p-3">
    <div class="modal-header border-0"><h5 id="mTitle" class="fw-bold"></h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
        <input type="hidden" id="mId"><input type="hidden" id="mIsTodo">
        <div class="mb-3"><label class="small fw-bold" id="t-m-date"></label><input type="date" id="mDate" class="form-control"></div>
        <div id="expFields">
            <div class="row g-2 mb-3">
                <div class="col-6"><label class="small fw-bold" id="t-m-type"></label><select id="mType" class="form-select" onchange="updateCats()"><option value="支出" id="t-m-exp-opt"></option><option value="收入" id="t-m-inc-opt"></option></select></div>
                <div class="col-6"><label class="small fw-bold" id="t-m-cat"></label><select id="mCat" class="form-select"></select></div>
            </div>
            <div class="mb-3"><label class="small fw-bold" id="t-m-amt"></label><input type="number" id="mAmt" class="form-control"></div>
        </div>
        <div class="mb-2"><label class="small fw-bold" id="t-m-note"></label><textarea id="mNote" class="form-control" rows="2"></textarea></div>
    </div>
    <div class="modal-footer border-0"><button class="btn btn-outline-danger me-auto" id="btnDel" onclick="deleteEntry()">刪除</button><button class="btn btn-primary px-4 fw-bold" onclick="saveEntry()" id="t-m-save-btn"></button></div>
</div></div></div>


<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
    let entries = {{ entries|safe }}, userBudget = {{ budget }}, viewDate = new Date();
    const todayStr = new Date().toLocaleDateString('en-CA');
    let selectedDate = todayStr, trendChart = null, lang = 'zh', userName = "{{ user }}";
    let members = JSON.parse(localStorage.getItem('travel_members') || '["我"]');
    let selectedPayers = [];

    function removeMember(name) {
        if (confirm(`確定要移除旅伴「${name}」嗎？`)) {
            // 1. 從名單中濾掉
            members = members.filter(m => m !== name);
            // 2. 更新 localStorage
            localStorage.setItem('travel_members', JSON.stringify(members));
            // 3. 確保 selectedPayers 裡也沒有他
            selectedPayers = selectedPayers.filter(p => p !== name);
            // 4. 重新渲染介面
            renderTravel();
        }
    }


    

        // 定義支援的國家與幣別
    const currencyConfigs = {
        'JPY': { name: '日圓', flag: '日圓' },
        'KRW': { name: '韓元', flag: '韓元' },
        'USD': { name: '美元', flag: '美元' },
        'EUR': { name: '歐元', flag: '歐元' },
        'THB': { name: '泰銖', flag: '泰銖' },
        'CNY': { name: '人民幣', flag: '人民幣' },
        'HKD': { name: '港幣', flag: '港幣' },
        'GBP': { name: '英鎊', flag: '英鎊' }
    };

    let latestRates = {};

    async function fetchRates() {
        try {
            const response = await fetch('https://open.er-api.com/v6/latest/TWD');
            const data = await response.json();
            if (data.result === "success") {
                latestRates = data.rates;
                initCurrencyDropdown();
                performConversion();
            }
        } catch (err) {
            document.getElementById('rateInfo').innerText = "";
        }
    }

    // 初始化下拉選單
    function initCurrencyDropdown() {
        const selector = document.getElementById('currencySelector');
        selector.innerHTML = Object.keys(currencyConfigs).map(code => {
            return `<option value="${code}">${currencyConfigs[code].flag} ${code}</option>`;
        }).join('');
    }

    // 執行換算
    function performConversion() {
        const amount = parseFloat(document.getElementById('foreignAmount').value) || 0;
        const code = document.getElementById('currencySelector').value;
        const resultDisplay = document.getElementById('twdResult');
        const infoDisplay = document.getElementById('rateInfo');

        if (!latestRates[code]) return;

        const rate = latestRates[code];
        // 公式：外幣金額 / 匯率 = 台幣
        const twd = amount / rate;

        // 渲染結果 (加上千分位與四捨五入)
        resultDisplay.innerText = Math.round(twd).toLocaleString();

        // 更新下方匯率小字
        const baseRate = (code === 'JPY' || code === 'KRW') ? rate.toFixed(2) : rate.toFixed(4);
        infoDisplay.innerHTML = `當前匯率：1 TWD = <b>${baseRate}</b> ${code}<br>更新於：${new Date().toLocaleTimeString()}`;
    }

    // 頁面載入後啟動
    document.addEventListener('DOMContentLoaded', fetchRates);

    const trans = {
        zh: { 
            welcome: "你好, ", logout: "登出", tab_home: "📅 日常記", tab_report: "📊 數據分析", tab_travel: "✈️ 旅遊分帳", add_btn: "+ 記一筆", todo_btn: "+ 待辦事項", 
            budget_label: "本月支出進度", summary_label: "收支淨額", rank_label: "支出排行", trend_label: "半年收支趨勢", set_btn: "設定",
            m_date: "日期", m_type: "類型", m_cat: "分類", m_amt: "金額", m_note: "備註", m_exp_opt: "支出", m_inc_opt: "收入", m_save_btn: "儲存", m_del: "刪除",
            bm_title: "設定每月預算", bm_limit: "每月支出上限 ($)", bm_save: "儲存設定",
            tr_members: "👥 旅伴名單", tr_add_m: "新增", tr_calc: "📊 結算結果", tr_calc_btn: "開始計算", tr_date: "日期", tr_note: "項目", tr_amt: "金額", tr_paid_by: "誰先付錢？", tr_split: "分攤成員：", tr_list: "📝 旅遊流水帳",
            todo_tag: "📌 待辦事項", chart_inc: "收入", chart_exp: "支出", chart_month: "月"
        },
        en: { 
            welcome: "Hi, ", logout: "Logout", tab_home: "📅 Home", tab_report: "📊 Reports", tab_travel: "✈️ Travel", add_btn: "+ Record", todo_btn: "+ Todo", 
            budget_label: "Monthly Budget", summary_label: "Net Balance", rank_label: "Expense Ranking", trend_label: "6-Month Trend", set_btn: "Set",
            m_date: "Date", m_type: "Type", m_cat: "Category", m_amt: "Amount", m_note: "Note", m_exp_opt: "Expense", m_inc_opt: "Income", m_save_btn: "Save", m_del: "Delete",
            bm_title: "Set Monthly Budget", bm_limit: "Limit ($)", bm_save: "Save",
            tr_members: "👥 Members", tr_add_m: "Add", tr_calc: "📊 Settlement", tr_calc_btn: "Calculate", tr_date: "Date", tr_note: "Note", tr_amt: "Amt", tr_paid_by: "Paid By", tr_split: "Spliters:", tr_list: "📝 Travel Log",
            todo_tag: "📌 Todo Task", chart_inc: "Inc", chart_exp: "Exp", chart_month: "M"
        }
    };

    document.getElementById('newsToggle').onclick = function(e) {
        e.stopPropagation(); // 防止點擊冒泡
        const newsBox = document.getElementById('newsBox');
        const isCollapsed = newsBox.classList.toggle('collapsed');
        
        // 根據狀態切換箭頭方向：收合時顯示向上，展開時顯示向下
        this.innerText = isCollapsed ? '▲' : '▼';
    };

    // 點擊新聞框本體時的邏輯 (如果您希望點擊框也能切換)
    document.getElementById('newsBox').onclick = function(e) {
        // 只有當點擊的不是切換按鈕本身時才執行
        if (e.target.id !== 'newsToggle') {
            const isCollapsed = this.classList.toggle('collapsed');
            document.getElementById('newsToggle').innerText = isCollapsed ? '▲' : '▼';
        }
    };

    // --- 修復：語系切換與變色 ---
    function toggleLang(l) {
        lang = l;
        // 更新按鈕變色
        document.getElementById('b-zh').classList.toggle('active', l==='zh');
        document.getElementById('b-en').classList.toggle('active', l==='en');
        
        // 更新文字 (確保 ID 匹配語系表)
        Object.keys(trans[lang]).forEach(k => {
            const domId = 't-' + k.replace(/_/g, '-');
            const el = document.getElementById(domId);
            if(el) {
                if(k === 'welcome') el.innerText = trans[lang][k] + userName;
                else el.innerText = trans[lang][k];
            }
        });
        refreshUI();
        if(window.location.hash === '#report') renderReport();
        if(window.location.hash === '#travel') renderTravel();
    }

    // --- 修復：支出排行補回 ---
    function renderReport() {
        let y = viewDate.getFullYear(), m = viewDate.getMonth();
        let monEs = entries.filter(e => { 
            let ed=new Date(e.date); 
            return ed.getFullYear()===y && ed.getMonth()===m && !e.is_todo && !e.is_travel; 
        });
        
        let totalExp = monEs.filter(e=>e.type==='支出').reduce((s,e)=>s+e.amount, 0);
        let totalInc = monEs.filter(e=>e.type==='收入').reduce((s,e)=>s+e.amount, 0);
        
        document.getElementById('budgetBar').style.width = Math.min((totalExp/userBudget)*100, 100) + '%';
        document.getElementById('spentLabel').innerText = `$${totalExp}`;
        document.getElementById('limitLabel').innerText = `$${userBudget}`;
        document.getElementById('netBalance').innerText = (totalInc-totalExp>=0?'+$':'-$') + Math.abs(totalInc-totalExp);

        // 支出排行邏輯
        let cats = {};
        monEs.filter(e=>e.type==='支出').forEach(e => { cats[e.category] = (cats[e.category] || 0) + e.amount; });
        let sorted = Object.entries(cats).sort((a,b) => b[1]-a[1]);
        document.getElementById('rankList').innerHTML = sorted.map(([c,v]) => `
            <div class="d-flex justify-content-between mb-2 small border-bottom pb-1">
                <span>${c}</span><span class="fw-bold text-danger">$${Math.round(v)}</span>
            </div>`).join('') || "No Records";

        // 半年趨勢圖
        let labels = [], incData = [], expData = [];
        for(let i=5; i>=0; i--) {
            let d = new Date(y, m-i, 1);
            labels.push(`${d.getMonth()+1}${trans[lang].chart_month}`);
            let es = entries.filter(e => { let ed = new Date(e.date); return ed.getFullYear()===d.getFullYear() && ed.getMonth()===d.getMonth() && !e.is_todo && !e.is_travel; });
            incData.push(es.filter(e=>e.type==='收入').reduce((s,e)=>s+e.amount, 0));
            expData.push(es.filter(e=>e.type==='支出').reduce((s,e)=>s+e.amount, 0));
        }
        if(trendChart) trendChart.destroy();
        trendChart = new Chart(document.getElementById('trendChart'), {
            type: 'bar',
            data: { labels, datasets: [{label:trans[lang].chart_inc, data:incData, backgroundColor:'#10b981'}, {label:trans[lang].chart_exp, data:expData, backgroundColor:'#f43f5e'}] },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    // --- 其餘邏輯維持 (新聞、分帳、日曆) ---
    function reloadAt(hash) { window.location.hash = hash; window.location.reload(); }
    async function updateBudget() {
        const val = document.getElementById('newBudgetVal').value;
        await fetch('/api/update_budget', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({budget:parseInt(val)}) });
        reloadAt('#report');
    }

    function calculateSettlement() {
        let balances = {}; members.forEach(m => balances[m] = 0);
        entries.filter(e => e.is_travel).forEach(e => {
            let share = e.amount / e.payers.length;
            balances[e.paid_by] += e.amount;
            e.payers.forEach(p => balances[p] -= share);
        });
        let res = [], debtors = [], creditors = [];
        Object.keys(balances).forEach(m => {
            if(balances[m] < -0.1) debtors.push({n:m, a:Math.abs(balances[m])});
            else if(balances[m] > 0.1) creditors.push({n:m, a:balances[m]});
        });
        debtors.forEach(d => {
            creditors.forEach(c => {
                if(d.a > 0 && c.a > 0) {
                    let pay = Math.min(d.a, c.a);
                    res.push(`${d.n} ➔ ${c.n} : $${pay.toFixed(0)}`);
                    d.a -= pay; c.a -= pay;
                }
            });
        });
        document.getElementById('settlementList').innerHTML = res.length ? res.join('<br>') : "已結清";
    }

    function renderTravel() {
        // 渲染旅伴與刪除按鈕
        document.getElementById('memberBadges').innerHTML = members.map(m => `
            <span class="badge bg-light text-dark border p-2 px-3 d-flex align-items-center gap-2">
                ${m}
                ${m !== '我' ? `<span style="cursor:pointer;" class="text-danger fw-bold" onclick="removeMember('${m}')">×</span>` : ''}
            </span>
        `).join('');

        // 更新下拉選單
        document.getElementById('trPaidBy').innerHTML = members.map(m => `<option value="${m}">${m}</option>`).join('');
        
        // 更新分攤勾選框
        document.getElementById('payerCheckboxes').innerHTML = members.map(m => `
            <button class="btn btn-sm ${selectedPayers.includes(m)?'btn-primary':'btn-outline-secondary'} mb-1" 
                    onclick="togglePayer('${m}')">${m}</button>
        `).join('');
    
        // 渲染旅遊清單 (加入刪除按鈕)
        const trEs = entries.filter(e => e.is_travel === true);
        document.getElementById('travelLog').innerHTML = trEs.map(e => `
            <div class="border-bottom py-2 d-flex justify-content-between align-items-center">
                <div>
                    <div class="fw-bold">${e.note}</div>
                    <div class="small text-muted">${e.date} | ${e.paid_by} 支付</div>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <span class="text-danger fw-bold me-2">$${e.amount}</span>
                    <button class="btn btn-sm btn-outline-primary" onclick="editTravel('${e.id}')">✎</button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteTravel('${e.id}')">✕</button>
                </div>
            </div>`).reverse().join('') || 'No Records';
    }

    function renderCalendar() {
        const grid = document.getElementById('calendarGrid'); grid.innerHTML = '';
        let y = viewDate.getFullYear(), m = viewDate.getMonth();
        document.getElementById('monthDisplay').innerText = `${y} / ${String(m+1).padStart(2,'0')}`;
        document.getElementById('yearSelect').value = y;
        let firstDay = new Date(y, m, 1).getDay(), daysInMonth = new Date(y, m + 1, 0).getDate();
        for(let i=0; i<firstDay; i++) grid.innerHTML += '<div class="calendar-day opacity-25"></div>';
        for(let d=1; d<=daysInMonth; d++) {
            let dStr = `${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
            let dayEs = entries.filter(e => e.date === dStr);
            let inc = dayEs.filter(e=>e.type==='收入' && !e.is_todo && !e.is_travel).reduce((s,e)=>s+e.amount, 0);
            let exp = dayEs.filter(e=>e.type==='支出' && !e.is_todo && !e.is_travel).reduce((s,e)=>s+e.amount, 0);
            grid.innerHTML += `<div class="calendar-day p-2 ${selectedDate===dStr?'selected':''} ${dStr===todayStr?'day-today':''}" onclick="selectDate('${dStr}')">
                <span class="day-num" style="font-weight:700;">${d}</span>
                ${inc>0?`<span class="day-val val-inc">+$${inc}</span>`:''}
                ${exp>0?`<span class="day-val val-exp">-$${exp}</span>`:''}
                ${dayEs.some(e=>e.is_todo) ? '<span class="day-val val-todo">📌</span>' : ''}
            </div>`;
        }
    }

    function renderDetail() {
        document.getElementById('detailDate').innerText = selectedDate;
        const dayEs = entries.filter(e => e.date === selectedDate && !e.is_travel);
        document.getElementById('detailList').innerHTML = dayEs.map(e => `
            <div class="card p-3 mb-2 shadow-sm border-0" onclick="editEntry('${e.id}')" style="cursor:pointer; background:#f8fafc; font-size:13px;">
                <div class="d-flex justify-content-between">
                    <div>
                        <div class="fw-bold">${e.is_todo ? trans[lang].todo_tag : e.category}</div>
                        <div class="text-muted small">${e.note||''}</div>
                    </div>
                    ${e.is_todo ? '' : `<span class="${e.type==='收入'?'text-success':'text-danger'} fw-bold">$${e.amount}</span>`}
                </div>
            </div>`).join('') || "No Records";
    }

    // 初始化與輔助函數
    function selectDate(d) { selectedDate = d; refreshUI(); }
    function changeMonth(s) { viewDate.setMonth(viewDate.getMonth() + s); refreshUI(); }
    function jumpDate() { viewDate.setFullYear(document.getElementById('yearSelect').value); refreshUI(); }
    function refreshUI() { renderCalendar(); renderDetail(); }
    function togglePayer(m) { let i=selectedPayers.indexOf(m); if(i>-1) selectedPayers.splice(i,1); else selectedPayers.push(m); renderTravel(); }
    function addMember() { let n = document.getElementById('newMemberName').value.trim(); if(n && !members.includes(n)) { members.push(n); localStorage.setItem('travel_members', JSON.stringify(members)); document.getElementById('newMemberName').value = ''; renderTravel(); } }
    
    // 新聞輪播
    const newsItems = { zh: ["財經：台股震盪走高", "匯率：日圓再創新低"], en: ["Stocks trend higher", "Yen hits new low"] };
    let nPos = 0;
    setInterval(() => {
        const title = document.getElementById('newsTitle');
        if(title) {
            title.style.opacity = 0;
            setTimeout(() => { title.innerText = newsItems[lang][nPos]; title.style.opacity = 1; nPos = (nPos+1)%newsItems[lang].length; }, 300);
        }
    }, 5000);

    const entryModal = new bootstrap.Modal(document.getElementById('entryModal'));
    function openModal(m) { document.getElementById('mId').value=""; document.getElementById('mIsTodo').value=m==='todo'?"1":"0"; document.getElementById('expFields').style.display=m==='todo'?'none':'block'; document.getElementById('mDate').value=selectedDate; updateCats(); entryModal.show(); }
    function updateCats() { const c = document.getElementById('mType').value==='支出' ? ["餐飲","交通","購物","娛樂","其他"] : ["薪水","投資","獎金"]; document.getElementById('mCat').innerHTML = c.map(x=>`<option value="${x}">${x}</option>`).join(''); }
    function editEntry(id) { let e = entries.find(x => String(x.id) === String(id)); document.getElementById('mId').value=e.id; document.getElementById('mDate').value=e.date; document.getElementById('mIsTodo').value=e.is_todo?"1":"0"; document.getElementById('expFields').style.display=e.is_todo?'none':'block'; document.getElementById('mNote').value=e.note; if(!e.is_todo) { document.getElementById('mType').value=e.type; updateCats(); document.getElementById('mCat').value=e.category; document.getElementById('mAmt').value=e.amount; } entryModal.show(); }
    async function saveEntry() { let p = { id: document.getElementById('mId').value, date: document.getElementById('mDate').value, is_todo: document.getElementById('mIsTodo').value === "1", type: document.getElementById('mType').value, category: document.getElementById('mIsTodo').value === "1" ? "Todo" : document.getElementById('mCat').value, amount: document.getElementById('mAmt').value, note: document.getElementById('mNote').value }; await fetch('/api/save', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }); location.reload(); }
    async function deleteTravel(id) {
        if (confirm("確定要刪除這筆旅遊花費嗎？")) {
            await fetch('/api/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ id: id })
            });
            
            // 刪除後從當前 entries 數組中移除，並重新渲染頁面
            entries = entries.filter(x => String(x.id) !== String(id));
            renderTravel(); 
            calculateSettlement(); // 重新計算分帳結果
            
            // 或者是為了確保數據完全同步，也可以使用：
            // reloadAt('#travel');
        }
    }
    
   async function deleteEntry() {
    const id = document.getElementById('mId').value;
    if (!id) return;

    if (confirm("確定要刪除這項記錄嗎？")) {
        try {
            const resp = await fetch('/api/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id })
            });
            const result = await resp.json();
                if (result.status === "success") {
                    entryModal.hide();
                    
                    // 修正點：刪除後將網址 hash 設為 home，並重新載入頁面
                    window.location.hash = "#home";
                    window.location.reload(); 
                }
            } catch (err) {
                console.error("刪除失敗:", err);
            }
        }
    }
    
    async function saveTravel() { let p = { id: document.getElementById('trEditId').value, type:"支出", category:"旅遊", amount:parseFloat(document.getElementById('trAmt').value), date:document.getElementById('trDate').value, note:document.getElementById('trNote').value, is_travel:true, paid_by:document.getElementById('trPaidBy').value, payers:selectedPayers }; await fetch('/api/save', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }); reloadAt('#travel'); }
    function editTravel(id) { let e = entries.find(x => String(x.id) === String(id)); document.getElementById('trEditId').value=e.id; document.getElementById('trNote').value=e.note; document.getElementById('trAmt').value=e.amount; document.getElementById('trPaidBy').value=e.paid_by; selectedPayers=[...e.payers]; document.getElementById('btnTrCancel').classList.remove('d-none'); renderTravel(); }
    function resetTrForm() { document.getElementById('trEditId').value=""; document.getElementById('trNote').value=""; document.getElementById('trAmt').value=""; selectedPayers=[]; document.getElementById('btnTrCancel').classList.add('d-none'); renderTravel(); }

    const ys = document.getElementById('yearSelect'); const cy = new Date().getFullYear();
    for(let i=cy-5; i<=cy+5; i++) { let o = document.createElement('option'); o.value=i; o.innerText=i; if(i===cy) o.selected=true; ys.appendChild(o); }

    window.onload = () => {
        // 原有的邏輯 (語系、日曆等)
        toggleLang('zh');
        
        // 新增匯率獲取
        fetchRates(); 
        
        // 如果網址有 hash，跳轉到對應頁籤
        let h = window.location.hash;
        if(h === '#report') { new bootstrap.Tab(document.getElementById('t-tab-report')).show(); renderReport(); }
        else if(h === '#travel') { new bootstrap.Tab(document.getElementById('t-tab-travel')).show(); renderTravel(); }
    };
</script>

</body></html>
"""
if __name__ == "__main__":


    app.run(debug=True)