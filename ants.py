from __future__ import annotations

import calendar
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

APP_VERSION = "0.3.0"
APP_DIR = Path.home() / "Documents" / "ANTs"
DB_PATH = APP_DIR / "ants.db"
BACKUP_DIR = APP_DIR / "backups"

EXPENSE_CATEGORIES = [
    ("Logement", "Loyer / logement"),
    ("Alimentation", "Courses"),
    ("Alimentation", "Restaurant / restauration"),
    ("Transport", "Carburant"),
    ("Transport", "Train"),
    ("Transport", "Transports urbains"),
    ("Transport", "Parking / péage"),
    ("Transport", "Entretien véhicule"),
    ("Charges fixes", "Téléphone / Internet"),
    ("Charges fixes", "Assurance habitation"),
    ("Charges fixes", "Assurance automobile"),
    ("Charges fixes", "Frais bancaires"),
    ("Santé", "Santé"),
    ("Études", "Études"),
    ("Loisirs", "Loisirs"),
    ("Achats", "Achats"),
    ("Divers", "Divers"),
]
INCOME_CATEGORIES = [
    ("Revenus", "Salaire"),
    ("Revenus", "Prime"),
    ("Revenus", "Aide / allocation"),
    ("Revenus", "Remboursement"),
    ("Revenus", "Revenu exceptionnel"),
    ("Revenus", "Autre revenu"),
]
MOVEMENT_CATEGORIES = [
    ("Mouvements", "Retrait d'espèces"),
    ("Mouvements", "Dépôt d'espèces"),
    ("Mouvements", "Virement vers épargne"),
    ("Mouvements", "Virement depuis épargne"),
    ("Mouvements", "Virement interne"),
]


