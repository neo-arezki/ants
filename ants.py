from __future__ import annotations

import calendar
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

APP_VERSION = "0.4.0"
APP_DIR = Path.home() / "Documents" / "ANTs"
DB_PATH = APP_DIR / "ants.db"
BACKUP_DIR = APP_DIR / "backups"
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
KIND_LABELS = {"expense": "Dépense", "income": "Revenu", "movement": "Mouvement"}
LABEL_KINDS = {v: k for k, v in KIND_LABELS.items()}
STATUS_LABELS = {"confirmed": "Confirmée", "planned": "Prévisionnelle"}
LABEL_STATUSES = {v: k for k, v in STATUS_LABELS.items()}

EXPENSE_CATEGORIES = [
    ("Logement", "Loyer / logement", "🏠", 1),
    ("Logement", "Énergie / eau", "💡", 1),
    ("Logement", "Entretien du logement", "🧰", 0),
    ("Alimentation", "Courses", "🛒", 0),
    ("Alimentation", "Boulangerie", "🥖", 0),
    ("Alimentation", "Restaurant / restauration", "🍽", 0),
    ("Alimentation", "Fast-food", "🍔", 0),
    ("Transport", "Carburant", "⛽", 0),
    ("Transport", "Train", "🚆", 0),
    ("Transport", "Transports urbains", "🚇", 0),
    ("Transport", "Taxi / VTC", "🚕", 0),
    ("Transport", "Parking / péage", "🅿", 0),
    ("Transport", "Entretien véhicule", "🚗", 0),
    ("Télécommunications", "Téléphone / Internet", "📱", 1),
    ("Assurances", "Assurance habitation", "🛡", 1),
    ("Assurances", "Assurance automobile", "🛡", 1),
    ("Banque", "Frais bancaires", "🏦", 1),
    ("Santé", "Santé", "🩺", 0),
    ("Études", "Université / inscription", "🎓", 0),
    ("Études", "Livres", "📚", 0),
    ("Études", "Matériel", "🖊", 0),
    ("Études", "Formation", "🧠", 0),
    ("Loisirs", "Vie sociale / bar / café", "🍺", 0),
    ("Loisirs", "Cinéma", "🎬", 0),
    ("Loisirs", "Théâtre", "🎭", 0),
    ("Loisirs", "Musée / exposition", "🖼", 0),
    ("Loisirs", "Festival / concert", "🎪", 0),
    ("Loisirs", "Cours de musique", "🎹", 1),
    ("Loisirs", "Jeux vidéo", "🎮", 0),
    ("Loisirs", "Streaming", "📺", 1),
    ("Achats", "Équipement", "🧰", 0),
    ("Achats", "Matériel informatique", "💻", 0),
    ("Achats", "Tabac", "🚬", 0),
    ("Achats", "Cadeaux", "🎁", 0),
    ("Achats", "Achats divers", "🛍", 0),
    ("Divers", "Divers", "📦", 0),
]
INCOME_CATEGORIES = [
    ("Revenus", "Salaire", "💼", 1),
    ("Revenus", "Prime", "✨", 0),
    ("Revenus", "Aide / allocation", "🤝", 1),
    ("Revenus", "Remboursement", "↩", 0),
    ("Revenus", "Revenu exceptionnel", "⭐", 0),
    ("Revenus", "Autre revenu", "💶", 0),
]
MOVEMENT_CATEGORIES = [
    ("Mouvements", "Retrait d'espèces", "🏧", 0),
    ("Mouvements", "Dépôt d'espèces", "💵", 0),
    ("Mouvements", "Virement vers épargne", "↗", 0),
    ("Mouvements", "Virement depuis épargne", "↙", 0),
    ("Mouvements", "Virement interne", "🔄", 0),
]


