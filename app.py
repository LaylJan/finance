import os

from cs50 import SQL
from datetime import datetime, date
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute(
        "SELECT symbol, qty FROM purchase WHERE id = ?", session["user_id"]
    )
    grandTotal = 0
    for row in rows:
        quote = lookup(row["symbol"])
        price = quote["price"]
        total = round(row["qty"] * price, 4)
        row["price"] = price
        row["total"] = total
        grandTotal = grandTotal + total
    balance = round(
        float(
            db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0][
                "cash"
            ]
        ),
        4,
    )
    grandTotal =  grandTotal + balance
    return render_template(
        "index.html", data=rows, balance=balance, grandTotal=round(grandTotal, 4)
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    status = "Buy"
    today = date.today()
    time = datetime.now().time()
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        if request.form.get("shares").isdigit() and quote is not None and int(request.form.get("shares")) >= 0:
            user_cash = db.execute(
                "SELECT cash FROM users WHERE id = ?", session["user_id"]
            )[0]["cash"]
            isAfford = quote["price"] * int(request.form.get("shares")) <= user_cash
            qty = int(request.form.get("shares"))
            amount = quote["price"] * qty
            if not isAfford:
                return apology("INSUFICIENT BALANCE", 400)
            user_cash = user_cash - amount
            db.execute(
                "UPDATE users SET cash = ? WHERE id = ?", user_cash, session["user_id"]
            )
            db.execute(
                "INSERT INTO history (id, symbol, qty, amount, status, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                session["user_id"],
                quote["symbol"],
                qty,
                amount,
                status,
                today,
                time,
            )
            rows = db.execute(
                "SELECT * FROM purchase WHERE id = ? AND symbol = ?",
                session["user_id"],
                quote["symbol"],
            )

            if len(rows) > 0:
                db.execute(
                    "UPDATE purchase SET qty = qty + ? WHERE id = ? AND symbol = ?",
                    qty,
                    session["user_id"],
                    quote["symbol"],
                )
            else:
                db.execute(
                    "INSERT INTO purchase (id, symbol, qty) VALUES (?, ?, ?)",
                    session["user_id"],
                    quote["symbol"],
                    qty,
                )
            return redirect("/")
        else:
            return apology("Invalid symbol or shares", 400)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM history WHERE id = ?", session["user_id"])
    return render_template("history.html", data=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        if quote is not None:
            return render_template("quote.html", quote=quote)
        else:
            return apology("Invalid symbol", 400)
    else:
        # quote has a quote[price], i want it rounded up to 2
        return render_template("quote.html", quote=None)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Password Does not match", 400)
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )
        if len(rows) == 0:
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?)",
                request.form.get("username"),
                generate_password_hash(request.form.get("password")),
            )
            return redirect("/")
        else:
            return apology("Username is already taken")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    status = "Sell"
    today = date.today()
    time = datetime.now().time()
    if request.method == "POST":
        result = db.execute(
            "SELECT qty FROM purchase WHERE id = ? AND symbol = ?",
            session["user_id"],
            request.form.get("symbol").upper(),
        )
        ownedQty = result[0]["qty"]
        symbols = db.execute(
            "SELECT symbol FROM purchase WHERE id = ?", session["user_id"]
        )
        owned = False
        for row in symbols:
            if request.form.get("symbol").upper() == row["symbol"]:
                owned = True
                break
        if not owned:
            return apology("Stock not owned")
        if (
            int(request.form.get("shares")) >= 0
            and int(request.form.get("shares")) <= ownedQty
        ):
            quote = lookup(request.form.get("symbol"))
            user_cash = db.execute(
                "SELECT cash FROM users WHERE id = ?", session["user_id"]
            )[0]["cash"]
            qty = int(request.form.get("shares"))
            print("test ", result[0]["qty"])
            amount = quote["price"] * int(request.form.get("shares"))
            user_cash = user_cash + amount
            db.execute(
                "UPDATE users SET cash = ? WHERE id = ?", user_cash, session["user_id"]
            )
            db.execute(
                "INSERT INTO history (id, symbol, qty, amount, status, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                session["user_id"],
                quote["symbol"],
                qty,
                amount,
                status,
                today,
                time,
            )
            db.execute(
                "UPDATE purchase SET qty = qty - ? WHERE id = ? AND symbol = ?",
                qty,
                session["user_id"],
                quote["symbol"],
            )
            rows = db.execute(
                "SELECT * FROM purchase WHERE id = ? AND symbol = ?",
                session["user_id"],
                quote["symbol"],
            )
            if rows[0]["qty"] == 0:
                print("Running")
                db.execute(
                    "DELETE FROM purchase WHERE id = ? AND symbol = ?",
                    session["user_id"],
                    request.form.get("symbol").upper(),
                )
            return redirect("/")

        else:
            return apology("Please enter a positive number or not enough stock")

    else:
        return render_template("sell.html")