def app_db_path() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def backup_database(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"ants_avant_v030_{stamp}.db"
    if not target.exists():
        shutil.copy2(path, target)


def table_sql(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row[0] if row and row[0] else ""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            category_type TEXT NOT NULL DEFAULT 'expense',
            parent_name TEXT NOT NULL DEFAULT '',
            UNIQUE(name, category_type)
        )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)")}
    if "parent_name" not in cols:
        conn.execute("ALTER TABLE categories ADD COLUMN parent_name TEXT NOT NULL DEFAULT ''")

    tx_sql = table_sql(conn, "transactions")
    if not tx_sql:
        conn.execute("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('expense','income','movement')),
                amount REAL NOT NULL CHECK(amount >= 0),
                category_id INTEGER,
                label TEXT NOT NULL DEFAULT '',
                exceptional INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                routine INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(category_id) REFERENCES categories(id)
            )
        """)
    elif "movement" not in tx_sql:
        conn.execute("ALTER TABLE transactions RENAME TO transactions_old_v02")
        conn.execute("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('expense','income','movement')),
                amount REAL NOT NULL CHECK(amount >= 0),
                category_id INTEGER,
                label TEXT NOT NULL DEFAULT '',
                exceptional INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                routine INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(category_id) REFERENCES categories(id)
            )
        """)
        conn.execute("""
            INSERT INTO transactions(id, transaction_date, kind, amount, category_id, label, exceptional, created_at, routine)
            SELECT id, transaction_date, kind, amount, category_id, label,
                   COALESCE(exceptional,0), COALESCE(created_at,CURRENT_TIMESTAMP), COALESCE(routine,0)
            FROM transactions_old_v02
        """)
        conn.execute("DROP TABLE transactions_old_v02")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL CHECK(target_amount >= 0),
            target_date TEXT NOT NULL,
            saved_amount REAL NOT NULL DEFAULT 0 CHECK(saved_amount >= 0),
            status TEXT NOT NULL DEFAULT 'En préparation',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS savings_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            balance REAL NOT NULL DEFAULT 0 CHECK(balance >= 0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for parent, name in EXPENSE_CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO categories(name,active,category_type,parent_name) VALUES(?,1,'expense',?)", (name, parent))
    for parent, name in INCOME_CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO categories(name,active,category_type,parent_name) VALUES(?,1,'income',?)", (name, parent))
    for parent, name in MOVEMENT_CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO categories(name,active,category_type,parent_name) VALUES(?,1,'movement',?)", (name, parent))

    # Reclassement prudent des écritures connues, sans supprimer les anciennes catégories.
    rules = [
        ("expense", "carburant", "Carburant"),
        ("expense", "sncf", "Train"),
        ("expense", "ratp", "Transports urbains"),
        ("expense", "bouygues", "Téléphone / Internet"),
        ("expense", "direct assurance", "Assurance automobile"),
        ("expense", "maif", "Assurance habitation"),
        ("expense", "tenue de compte", "Frais bancaires"),
        ("expense", "intermarché", "Courses"),
        ("expense", "carrefour", "Courses"),
        ("expense", "boulangerie", "Courses"),
        ("expense", "restaurant", "Restaurant / restauration"),
        ("expense", "pizza", "Restaurant / restauration"),
    ]
    for kind, needle, target_name in rules:
        target = conn.execute("SELECT id FROM categories WHERE name=? AND category_type=?", (target_name, kind)).fetchone()
        if target:
            conn.execute("UPDATE transactions SET category_id=? WHERE kind=? AND lower(label) LIKE ?", (target[0], kind, f"%{needle}%"))

    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('schema_version','0.3.0')")
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")


class Database:
    def __init__(self, path: Path):
        self.path = path
        first = not path.exists()
        if not first:
            backup_database(path)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        ensure_schema(self.conn)

    def close(self):
        self.conn.close()

    def categories(self, kind: str):
        return self.conn.execute(
            "SELECT id,parent_name,name FROM categories WHERE active=1 AND category_type=? ORDER BY parent_name,name",
            (kind,),
        ).fetchall()

    def label_values(self):
        rows = self.conn.execute("SELECT DISTINCT label FROM transactions WHERE trim(label)<>'' ORDER BY label COLLATE NOCASE").fetchall()
        return [r[0] for r in rows]

    def learned_defaults(self, label: str):
        rows = self.conn.execute("""
            SELECT kind, category_id, routine, amount
            FROM transactions
            WHERE lower(trim(label))=lower(trim(?))
            ORDER BY transaction_date DESC, id DESC
        """, (label,)).fetchall()
        if not rows:
            return None
        kind = Counter(r["kind"] for r in rows).most_common(1)[0][0]
        category_id = Counter(r["category_id"] for r in rows if r["category_id"] is not None).most_common(1)
        routine = Counter(r["routine"] for r in rows).most_common(1)[0][0]
        avg_amount = sum(float(r["amount"]) for r in rows) / len(rows)
        return {"kind": kind, "category_id": category_id[0][0] if category_id else None, "routine": routine, "avg_amount": avg_amount}

    def month_transactions(self, year: int, month: int):
        start = f"{year:04d}-{month:02d}-01"
        last = calendar.monthrange(year, month)[1]
        end = f"{year:04d}-{month:02d}-{last:02d}"
        return self.conn.execute("""
            SELECT t.id,t.transaction_date,t.kind,t.amount,t.label,t.routine,
                   c.name AS category,c.parent_name AS parent
            FROM transactions t
            LEFT JOIN categories c ON c.id=t.category_id
            WHERE t.transaction_date BETWEEN ? AND ?
            ORDER BY t.transaction_date DESC,t.id DESC
        """, (start,end)).fetchall()

    def get_transaction(self, tx_id: int):
        return self.conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()

    def save_transaction(self, tx_id, tx_date, kind, amount, category_id, label, routine):
        if tx_id:
            self.conn.execute("""
                UPDATE transactions SET transaction_date=?,kind=?,amount=?,category_id=?,label=?,routine=?,exceptional=? WHERE id=?
            """, (tx_date,kind,amount,category_id,label,routine,0 if routine else 1,tx_id))
        else:
            self.conn.execute("""
                INSERT INTO transactions(transaction_date,kind,amount,category_id,label,routine,exceptional)
                VALUES(?,?,?,?,?,?,?)
            """, (tx_date,kind,amount,category_id,label,routine,0 if routine else 1))
        self.conn.commit()

    def delete_transaction(self, tx_id):
        self.conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        self.conn.commit()

    def savings(self):
        return self.conn.execute("SELECT * FROM savings_accounts ORDER BY name").fetchall()

    def add_saving(self, name, balance):
        self.conn.execute("INSERT INTO savings_accounts(name,balance,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)", (name,balance))
        self.conn.commit()

    def update_saving(self, sid, balance):
        self.conn.execute("UPDATE savings_accounts SET balance=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (balance,sid))
        self.conn.commit()

    def delete_saving(self, sid):
        self.conn.execute("DELETE FROM savings_accounts WHERE id=?", (sid,))
        self.conn.commit()


MONTHS = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
KIND_LABELS = {"expense":"Dépense", "income":"Revenu", "movement":"Mouvement"}
LABEL_KINDS = {v:k for k,v in KIND_LABELS.items()}


class TransactionDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, year: int, month: int, tx_id=None):
        super().__init__(parent)
        self.db, self.tx_id = db, tx_id
        self.title("Modifier l'écriture" if tx_id else "Nouvelle écriture")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.kind_var = tk.StringVar(value="Dépense")
        self.date_var = tk.StringVar(value=self.default_date(year, month))
        self.label_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.routine_var = tk.BooleanVar(value=False)
        self.hint_var = tk.StringVar(value="")
        self.category_map = {}

        frame = ttk.Frame(self, padding=18)
        frame.grid(sticky="nsew")
        labels = ["Type", "Date (AAAA-MM-JJ)", "Libellé", "Montant (€)", "Poste"]
        for i, text in enumerate(labels):
            ttk.Label(frame, text=text).grid(row=i, column=0, sticky="w", pady=5, padx=(0,12))
        self.kind_box = ttk.Combobox(frame, textvariable=self.kind_var, values=list(LABEL_KINDS), state="readonly", width=33)
        self.kind_box.grid(row=0,column=1,sticky="ew",pady=5)
        ttk.Entry(frame,textvariable=self.date_var,width=36).grid(row=1,column=1,sticky="ew",pady=5)
        self.label_box = ttk.Combobox(frame,textvariable=self.label_var,values=db.label_values(),width=33)
        self.label_box.grid(row=2,column=1,sticky="ew",pady=5)
        ttk.Entry(frame,textvariable=self.amount_var,width=36).grid(row=3,column=1,sticky="ew",pady=5)
        self.category_box = ttk.Combobox(frame,textvariable=self.category_var,state="readonly",width=33)
        self.category_box.grid(row=4,column=1,sticky="ew",pady=5)
        ttk.Checkbutton(frame,text="Écriture courante / récurrente",variable=self.routine_var).grid(row=5,column=1,sticky="w",pady=(6,2))
        ttk.Label(frame,textvariable=self.hint_var,foreground="#666").grid(row=6,column=1,sticky="w",pady=(0,10))
        buttons = ttk.Frame(frame)
        buttons.grid(row=7,column=0,columnspan=2,sticky="e")
        ttk.Button(buttons,text="Annuler",command=self.destroy).pack(side="right",padx=(8,0))
        ttk.Button(buttons,text="Enregistrer",command=self.save).pack(side="right")

        self.kind_box.bind("<<ComboboxSelected>>", lambda e:self.refresh_categories())
        self.label_box.bind("<<ComboboxSelected>>", lambda e:self.apply_learning())
        self.label_box.bind("<FocusOut>", lambda e:self.apply_learning())
        self.refresh_categories()
        if tx_id:
            self.load(tx_id)
        self.label_box.focus_set()

    @staticmethod
    def default_date(year, month):
        today = date.today()
        if (year,month)==(today.year,today.month):
            return today.isoformat()
        return f"{year:04d}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}"

    def refresh_categories(self, selected_id=None):
        kind = LABEL_KINDS[self.kind_var.get()]
        rows = self.db.categories(kind)
        self.category_map = {f"{r['parent_name']} › {r['name']}": r['id'] for r in rows}
        self.category_box["values"] = list(self.category_map)
        if selected_id:
            for text,cid in self.category_map.items():
                if cid==selected_id:
                    self.category_var.set(text); return
        if self.category_map and self.category_var.get() not in self.category_map:
            self.category_var.set(next(iter(self.category_map)))

    def apply_learning(self):
        label = self.label_var.get().strip()
        if not label: return
        defaults = self.db.learned_defaults(label)
        if not defaults: return
        self.kind_var.set(KIND_LABELS[defaults["kind"]])
        self.refresh_categories(defaults["category_id"])
        self.routine_var.set(bool(defaults["routine"]))
        self.hint_var.set(f"ANTs reconnaît ce libellé · montant moyen {defaults['avg_amount']:.2f} €")

    def load(self, tx_id):
        r = self.db.get_transaction(tx_id)
        if not r: return
        self.kind_var.set(KIND_LABELS[r["kind"]])
        self.date_var.set(r["transaction_date"])
        self.label_var.set(r["label"])
        self.amount_var.set(str(r["amount"]).replace(".",","))
        self.routine_var.set(bool(r["routine"]))
        self.refresh_categories(r["category_id"])

    def save(self):
        try:
            datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d")
            amount = float(self.amount_var.get().replace(",","."))
            if amount < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Saisie incorrecte", "Vérifie la date et le montant.", parent=self)
            return
        label = self.label_var.get().strip()
        if not label:
            messagebox.showerror("Libellé manquant", "Renseigne un libellé.", parent=self); return
        category_id = self.category_map.get(self.category_var.get())
        self.db.save_transaction(self.tx_id,self.date_var.get().strip(),LABEL_KINDS[self.kind_var.get()],amount,category_id,label,int(self.routine_var.get()))
        self.destroy()
        self.master.refresh_all()


class SavingsDialog(tk.Toplevel):
    def __init__(self,parent,db,refresh):
        super().__init__(parent); self.db=db; self.refresh_callback=refresh
        self.title("Épargne"); self.geometry("480x330"); self.transient(parent); self.grab_set()
        self.tree=ttk.Treeview(self,columns=("name","balance"),show="headings",height=8)
        self.tree.heading("name",text="Compte"); self.tree.heading("balance",text="Solde")
        self.tree.column("name",width=280); self.tree.column("balance",width=140,anchor="e")
        self.tree.pack(fill="both",expand=True,padx=12,pady=12)
        bar=ttk.Frame(self); bar.pack(fill="x",padx=12,pady=(0,12))
        ttk.Button(bar,text="Ajouter",command=self.add).pack(side="left")
        ttk.Button(bar,text="Modifier",command=self.edit).pack(side="left",padx=6)
        ttk.Button(bar,text="Supprimer",command=self.delete).pack(side="left")
        ttk.Button(bar,text="Fermer",command=self.close).pack(side="right")
        self.load()
    def load(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.db.savings(): self.tree.insert("", "end", iid=str(r["id"]), values=(r["name"],f"{r['balance']:.2f} €"))
    def prompt(self,title,default_name="",default_balance=""):
        w=tk.Toplevel(self); w.title(title); w.resizable(False,False); w.transient(self); w.grab_set()
        n=tk.StringVar(value=default_name); b=tk.StringVar(value=default_balance)
        f=ttk.Frame(w,padding=15); f.pack()
        ttk.Label(f,text="Nom").grid(row=0,column=0,sticky="w",pady=5); ttk.Entry(f,textvariable=n,width=28).grid(row=0,column=1,pady=5)
        ttk.Label(f,text="Solde (€)").grid(row=1,column=0,sticky="w",pady=5); ttk.Entry(f,textvariable=b,width=28).grid(row=1,column=1,pady=5)
        result={}
        def ok():
            try: val=float(b.get().replace(",",".")); assert val>=0
            except Exception: messagebox.showerror("Erreur","Montant incorrect",parent=w); return
            if not n.get().strip(): return
            result.update(name=n.get().strip(),balance=val); w.destroy()
        ttk.Button(f,text="Valider",command=ok).grid(row=2,column=1,sticky="e",pady=(10,0))
        self.wait_window(w); return result or None
    def add(self):
        r=self.prompt("Ajouter un compte")
        if r:
            try:self.db.add_saving(r["name"],r["balance"])
            except sqlite3.IntegrityError: messagebox.showerror("Erreur","Ce compte existe déjà",parent=self)
            self.load()
    def edit(self):
        sel=self.tree.selection()
        if not sel:return
        vals=self.tree.item(sel[0],"values"); r=self.prompt("Modifier le solde",vals[0],vals[1].replace(" €",""))
        if r:self.db.update_saving(int(sel[0]),r["balance"]); self.load()
    def delete(self):
        sel=self.tree.selection()
        if sel and messagebox.askyesno("Confirmer","Supprimer ce compte d'épargne ?",parent=self): self.db.delete_saving(int(sel[0])); self.load()
    def close(self): self.refresh_callback(); self.destroy()


class ANTsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.db = Database(app_db_path())
        today=date.today(); self.year=today.year; self.month=today.month
        self.title(f"ANTs — v{APP_VERSION}"); self.geometry("1080x690"); self.minsize(900,560)
        self.protocol("WM_DELETE_WINDOW",self.on_close)
        self.make_ui(); self.refresh_all()

    def make_ui(self):
        style=ttk.Style(self)
        try: style.theme_use("vista")
        except tk.TclError: pass
        root=ttk.Frame(self,padding=16); root.pack(fill="both",expand=True)
        top=ttk.Frame(root); top.pack(fill="x")
        ttk.Label(top,text="ANTs",font=("Segoe UI",22,"bold")).pack(side="left")
        ttk.Label(top,text="  Journal financier personnel",font=("Segoe UI",11)).pack(side="left",pady=(8,0))
        ttk.Button(top,text="Épargne",command=lambda:SavingsDialog(self,self.db,self.refresh_all)).pack(side="right")
        ttk.Button(top,text="Nouvelle écriture",command=self.add_transaction).pack(side="right",padx=8)

        nav=ttk.Frame(root); nav.pack(fill="x",pady=(18,10))
        ttk.Button(nav,text="◀",width=4,command=lambda:self.shift_month(-1)).pack(side="left")
        self.month_label=ttk.Label(nav,font=("Segoe UI",16,"bold"),anchor="center")
        self.month_label.pack(side="left",fill="x",expand=True)
        ttk.Button(nav,text="▶",width=4,command=lambda:self.shift_month(1)).pack(side="right")

        cards=ttk.Frame(root); cards.pack(fill="x",pady=(0,12))
        self.card_vars={k:tk.StringVar() for k in ("income","expense","movement","balance","savings")}
        titles=[("Revenus","income"),("Dépenses","expense"),("Mouvements","movement"),("Solde du mois","balance"),("Épargne","savings")]
        for i,(title,key) in enumerate(titles):
            card=ttk.LabelFrame(cards,text=title,padding=10); card.grid(row=0,column=i,sticky="ew",padx=(0 if i==0 else 6,0)); cards.columnconfigure(i,weight=1)
            ttk.Label(card,textvariable=self.card_vars[key],font=("Segoe UI",13,"bold")).pack()

        columns=("date","type","label","category","routine","amount")
        self.tree=ttk.Treeview(root,columns=columns,show="headings",selectmode="browse")
        headings={"date":"Date","type":"Type","label":"Libellé","category":"Poste","routine":"Récurrente","amount":"Montant"}
        widths={"date":95,"type":100,"label":300,"category":260,"routine":90,"amount":110}
        for c in columns:
            self.tree.heading(c,text=headings[c]); self.tree.column(c,width=widths[c],anchor="e" if c=="amount" else "center" if c in ("date","type","routine") else "w")
        self.tree.pack(fill="both",expand=True)
        self.tree.bind("<Double-1>",lambda e:self.edit_transaction())
        bottom=ttk.Frame(root); bottom.pack(fill="x",pady=(10,0))
        ttk.Label(bottom,text="Double-clique sur une ligne pour la modifier.").pack(side="left")
        ttk.Button(bottom,text="Supprimer",command=self.delete_transaction).pack(side="right")
        ttk.Button(bottom,text="Modifier",command=self.edit_transaction).pack(side="right",padx=8)

    def shift_month(self,delta):
        idx=self.year*12+(self.month-1)+delta; self.year,self.month=divmod(idx,12); self.month+=1; self.refresh_all()
    def add_transaction(self): TransactionDialog(self,self.db,self.year,self.month)
    def selected_id(self):
        s=self.tree.selection(); return int(s[0]) if s else None
    def edit_transaction(self):
        tx=self.selected_id()
        if tx: TransactionDialog(self,self.db,self.year,self.month,tx)
    def delete_transaction(self):
        tx=self.selected_id()
        if tx and messagebox.askyesno("Confirmer","Supprimer cette écriture ?",parent=self): self.db.delete_transaction(tx); self.refresh_all()
    def refresh_all(self):
        self.month_label.config(text=f"{MONTHS[self.month-1].capitalize()} {self.year}")
        rows=self.db.month_transactions(self.year,self.month)
        self.tree.delete(*self.tree.get_children())
        totals={"income":0.0,"expense":0.0,"movement":0.0}
        for r in rows:
            totals[r["kind"]]+=float(r["amount"])
            sign="+" if r["kind"]=="income" else "−" if r["kind"]=="expense" else "↔"
            cat=" › ".join(x for x in (r["parent"],r["category"]) if x)
            self.tree.insert("","end",iid=str(r["id"]),values=(
                datetime.strptime(r["transaction_date"],"%Y-%m-%d").strftime("%d/%m/%Y"),
                KIND_LABELS[r["kind"]],r["label"],cat,"Oui" if r["routine"] else "Non",f"{sign} {r['amount']:.2f} €"
            ))
        savings=sum(float(r["balance"]) for r in self.db.savings())
        self.card_vars["income"].set(f"{totals['income']:.2f} €")
        self.card_vars["expense"].set(f"{totals['expense']:.2f} €")
        self.card_vars["movement"].set(f"{totals['movement']:.2f} €")
        self.card_vars["balance"].set(f"{totals['income']-totals['expense']:.2f} €")
        self.card_vars["savings"].set(f"{savings:.2f} €")
    def on_close(self): self.db.close(); self.destroy()


def main():
    try:
        app=ANTsApp(); app.mainloop()
    except Exception as exc:
        messagebox.showerror("ANTs",f"ANTs n'a pas pu démarrer.\n\n{exc}")
        raise

if __name__=="__main__": main()
