
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from statistics import median

app = Flask(__name__)
DB_PATH = os.path.join(app.root_path, "expenses.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                merchant TEXT NOT NULL,
                date TEXT NOT NULL
            )
        """)


def analyze_transactions(transactions):
    results = []
    amounts_by_category = {}

    for tx in transactions:
        amounts_by_category.setdefault(tx["category"], []).append(
            tx["amount"]
        )

    for tx in transactions:
        history = [
            amount for amount in amounts_by_category[tx["category"]]
            if amount != tx["amount"]
        ]

        # Compare with other transactions in the same category.
        # For identical amounts, this simple baseline is inconclusive.
        if len(history) >= 3:
            typical = median(history)
            unusual = tx["amount"] > max(typical * 2.5, typical + 500)
        else:
            typical = None
            unusual = False

        results.append({
            "id": tx["id"],
            "amount": tx["amount"],
            "category": tx["category"],
            "merchant": tx["merchant"],
            "date": tx["date"],
            "unusual": unusual,
            "typical": typical,
            "reason": (
                f"Amount is substantially above the category median "
                f"of ₹{typical:.2f}."
                if unusual else "No anomaly detected by the current baseline."
            )
        })

    return results


@app.route("/")
def index():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY date DESC, id DESC"
        ).fetchall()

    transactions = analyze_transactions(rows)
    total = sum(tx["amount"] for tx in transactions)
    alerts = sum(tx["unusual"] for tx in transactions)

    return render_template(
        "index.html",
        transactions=transactions,
        total=total,
        alerts=alerts
    )


@app.route("/add", methods=["POST"])
def add_transaction():
    amount = float(request.form["amount"])
    category = request.form["category"].strip()
    merchant = request.form["merchant"].strip()
    date = request.form["date"]

    if amount <= 0 or not category or not merchant or not date:
        return "Please enter valid transaction details.", 400

    with get_db() as conn:
        conn.execute(
            """INSERT INTO transactions
               (amount, category, merchant, date)
               VALUES (?, ?, ?, ?)""",
            (amount, category, merchant, date)
        )

    return redirect(url_for("index"))


@app.route("/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM transactions WHERE id = ?",
            (transaction_id,)
        )

    return redirect(url_for("index"))


if __name__ == "__main__":
    initialize_db()
    app.run(debug=True)