def app_db_path() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def backup_database(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"ants_avant_v040_{stamp}.db"
    if not target.exists():
        shutil.copy2(path, target)


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not table_exists(conn, name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({name})")}


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
            icon TEXT NOT NULL DEFAULT '•',
            default_fixed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(name, category_type)
        )
    """)
    cat_cols = table_columns(conn, "categories")
    for col, ddl in (
        ("parent_name", "TEXT NOT NULL DEFAULT ''"),
        ("icon", "TEXT NOT NULL DEFAULT '•'"),
        ("default_fixed", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in cat_cols:
            conn.execute(f"ALTER TABLE categories ADD COLUMN {col} {ddl}")

    if not table_exists(conn, "transactions"):
        conn.execute("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                category_id INTEGER,
                label TEXT NOT NULL DEFAULT '',
                exceptional INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                routine INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'confirmed',
                date_known INTEGER NOT NULL DEFAULT 1,
                project_id INTEGER,
                comment TEXT NOT NULL DEFAULT ''
            )
        """)
    else:
        tx_cols = table_columns(conn, "transactions")
        additions = {
            "routine": "INTEGER NOT NULL DEFAULT 0",
            "exceptional": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'confirmed'",
            "date_known": "INTEGER NOT NULL DEFAULT 1",
            "project_id": "INTEGER",
            "comment": "TEXT NOT NULL DEFAULT ''",
        }
        for col, ddl in additions.items():
            if col not in tx_cols:
                conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} {ddl}")

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

    for kind, rows in (("expense", EXPENSE_CATEGORIES), ("income", INCOME_CATEGORIES), ("movement", MOVEMENT_CATEGORIES)):
        for parent, name, icon, recurring in rows:
            conn.execute(
                "INSERT OR IGNORE INTO categories(name,active,category_type,parent_name,icon,default_fixed) VALUES(?,1,?,?,?,?)",
                (name, kind, parent, icon, recurring),
            )
            conn.execute(
                "UPDATE categories SET parent_name=?, icon=?, default_fixed=? WHERE name=? AND category_type=?",
                (parent, icon, recurring, name, kind),
            )

    # Reclassement prudent : uniquement les libellés suffisamment explicites.
    rules = [
        ("expense", "loyer", "Loyer / logement"),
        ("expense", "carburant", "Carburant"),
        ("expense", "sncf", "Train"),
        ("expense", "ratp", "Transports urbains"),
        ("expense", "uber", "Taxi / VTC"),
        ("expense", "bolt", "Taxi / VTC"),
        ("expense", "bouygues", "Téléphone / Internet"),
        ("expense", "direct assurance", "Assurance automobile"),
        ("expense", "maif", "Assurance habitation"),
        ("expense", "tenue de compte", "Frais bancaires"),
        ("expense", "intermarché", "Courses"),
        ("expense", "carrefour", "Courses"),
        ("expense", "boulangerie", "Boulangerie"),
        ("expense", "restaurant", "Restaurant / restauration"),
        ("expense", "pizza", "Fast-food"),
        ("expense", "burger", "Fast-food"),
        ("expense", "bar", "Vie sociale / bar / café"),
        ("expense", "café", "Vie sociale / bar / café"),
        ("expense", "cinéma", "Cinéma"),
        ("expense", "theatre", "Théâtre"),
        ("expense", "théâtre", "Théâtre"),
        ("expense", "festival", "Festival / concert"),
        ("expense", "concert", "Festival / concert"),
        ("expense", "piano", "Cours de musique"),
        ("expense", "steam", "Jeux vidéo"),
        ("expense", "netflix", "Streaming"),
        ("expense", "batterie lenovo", "Matériel informatique"),
        ("expense", "cvec", "Université / inscription"),
        ("expense", "tabac", "Tabac"),
        ("expense", "clope", "Tabac"),
        ("movement", "retrait", "Retrait d'espèces"),
    ]
    for kind, needle, target_name in rules:
        target = conn.execute("SELECT id FROM categories WHERE name=? AND category_type=?", (target_name, kind)).fetchone()
        if target:
            conn.execute(
                "UPDATE transactions SET category_id=? WHERE kind=? AND lower(label) LIKE ?",
                (target[0], kind, f"%{needle.lower()}%"),
            )

    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('schema_version',?)", (APP_VERSION,))
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")


