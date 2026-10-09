from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date
from statistics import median
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-deployment")

DB_PATH = os.path.join(app.root_path, "expenses.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                merchant TEXT NOT NULL,
                date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                target REAL NOT NULL,
                saved REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("home"))

        flash("Incorrect email or password.", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get(
            "username", request.form.get("name", "")
        ).strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", password)

        if not username or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("register.html")

        if password != confirm:
            flash("The passwords do not match.", "error")
            return render_template("register.html")

        try:
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO users (username, email, password_hash)
                       VALUES (?, ?, ?)""",
                    (username, email, generate_password_hash(password))
                )
            flash("Account created! Please sign in.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "error")

    return render_template("register.html")


@app.route("/home")
@login_required
def home():
    user_id = session["user_id"]

    with get_db() as conn:
        transactions = conn.execute(
            "SELECT * FROM transactions WHERE user_id = ?",
            (user_id,)
        ).fetchall()

        goals = conn.execute(
            "SELECT * FROM savings_goals WHERE user_id = ?",
            (user_id,)
        ).fetchall()

    total = sum(row["amount"] for row in transactions)
    today = date.today().isoformat()
    this_month = today[:7]

    monthly_total = sum(
        row["amount"] for row in transactions
        if row["date"].startswith(this_month)
    )

    return render_template(
        "home.html",
        username=session.get("username", "there"),
        transaction_count=len(transactions),
        total=total,
        monthly_total=monthly_total,
        goal_count=len(goals)
    )


@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    user_id = session["user_id"]

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0"))
            category = request.form.get("category", "").strip()
            custom_category = request.form.get(
                "custom_category", ""
            ).strip()
            merchant = request.form.get("merchant", "").strip()
            transaction_date = request.form.get("date", "")

            if category == "Custom":
                category = custom_category

            if (
                amount <= 0 or not category or not merchant
                or not transaction_date
            ):
                raise ValueError

            with get_db() as conn:
                conn.execute(
                    """INSERT INTO transactions
                       (user_id, amount, category, merchant, date)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, amount, category, merchant, transaction_date)
                )

            flash("Transaction added successfully!", "success")
            return redirect(url_for("transactions"))

        except (ValueError, TypeError):
            flash("Please enter valid transaction details.", "error")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM transactions
               WHERE user_id = ?
               ORDER BY date DESC, id DESC""",
            (user_id,)
        ).fetchall()

    return render_template(
        "transactions.html",
        transactions=rows,
        today=date.today().isoformat()
    )


@app.route("/history")
@login_required
def history():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM transactions
               WHERE user_id = ?
               ORDER BY date DESC, id DESC""",
            (session["user_id"],)
        ).fetchall()

    return render_template("history.html", transactions=rows)


@app.route("/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, session["user_id"])
        )

    flash("Transaction deleted.", "success")
    return redirect(request.referrer or url_for("history"))


@app.route("/growth")
@login_required
def growth():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE user_id = ?",
            (session["user_id"],)
        ).fetchall()

    total = sum(row["amount"] for row in rows)
    categories = {}

    for row in rows:
        categories[row["category"]] = (
            categories.get(row["category"], 0) + row["amount"]
        )

    top_category = (
        max(categories, key=categories.get) if categories else "Not enough data"
    )

    return render_template(
        "growth.html",
        total=total,
        count=len(rows),
        top_category=top_category,
        categories=categories
    )


@app.route("/savings", methods=["GET", "POST"])
@login_required
def savings():
    user_id = session["user_id"]

    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            target = float(request.form.get("target", "0"))
            saved = float(request.form.get("saved", "0"))

            if not title or target <= 0 or saved < 0 or saved > target:
                raise ValueError

            with get_db() as conn:
                conn.execute(
                    """INSERT INTO savings_goals
                       (user_id, title, target, saved)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, title, target, saved)
                )

            flash("Savings goal created!", "success")
            return redirect(url_for("savings"))

        except (ValueError, TypeError):
            flash("Please enter a valid goal and amount.", "error")

    with get_db() as conn:
        goals = conn.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ).fetchall()

    return render_template("savings.html", goals=goals)


@app.route("/anomalies")
@login_required
def anomalies():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM transactions
               WHERE user_id = ? ORDER BY date DESC""",
            (session["user_id"],)
        ).fetchall()

    amounts = {}
    for row in rows:
        amounts.setdefault(row["category"], []).append(row["amount"])

    alerts = []

    for row in rows:
        history = amounts[row["category"]]
        if len(history) >= 4:
            typical = median(history)
            if row["amount"] > max(typical * 2.5, typical + 500):
                alerts.append({
                    "date": row["date"],
                    "merchant": row["merchant"],
                    "category": row["category"],
                    "amount": row["amount"],
                    "typical": typical
                })

    return render_template("anomalies.html", alerts=alerts)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    initialize_db()
    app.run(debug=True)

