from database import get_connection

class TripModel:
    @staticmethod
    def create_trip(name, date):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO trips (name, date) VALUES (?, ?)", (name, date))
        trip_id = cur.lastrowid
        conn.commit()
        conn.close()
        return trip_id

    @staticmethod
    def add_member(trip_id, name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, name))
        conn.commit()
        conn.close()

    @staticmethod
    def get_members(trip_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,))
        members = [row[0] for row in cur.fetchall()]
        conn.close()
        return members

class ExpenseModel:
    @staticmethod
    def create_expense(trip_id, desc, amount, payer):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO expenses (trip_id, description, amount, payer_name) VALUES (?, ?, ?, ?)", 
                    (trip_id, desc, amount, payer))
        conn.commit()
        conn.close()

    @staticmethod
    def get_all_expenses(trip_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, description, amount, payer_name FROM expenses WHERE trip_id = ?", (trip_id,))
        rows = cur.fetchall()
        conn.close()
        return rows

    @staticmethod
    def delete_expense(expense_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
        conn.close()
        
from datetime import date

class RecurringTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    type = db.Column(db.String(10), nullable=False)   # 'income' (收入) 或 'expense' (支出)
    category = db.Column(db.String(50), nullable=False) # 例如：薪資、房租、訂閱服務
    amount = db.Column(db.Float, nullable=False)      # 金額
    content = db.Column(db.String(200))               # 備註 (例如：15號發薪)
    
    # 週期設定
    # frequency: 'monthly' (每月), 'yearly' (每年)
    frequency = db.Column(db.String(20), default='monthly') 
    day_of_period = db.Column(db.Integer, nullable=False)   # 每月幾號 (1-31)
    
    # 防止重複入帳的機制
    last_processed = db.Column(db.Date) # 記錄上一次成功自動入帳的日期

    def __repr__(self):
        return f'<RecurringTask {self.category} {self.amount}>'