class Database:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            backup_database(path)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        ensure_schema(self.conn)

    def close(self):
        self.conn.close()

    def categories(self, kind: str):
        return self.conn.execute(
            "SELECT id,parent_name,name,icon,default_fixed FROM categories WHERE active=1 AND category_type=? ORDER BY parent_name,name",
            (kind,),
        ).fetchall()

    def projects(self):
        return self.conn.execute("SELECT * FROM projects ORDER BY target_date, name").fetchall()

    def project_map(self):
        return {row["name"]: row["id"] for row in self.projects()}

    def label_values(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT label FROM transactions WHERE trim(label)<>'' ORDER BY label COLLATE NOCASE")]

    def learned_defaults(self, label: str):
        rows = self.conn.execute(
            "SELECT kind,category_id,routine,amount,project_id FROM transactions WHERE lower(trim(label))=lower(trim(?)) ORDER BY transaction_date DESC,id DESC",
            (label,),
        ).fetchall()
        if not rows:
            return None
        kind = Counter(r["kind"] for r in rows).most_common(1)[0][0]
        cids = [r["category_id"] for r in rows if r["category_id"] is not None]
        pids = [r["project_id"] for r in rows if r["project_id"] is not None]
        return {
            "kind": kind,
            "category_id": Counter(cids).most_common(1)[0][0] if cids else None,
            "routine": Counter(r["routine"] for r in rows).most_common(1)[0][0],
            "avg_amount": sum(float(r["amount"]) for r in rows) / len(rows),
            "project_id": Counter(pids).most_common(1)[0][0] if pids else None,
        }

    def month_transactions(self, year: int, month: int):
        start = f"{year:04d}-{month:02d}-01"
        end = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        return self.conn.execute("""
            SELECT t.id,t.transaction_date,t.kind,t.amount,t.label,t.routine,t.status,t.date_known,t.comment,t.project_id,
                   c.name AS category,c.parent_name AS parent,c.icon,c.default_fixed,
                   p.name AS project_name
            FROM transactions t
            LEFT JOIN categories c ON c.id=t.category_id
            LEFT JOIN projects p ON p.id=t.project_id
            WHERE t.transaction_date BETWEEN ? AND ?
            ORDER BY t.transaction_date DESC,t.id DESC
        """, (start, end)).fetchall()

    def previous_month_rows(self, year: int, month: int):
        idx = year * 12 + month - 2
        py, pm0 = divmod(idx, 12)
        pm = pm0 + 1
        return self.month_transactions(py, pm)

    def get_transaction(self, tx_id: int):
        return self.conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()

    def save_transaction(self, tx_id, tx_date, kind, amount, category_id, label, routine, status, date_known, project_id, comment):
        params = (tx_date, kind, amount, category_id, label, routine, 0 if routine else 1, status, date_known, project_id, comment)
        if tx_id:
            self.conn.execute(
                "UPDATE transactions SET transaction_date=?,kind=?,amount=?,category_id=?,label=?,routine=?,exceptional=?,status=?,date_known=?,project_id=?,comment=? WHERE id=?",
                params + (tx_id,),
            )
        else:
            self.conn.execute(
                "INSERT INTO transactions(transaction_date,kind,amount,category_id,label,routine,exceptional,status,date_known,project_id,comment) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                params,
            )
        self.conn.commit()

    def delete_transaction(self, tx_id: int):
        self.conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        self.conn.commit()

    def import_recurring(self, year: int, month: int) -> int:
        target_start = f"{year:04d}-{month:02d}-01"
        target_end = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        candidates = self.conn.execute("""
            SELECT t.* FROM transactions t
            JOIN (
                SELECT lower(trim(label)) key, MAX(transaction_date || printf('%010d', id)) marker
                FROM transactions
                WHERE routine=1 AND kind IN ('expense','income') AND transaction_date < ?
                GROUP BY lower(trim(label))
            ) latest ON lower(trim(t.label))=latest.key
                         AND (t.transaction_date || printf('%010d', t.id))=latest.marker
            ORDER BY t.label COLLATE NOCASE
        """, (target_start,)).fetchall()
        count = 0
        for row in candidates:
            exists = self.conn.execute(
                "SELECT 1 FROM transactions WHERE lower(trim(label))=lower(trim(?)) AND transaction_date BETWEEN ? AND ?",
                (row["label"], target_start, target_end),
            ).fetchone()
            if exists:
                continue
            self.conn.execute("""
                INSERT INTO transactions(transaction_date,kind,amount,category_id,label,routine,exceptional,status,date_known,project_id,comment)
                VALUES(?,?,?,?,?,1,0,'planned',0,?,?)
            """, (target_start, row["kind"], row["amount"], row["category_id"], row["label"], row["project_id"], "Importée depuis les écritures habituelles"))
            count += 1
        self.conn.commit()
        return count

    def savings(self):
        return self.conn.execute("SELECT * FROM savings_accounts ORDER BY name").fetchall()

    def add_saving(self, name: str, balance: float):
        self.conn.execute("INSERT INTO savings_accounts(name,balance,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)", (name, balance)); self.conn.commit()

    def update_saving(self, sid: int, balance: float):
        self.conn.execute("UPDATE savings_accounts SET balance=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (balance, sid)); self.conn.commit()

    def delete_saving(self, sid: int):
        self.conn.execute("DELETE FROM savings_accounts WHERE id=?", (sid,)); self.conn.commit()

    def save_project(self, pid, name, target_amount, target_date, saved_amount, status):
        if pid:
            self.conn.execute("UPDATE projects SET name=?,target_amount=?,target_date=?,saved_amount=?,status=? WHERE id=?", (name, target_amount, target_date, saved_amount, status, pid))
        else:
            self.conn.execute("INSERT INTO projects(name,target_amount,target_date,saved_amount,status) VALUES(?,?,?,?,?)", (name, target_amount, target_date, saved_amount, status))
        self.conn.commit()

    def delete_project(self, pid):
        self.conn.execute("UPDATE transactions SET project_id=NULL WHERE project_id=?", (pid,))
        self.conn.execute("DELETE FROM projects WHERE id=?", (pid,)); self.conn.commit()


class TransactionDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, year: int, month: int, tx_id=None):
        super().__init__(parent)
        self.db, self.tx_id = db, tx_id
        self.title("Modifier l'écriture" if tx_id else "Nouvelle écriture")
        self.resizable(False, False); self.transient(parent); self.grab_set()
        is_future = (year, month) > (date.today().year, date.today().month)
        self.kind_var = tk.StringVar(value="Dépense")
        self.date_var = tk.StringVar(value=self.default_date(year, month))
        self.date_known_var = tk.BooleanVar(value=not is_future)
        self.label_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.routine_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Prévisionnelle" if is_future else "Confirmée")
        self.project_var = tk.StringVar(value="Aucun projet")
        self.comment_var = tk.StringVar()
        self.hint_var = tk.StringVar()
        self.category_map = {}
        self.projects = {"Aucun projet": None, **db.project_map()}

        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        labels = ("Type", "Statut", "Date (AAAA-MM-JJ)", "Libellé", "Montant (€)", "Poste", "Projet", "Commentaire")
        for i, text in enumerate(labels):
            ttk.Label(frame, text=text).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 12))
        self.kind_box = ttk.Combobox(frame, textvariable=self.kind_var, values=list(LABEL_KINDS), state="readonly", width=42); self.kind_box.grid(row=0, column=1, pady=5)
        ttk.Combobox(frame, textvariable=self.status_var, values=list(LABEL_STATUSES), state="readonly", width=42).grid(row=1, column=1, pady=5)
        date_row = ttk.Frame(frame); date_row.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Entry(date_row, textvariable=self.date_var, width=25).pack(side="left")
        ttk.Checkbutton(date_row, text="Date connue", variable=self.date_known_var).pack(side="left", padx=(10, 0))
        self.label_box = ttk.Combobox(frame, textvariable=self.label_var, values=db.label_values(), width=42); self.label_box.grid(row=3, column=1, pady=5)
        ttk.Entry(frame, textvariable=self.amount_var, width=45).grid(row=4, column=1, pady=5)
        self.category_box = ttk.Combobox(frame, textvariable=self.category_var, state="readonly", width=42); self.category_box.grid(row=5, column=1, pady=5)
        ttk.Combobox(frame, textvariable=self.project_var, values=list(self.projects), state="readonly", width=42).grid(row=6, column=1, pady=5)
        ttk.Entry(frame, textvariable=self.comment_var, width=45).grid(row=7, column=1, pady=5)
        ttk.Checkbutton(frame, text="Écriture habituelle / récurrente", variable=self.routine_var).grid(row=8, column=1, sticky="w", pady=(7, 2))
        ttk.Label(frame, textvariable=self.hint_var, foreground="#5f6b7a").grid(row=9, column=1, sticky="w", pady=(0, 10))
        buttons = ttk.Frame(frame); buttons.grid(row=10, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Enregistrer", command=self.save).pack(side="right")
        self.kind_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_categories())
        self.label_box.bind("<<ComboboxSelected>>", lambda _e: self.apply_learning())
        self.label_box.bind("<FocusOut>", lambda _e: self.apply_learning())
        self.refresh_categories()
        if tx_id:
            self.load(tx_id)
        self.label_box.focus_set()

    @staticmethod
    def default_date(year, month):
        today = date.today()
        if (year, month) == (today.year, today.month):
            return today.isoformat()
        return f"{year:04d}-{month:02d}-01"

    def refresh_categories(self, selected_id=None):
        kind = LABEL_KINDS[self.kind_var.get()]
        rows = self.db.categories(kind)
        self.category_map = {f"{r['icon']}  {r['parent_name']} › {r['name']}": (r['id'], r['default_fixed']) for r in rows}
        self.category_box["values"] = list(self.category_map)
        if selected_id:
            for text, (cid, _fixed) in self.category_map.items():
                if cid == selected_id:
                    self.category_var.set(text); return
        if self.category_map:
            self.category_var.set(next(iter(self.category_map)))
            data = self.category_map.get(self.category_var.get())
            if data and data[1]: self.routine_var.set(True)

    def apply_learning(self):
        defaults = self.db.learned_defaults(self.label_var.get().strip())
        if not defaults: return
        self.kind_var.set(KIND_LABELS[defaults["kind"]]); self.refresh_categories(defaults["category_id"])
        self.routine_var.set(bool(defaults["routine"]))
        if defaults["project_id"]:
            for name, pid in self.projects.items():
                if pid == defaults["project_id"]: self.project_var.set(name); break
        self.hint_var.set(f"ANTs reconnaît ce libellé · moyenne {defaults['avg_amount']:.2f} €")

    def load(self, tx_id):
        r = self.db.get_transaction(tx_id)
        if not r: return
        self.kind_var.set(KIND_LABELS.get(r["kind"], "Dépense")); self.status_var.set(STATUS_LABELS.get(r["status"], "Confirmée"))
        self.date_var.set(r["transaction_date"]); self.date_known_var.set(bool(r["date_known"])); self.label_var.set(r["label"])
        self.amount_var.set(str(r["amount"]).replace(".", ",")); self.routine_var.set(bool(r["routine"])); self.comment_var.set(r["comment"] or "")
        self.refresh_categories(r["category_id"])
        if r["project_id"]:
            for name, pid in self.projects.items():
                if pid == r["project_id"]: self.project_var.set(name); break

    def save(self):
        try:
            datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d")
            amount = float(self.amount_var.get().replace(",", "."))
            if amount < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Saisie incorrecte", "Vérifie la date et le montant.", parent=self); return
        label = self.label_var.get().strip()
        if not label:
            messagebox.showerror("Libellé manquant", "Renseigne un libellé.", parent=self); return
        selected = self.category_map.get(self.category_var.get()); category_id = selected[0] if selected else None
        self.db.save_transaction(
            self.tx_id, self.date_var.get().strip(), LABEL_KINDS[self.kind_var.get()], amount, category_id, label,
            int(self.routine_var.get()), LABEL_STATUSES[self.status_var.get()], int(self.date_known_var.get()),
            self.projects.get(self.project_var.get()), self.comment_var.get().strip(),
        )
        self.destroy(); self.master.refresh_all()


class ProjectDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, project=None):
        super().__init__(parent); self.db, self.project = db, project
        self.title("Modifier le projet" if project else "Nouveau projet"); self.resizable(False, False); self.transient(parent); self.grab_set()
        self.vars = {
            "name": tk.StringVar(value=project["name"] if project else ""),
            "target": tk.StringVar(value=str(project["target_amount"]).replace(".", ",") if project else ""),
            "date": tk.StringVar(value=project["target_date"] if project else ""),
            "saved": tk.StringVar(value=str(project["saved_amount"]).replace(".", ",") if project else "0"),
            "status": tk.StringVar(value=project["status"] if project else "En préparation"),
        }
        f = ttk.Frame(self, padding=18); f.pack()
        fields = (("Nom", "name"), ("Objectif (€)", "target"), ("Date cible", "date"), ("Déjà épargné (€)", "saved"), ("Statut", "status"))
        for i, (lab, key) in enumerate(fields):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 12))
            if key == "status": ttk.Combobox(f, textvariable=self.vars[key], values=("En préparation", "En cours", "En pause", "Réalisé"), state="readonly", width=32).grid(row=i, column=1, pady=5)
            else: ttk.Entry(f, textvariable=self.vars[key], width=35).grid(row=i, column=1, pady=5)
        ttk.Label(f, text="Date au format AAAA-MM-JJ").grid(row=5, column=1, sticky="w")
        ttk.Button(f, text="Enregistrer", command=self.save).grid(row=6, column=1, sticky="e", pady=(12, 0))

    def save(self):
        try:
            target = float(self.vars["target"].get().replace(",", ".")); saved = float(self.vars["saved"].get().replace(",", "."))
            datetime.strptime(self.vars["date"].get().strip(), "%Y-%m-%d"); assert target >= 0 and saved >= 0
        except Exception:
            messagebox.showerror("Erreur", "Vérifie les montants et la date.", parent=self); return
        if not self.vars["name"].get().strip():
            messagebox.showerror("Erreur", "Renseigne un nom de projet.", parent=self); return
        self.db.save_project(self.project["id"] if self.project else None, self.vars["name"].get().strip(), target, self.vars["date"].get().strip(), saved, self.vars["status"].get())
        self.destroy(); self.master.refresh_all()


