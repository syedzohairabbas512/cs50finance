import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed coy
# okies)
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

    cash = (db.execute("SELECT cash FROM users WHERE id = ?",
            session["user_id"])[0]["cash"])
    print(cash)
    stocks = db.execute(
        "SELECT * FROM purchases WHERE username = ?", session["user_id"])

    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["name"] = quote["name"]
        stock["symbol"] = quote["symbol"]
        stock["price"] = quote["price"]
        # Add a new key to store total price
        stock["total_price"] = (stock["price"] * stock["shares"])

    return render_template("index.html", stocks=stocks, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        if not symbol or not shares:
            return apology("Please enter the symbol and number of shares")
        # if not shares > 0:
        #     return apology("Please enter the positive number of shares")
        price = lookup(symbol)["price"]
        print(price)
        cash = (db.execute("SELECT cash FROM users WHERE id = ?",
                session["user_id"])[0]["cash"])
        print(cash)
        total_cost = (price) * (shares)
        print(total_cost)
        if total_cost > cash:
            return apology("Not enough cash", 400)
        cash = cash - total_cost
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
                   cash, session["user_id"])
        db.execute(
            "INSERT INTO purchases(username, symbol, shares, price) VALUES (?, ?, ?, ?)",
            session["user_id"],
            symbol,
            shares,
            total_cost,
        )
        quote = lookup(symbol)

        # Record the sale in the history table
        db.execute("INSERT INTO history (userid, symbol, shares, method, price) VALUES (:userid, :symbol, :shares, 'Buy', :price)",
                   userid=session["user_id"], symbol=symbol, shares=shares, price=quote['price'])
        flash(
            f"Successfully Bought {shares} of {symbol} at {usd(total_cost)}!")
        return redirect("/")
    return render_template("buy.html")


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
            "SELECT * FROM users WHERE username = ?", request.form.get(
                "username")
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
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("Invalid Symbol", 400)
        return render_template("quoted.html", quote=quote)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")
        if not username:
            return apology("Pleas1e provide the username")
        if not password:
            return apology("Please enter the password")
        if not confirm_password:
            return apology("Please confirm password")
        if password != confirm_password:
            return apology("Passwords do not match")
        # ensuring that the username does not exit already
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) != 0:
            return apology("Username already exists", 400)
        # hashing the user password
        hashed_value = generate_password_hash(password)
        checking_password = check_password_hash(hashed_value, password)
        storing_info = db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)", username, hashed_value
        )

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = rows[0]["id"]
        # Remember which user has logged in
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        # Get the user's current stocks
        symbols = db.execute("SELECT DISTINCT symbol FROM purchases WHERE username = :username",
                             username=session["user_id"])

        # Render the sell.html form, passing in current stocks
        return render_template("sell.html", symbols=symbols)

    if request.method == "POST":
        # Get data from the form
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Check if the symbol is valid and if the user owns shares of that stock
        rows = db.execute("SELECT SUM(shares) as total_shares FROM purchases WHERE username = :username AND symbol = :symbol GROUP BY symbol",
                          username=session["user_id"], symbol=symbol)

        if len(rows) != 1 or rows[0]["total_shares"] is None:
            return apology("Invalid stock symbol or you don't own any shares of this stock", 403)

        total_shares_owned = rows[0]["total_shares"]

        if shares <= 0 or shares > total_shares_owned:
            return apology("Invalid number of shares to sell", 403)

        # Get the current price of the stock
        quote = lookup(symbol)

        if quote is None:
            return apology("Unable to fetch stock quote", 403)

        # Calculate the sale value
        sale_value = quote['price'] * shares

        # Update user's cash balance
        user = db.execute(
            "SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]
        current_cash = user["cash"]
        new_cash = current_cash + sale_value

        db.execute("UPDATE users SET cash = :new_cash WHERE id = :id",
                   new_cash=new_cash, id=session["user_id"])

        # Update the purchases table
        if shares == total_shares_owned:
            # If all shares are sold, delete the row
            db.execute("DELETE FROM purchases WHERE username = :username AND symbol = :symbol",
                       username=session["user_id"], symbol=symbol)
        else:
            # If some shares remain, update the row
            db.execute("UPDATE purchases SET shares = shares - :shares WHERE username = :username AND symbol = :symbol",
                       shares=shares, username=session["user_id"], symbol=symbol)

        # Record the sale in the history table
        db.execute("INSERT INTO history (userid, symbol, shares, method, price) VALUES (:userid, :symbol, :shares, 'Sell', :price)",
                   userid=session["user_id"], symbol=symbol, shares=shares, price=quote['price'])
        flash(
            f"Successfully sold {shares} of {symbol}!")
        # Redirect to the index page
        return redirect("/")


@app.route("/history")
@login_required
def history():
    history = db.execute(
        "SELECT * FROM history WHERE userid = ?", session['user_id'])
    return render_template('history.html', history=history)
