from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash

from app.db import mysql


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth"
)


@auth_bp.route("/login")
def login():
    return render_template("login.html")


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    message = ""

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:

            message = "Username and password are required."

        else:

            cursor = None

            try:

                cursor = mysql.connection.cursor()

                cursor.execute(
                    """
                    SELECT
                        admin_id,
                        admin_code,
                        username,
                        password_hash,
                        full_name,
                        status
                    FROM admin_accounts
                    WHERE username = %s
                    LIMIT 1
                    """,
                    (username,)
                )

                admin = cursor.fetchone()

                if not admin:

                    message = "Invalid username or password."

                elif admin["status"] != "ACTIVE":

                    message = "This Admin account is not active."

                elif not check_password_hash(
                    admin["password_hash"],
                    password
                ):

                    message = "Invalid username or password."

                else:

                    session.clear()

                    session["admin_authenticated"] = True
                    session["admin_id"] = admin["admin_id"]
                    session["admin_code"] = admin["admin_code"]
                    session["admin_username"] = admin["username"]

                    return redirect(
                        url_for("admin.dashboard")
                    )

            except Exception as error:

                message = f"Login failed: {error}"

            finally:

                if cursor:
                    cursor.close()

    return render_template(
        "admin_login.html",
        message=message
    )