class ANTsApp(tk.Tk):
    def __init__(self):
        super().__init__(); self.db = Database(app_db_path())
        today = date.today(); self.year, self.month = today.year, today.month
        self.title(f"ANTs — v{APP_VERSION}"); self.geometry("1280x790"); self.minsize(1060, 680)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.setup_style(); self.make_ui(); self.refresh_all()

    def setup_style(self):
        s = ttk.Style(self)
        try: s.theme_use("vista")
        except tk.TclError: pass
        s.configure("Card.TLabelframe", padding=10)
        s.configure("Treeview", rowheight=29, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def make_ui(self):
        root = ttk.Frame(self, padding=14); root.pack(fill="both", expand=True)
        top = ttk.Frame(root); top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="🐜", font=("Segoe UI Emoji", 24)).pack(side="left", padx=(0, 6))
        ttk.Label(top, text="ANTs", font=("Segoe UI", 23, "bold")).pack(side="left")
        ttk.Label(top, text="  compagnon financier personnel", font=("Segoe UI", 11)).pack(side="left", pady=(9, 0))
        ttk.Button(top, text="＋ Nouvelle écriture", command=self.add_transaction).pack(side="right")
        self.tabs = ttk.Notebook(root); self.tabs.pack(fill="both", expand=True)
        self.dashboard_tab = ttk.Frame(self.tabs, padding=14); self.journal_tab = ttk.Frame(self.tabs, padding=14)
        self.projects_tab = ttk.Frame(self.tabs, padding=14); self.savings_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.dashboard_tab, text="  Tableau de bord  "); self.tabs.add(self.journal_tab, text="  Journal  ")
        self.tabs.add(self.projects_tab, text="  Projets  "); self.tabs.add(self.savings_tab, text="  Épargne  ")
        self.make_dashboard(); self.make_journal(); self.make_projects(); self.make_savings()

    def month_nav(self, parent, with_import=False):
        nav = ttk.Frame(parent); nav.pack(fill="x", pady=(0, 12))
        ttk.Button(nav, text="◀", width=4, command=lambda: self.shift_month(-1)).pack(side="left")
        label = ttk.Label(nav, font=("Segoe UI", 16, "bold"), anchor="center"); label.pack(side="left", fill="x", expand=True)
        if with_import:
            self.import_button = ttk.Button(nav, text="Importer les écritures habituelles", command=self.import_recurring)
            self.import_button.pack(side="right", padx=(8, 0))
        ttk.Button(nav, text="▶", width=4, command=lambda: self.shift_month(1)).pack(side="right")
        return label

    def make_dashboard(self):
        self.dashboard_month_label = self.month_nav(self.dashboard_tab)
        self.card_vars = {k: tk.StringVar() for k in ("income", "expense", "recurring", "movement", "balance", "savings")}
        cards = ttk.Frame(self.dashboard_tab); cards.pack(fill="x")
        specs = [("🟢 Revenus", "income"), ("🔴 Dépenses", "expense"), ("🔁 Habituelles", "recurring"), ("🔵 Mouvements", "movement"), ("Solde du mois", "balance"), ("Épargne", "savings")]
        for i, (title, key) in enumerate(specs):
            c = ttk.LabelFrame(cards, text=title, style="Card.TLabelframe"); c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0)); cards.columnconfigure(i, weight=1)
            ttk.Label(c, textvariable=self.card_vars[key], font=("Segoe UI", 13, "bold")).pack()
        lower = ttk.Frame(self.dashboard_tab); lower.pack(fill="both", expand=True, pady=(14, 0))
        left = ttk.LabelFrame(lower, text="Dépenses par poste", padding=10); left.pack(side="left", fill="both", expand=True, padx=(0, 7))
        right = ttk.LabelFrame(lower, text="Observations des fourmis", padding=10); right.pack(side="left", fill="both", expand=True, padx=(7, 0))
        self.category_tree = ttk.Treeview(left, columns=("category", "amount"), show="headings", height=12)
        self.category_tree.heading("category", text="Poste"); self.category_tree.heading("amount", text="Montant")
        self.category_tree.column("category", width=360); self.category_tree.column("amount", width=130, anchor="e"); self.category_tree.pack(fill="both", expand=True)
        self.coach_text = tk.Text(right, wrap="word", height=12, relief="flat", background="#f7f8fa", font=("Segoe UI", 10))
        self.coach_text.pack(fill="both", expand=True); self.coach_text.configure(state="disabled")

    def make_journal(self):
        self.journal_month_label = self.month_nav(self.journal_tab, with_import=True)
        columns = ("date", "status", "icon", "label", "category", "nature", "project", "amount")
        self.tree = ttk.Treeview(self.journal_tab, columns=columns, show="headings", selectmode="browse")
        heads = {"date": "Date", "status": "Statut", "icon": "", "label": "Libellé", "category": "Poste", "nature": "Nature", "project": "Projet", "amount": "Montant"}
        widths = {"date": 100, "status": 110, "icon": 45, "label": 235, "category": 270, "nature": 110, "project": 150, "amount": 125}
        for c in columns:
            self.tree.heading(c, text=heads[c]); self.tree.column(c, width=widths[c], anchor="e" if c == "amount" else "center" if c in ("date", "status", "icon", "nature") else "w")
        self.tree.pack(fill="both", expand=True); self.tree.bind("<Double-1>", lambda _e: self.edit_transaction())
        self.tree.tag_configure("income", foreground="#137333"); self.tree.tag_configure("expense", foreground="#b3261e")
        self.tree.tag_configure("movement", foreground="#1a73e8"); self.tree.tag_configure("planned", background="#fff6d8")
        bar = ttk.Frame(self.journal_tab); bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Supprimer", command=self.delete_transaction).pack(side="right")
        ttk.Button(bar, text="Modifier", command=self.edit_transaction).pack(side="right", padx=8)
        ttk.Button(bar, text="＋ Nouvelle écriture", command=self.add_transaction).pack(side="right")

    def make_projects(self):
        top = ttk.Frame(self.projects_tab); top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Projets futurs", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top, text="＋ Nouveau projet", command=lambda: ProjectDialog(self, self.db)).pack(side="right")
        cols = ("name", "target", "saved", "spent", "remaining", "date", "monthly", "status")
        self.project_tree = ttk.Treeview(self.projects_tab, columns=cols, show="headings", selectmode="browse")
        heads = {"name": "Projet", "target": "Objectif", "saved": "Déjà épargné", "spent": "Dépenses liées", "remaining": "Reste", "date": "Date cible", "monthly": "Effort mensuel", "status": "Statut"}
        for c in cols:
            self.project_tree.heading(c, text=heads[c]); self.project_tree.column(c, width=145 if c == "name" else 115, anchor="e" if c in ("target", "saved", "spent", "remaining", "monthly") else "center")
        self.project_tree.pack(fill="both", expand=True); self.project_tree.bind("<Double-1>", lambda _e: self.edit_project())
        bar = ttk.Frame(self.projects_tab); bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Supprimer", command=self.delete_project).pack(side="right"); ttk.Button(bar, text="Modifier", command=self.edit_project).pack(side="right", padx=8)

    def make_savings(self):
        top = ttk.Frame(self.savings_tab); top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Comptes d'épargne", font=("Segoe UI", 16, "bold")).pack(side="left"); ttk.Button(top, text="＋ Ajouter", command=self.add_saving).pack(side="right")
        self.savings_tree = ttk.Treeview(self.savings_tab, columns=("name", "balance", "updated"), show="headings")
        self.savings_tree.heading("name", text="Compte"); self.savings_tree.heading("balance", text="Solde"); self.savings_tree.heading("updated", text="Mise à jour")
        self.savings_tree.column("name", width=360); self.savings_tree.column("balance", width=180, anchor="e"); self.savings_tree.column("updated", width=180, anchor="center"); self.savings_tree.pack(fill="both", expand=True)
        bar = ttk.Frame(self.savings_tab); bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Supprimer", command=self.delete_saving).pack(side="right"); ttk.Button(bar, text="Modifier le solde", command=self.edit_saving).pack(side="right", padx=8)

    def shift_month(self, delta):
        idx = self.year * 12 + self.month - 1 + delta; self.year, m = divmod(idx, 12); self.month = m + 1; self.refresh_all()

    def import_recurring(self):
        if (self.year, self.month) <= (date.today().year, date.today().month):
            if not messagebox.askyesno("Importer", "Ce mois n'est pas futur. Importer quand même les écritures habituelles manquantes ?", parent=self): return
        count = self.db.import_recurring(self.year, self.month)
        messagebox.showinfo("Budget prévisionnel", f"{count} écriture(s) habituelle(s) ajoutée(s) comme prévisionnelles.", parent=self); self.refresh_all()

    def add_transaction(self): TransactionDialog(self, self.db, self.year, self.month)
    def selected_id(self):
        s = self.tree.selection(); return int(s[0]) if s else None
    def edit_transaction(self):
        tx = self.selected_id()
        if tx: TransactionDialog(self, self.db, self.year, self.month, tx)
    def delete_transaction(self):
        tx = self.selected_id()
        if tx and messagebox.askyesno("Confirmer", "Supprimer cette écriture ?", parent=self): self.db.delete_transaction(tx); self.refresh_all()

    def selected_project(self):
        s = self.project_tree.selection()
        if not s: return None
        pid = int(s[0]); return next((r for r in self.db.projects() if r["id"] == pid), None)
    def edit_project(self):
        p = self.selected_project()
        if p: ProjectDialog(self, self.db, p)
    def delete_project(self):
        p = self.selected_project()
        if p and messagebox.askyesno("Confirmer", "Supprimer ce projet ? Les écritures resteront conservées.", parent=self): self.db.delete_project(p["id"]); self.refresh_all()

    def saving_prompt(self, title, name="", balance=""):
        w = tk.Toplevel(self); w.title(title); w.transient(self); w.grab_set(); w.resizable(False, False)
        nv, bv = tk.StringVar(value=name), tk.StringVar(value=balance); f = ttk.Frame(w, padding=16); f.pack()
        ttk.Label(f, text="Nom").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10)); ttk.Entry(f, textvariable=nv, width=30).grid(row=0, column=1, pady=5)
        ttk.Label(f, text="Solde (€)").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 10)); ttk.Entry(f, textvariable=bv, width=30).grid(row=1, column=1, pady=5)
        result = {}
        def ok():
            try: val = float(bv.get().replace(",", ".")); assert val >= 0
            except Exception: messagebox.showerror("Erreur", "Montant incorrect", parent=w); return
            if not nv.get().strip(): return
            result.update(name=nv.get().strip(), balance=val); w.destroy()
        ttk.Button(f, text="Valider", command=ok).grid(row=2, column=1, sticky="e", pady=(10, 0)); self.wait_window(w); return result or None

    def add_saving(self):
        r = self.saving_prompt("Ajouter un compte")
        if r:
            try: self.db.add_saving(r["name"], r["balance"])
            except sqlite3.IntegrityError: messagebox.showerror("Erreur", "Ce compte existe déjà", parent=self)
            self.refresh_all()
    def selected_saving(self):
        s = self.savings_tree.selection(); return int(s[0]) if s else None
    def edit_saving(self):
        sid = self.selected_saving()
        if not sid: return
        row = next((r for r in self.db.savings() if r["id"] == sid), None)
        if not row: return
        r = self.saving_prompt("Modifier le solde", row["name"], str(row["balance"]).replace(".", ","))
        if r: self.db.update_saving(sid, r["balance"]); self.refresh_all()
    def delete_saving(self):
        sid = self.selected_saving()
        if sid and messagebox.askyesno("Confirmer", "Supprimer ce compte d'épargne ?", parent=self): self.db.delete_saving(sid); self.refresh_all()

    def observations(self, rows, totals, recurring_total, by_category):
        obs = []
        confirmed = [r for r in rows if r["status"] == "confirmed"]; planned = [r for r in rows if r["status"] == "planned"]
        if not rows: return ["Aucune écriture enregistrée pour ce mois."]
        if planned:
            obs.append(f"Le budget contient {len(planned)} prévision(s) et {len(confirmed)} écriture(s) confirmée(s).")
        else:
            obs.append(f"Ce mois comporte {len(rows)} écriture(s) confirmée(s).")
        if totals["expense"]:
            pct = recurring_total / totals["expense"] * 100
            obs.append(f"Les écritures habituelles représentent {recurring_total:.2f} €, soit {pct:.0f} % des dépenses du mois.")
        if by_category:
            ranked = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
            top_cat, top_amt = ranked[0]; obs.append(f"Le premier poste de dépense est {top_cat} avec {top_amt:.2f} €.")
            if len(ranked) > 1: obs.append(f"Les deux premiers postes concentrent {(ranked[0][1]+ranked[1][1])/totals['expense']*100:.0f} % des dépenses.")
        prev_rows = self.db.previous_month_rows(self.year, self.month)
        prev_expense = sum(float(r["amount"]) for r in prev_rows if r["kind"] == "expense")
        if prev_expense and totals["expense"]:
            diff = totals["expense"] - prev_expense; direction = "plus" if diff > 0 else "moins"
            obs.append(f"Par rapport au mois précédent, les dépenses sont {abs(diff):.2f} € {direction} élevées.")
        cash = sum(float(r["amount"]) for r in rows if r["kind"] == "movement" and (r["category"] or "") == "Retrait d'espèces")
        if cash: obs.append(f"Le besoin d'espèces enregistré ce mois-ci est de {cash:.2f} €.")
        balance = totals["income"] - totals["expense"]
        if planned: obs.append(f"À ce stade, le solde prévisionnel du mois est de {balance:.2f} €.")
        active_projects = [p for p in self.db.projects() if p["status"] in ("En préparation", "En cours")]
        if active_projects:
            closest = min(active_projects, key=lambda p: p["target_date"])
            remain = max(0.0, float(closest["target_amount"]) - float(closest["saved_amount"]))
            obs.append(f"Projet le plus proche : {closest['name']} · encore {remain:.2f} € à constituer avant le {closest['target_date']}.")
        return obs

    def refresh_all(self):
        month_text = f"{MONTHS[self.month - 1].capitalize()} {self.year}"
        self.dashboard_month_label.config(text=month_text); self.journal_month_label.config(text=month_text)
        rows = self.db.month_transactions(self.year, self.month)
        totals = defaultdict(float); by_category = defaultdict(float); recurring_total = 0.0
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            amount = float(r["amount"]); totals[r["kind"]] += amount
            if r["kind"] == "expense":
                by_category[f"{r['icon'] or '•'}  {r['parent'] or ''} › {r['category'] or 'Sans poste'}"] += amount
                if r["routine"] or r["default_fixed"]: recurring_total += amount
            sign = "+" if r["kind"] == "income" else "−" if r["kind"] == "expense" else "↔"
            category = " › ".join(x for x in (r["parent"], r["category"]) if x)
            nature = "🔁 Habituelle" if r["routine"] else "Ponctuelle"
            tx_date = datetime.strptime(r["transaction_date"], "%Y-%m-%d").strftime("%d/%m/%Y") if r["date_known"] else "À préciser"
            tags = (r["kind"], r["status"])
            self.tree.insert("", "end", iid=str(r["id"]), tags=tags, values=(
                tx_date, STATUS_LABELS.get(r["status"], "Confirmée"), r["icon"] or "•", r["label"], category, nature, r["project_name"] or "—", f"{sign} {amount:.2f} €"
            ))
        savings_total = sum(float(r["balance"]) for r in self.db.savings()); balance = totals["income"] - totals["expense"]
        self.card_vars["income"].set(f"{totals['income']:.2f} €"); self.card_vars["expense"].set(f"{totals['expense']:.2f} €")
        self.card_vars["recurring"].set(f"{recurring_total:.2f} €"); self.card_vars["movement"].set(f"{totals['movement']:.2f} €")
        self.card_vars["balance"].set(f"{balance:.2f} €"); self.card_vars["savings"].set(f"{savings_total:.2f} €")
        self.category_tree.delete(*self.category_tree.get_children())
        for category, amount in sorted(by_category.items(), key=lambda x: x[1], reverse=True): self.category_tree.insert("", "end", values=(category, f"{amount:.2f} €"))
        obs = self.observations(rows, totals, recurring_total, by_category)
        self.coach_text.configure(state="normal"); self.coach_text.delete("1.0", "end"); self.coach_text.insert("1.0", "\n\n".join(obs)); self.coach_text.configure(state="disabled")

        project_spend = defaultdict(float)
        for r in self.db.conn.execute("SELECT project_id,SUM(amount) total FROM transactions WHERE project_id IS NOT NULL AND kind='expense' GROUP BY project_id"):
            project_spend[r["project_id"]] = float(r["total"] or 0)
        self.project_tree.delete(*self.project_tree.get_children()); today = date.today()
        for p in self.db.projects():
            target = float(p["target_amount"]); saved = float(p["saved_amount"]); spent = project_spend[p["id"]]; remaining = max(0.0, target - saved - spent)
            try:
                td = datetime.strptime(p["target_date"], "%Y-%m-%d").date(); months = max(1, (td.year - today.year) * 12 + td.month - today.month); monthly = remaining / months
            except ValueError: monthly = 0
            self.project_tree.insert("", "end", iid=str(p["id"]), values=(p["name"], f"{target:.2f} €", f"{saved:.2f} €", f"{spent:.2f} €", f"{remaining:.2f} €", p["target_date"], f"{monthly:.2f} €", p["status"]))
        self.savings_tree.delete(*self.savings_tree.get_children())
        for s in self.db.savings(): self.savings_tree.insert("", "end", iid=str(s["id"]), values=(s["name"], f"{float(s['balance']):.2f} €", str(s["updated_at"])[:10]))

    def on_close(self): self.db.close(); self.destroy()


def main():
    app = ANTsApp(); app.mainloop()


if __name__ == "__main__":
    main()
