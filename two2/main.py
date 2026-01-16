from database import init_db
from models import TripModel, ExpenseModel
from calculator import TravelCalculator
import os

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    init_db()
    
    # 模擬建立一個專案 (CRUD - Create)
    t_name = "2024 日本行"
    t_id = TripModel.create_trip(t_name, "2024-12-25")
    
    # 新增成員
    group = ["小明", "小華", "阿強"]
    for m in group:
        TripModel.add_member(t_id, m)
        
    # 新增一些花費 (CRUD - Create)
    ExpenseModel.create_expense(t_id, "環球影城門票", 9000, "小明")
    ExpenseModel.create_expense(t_id, "居酒屋晚餐", 3000, "小華")
    ExpenseModel.create_expense(t_id, "JR Pass", 4500, "阿強")

    # 顯示主介面
    while True:
        clear_screen()
        print(f"=== {t_name} 管理系統 ===")
        members = TripModel.get_members(t_id)
        expenses = ExpenseModel.get_all_expenses(t_id)
        
        print(f"成員: {', '.join(members)}")
        print("-" * 30)
        print("ID | 項目 | 金額 | 付款人")
        for e in expenses:
            print(f"{e[0]} | {e[1]} | {e[2]} | {e[3]}")
        
        print("-" * 30)
        
        # 執行計算 (CRUD - Read)
        balances, avg = TravelCalculator.calculate_balances(members, expenses)
        print(f"總支出: {sum(e[2] for e in expenses)} | 平均每人應付: {avg:.2f}")
        print("\n結算狀態 (正數代表應收回，負數代表應付):")
        for name, bal in balances.items():
            status = "收回" if bal >= 0 else "付錢"
            print(f" > {name}: {status} {abs(bal):.2f} 元")
            
        print("\n[1] 新增花費 [2] 刪除花費 [3] 退出")
        choice = input("請選擇操作: ")
        
        if choice == "1":
            desc = input("項目名稱: ")
            amt = float(input("金額: "))
            payer = input(f"付款人 ({'/'.join(members)}): ")
            ExpenseModel.create_expense(t_id, desc, amt, payer)
        elif choice == "2":
            eid = int(input("輸入要刪除的支出 ID: "))
            ExpenseModel.delete_expense(eid)
        elif choice == "3":
            break

if __name__ == "__main__":
    main()