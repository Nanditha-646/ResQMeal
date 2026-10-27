from functools import wraps
from datetime import datetime, timedelta
import random
import string
import secrets

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import generate_password_hash, check_password_hash

from app.db import mysql


donor_bp = Blueprint("donor", __name__, url_prefix="/donor")


# =========================================================
# DONOR LOGIN CHECK
# =========================================================

def donor_required(view_function):

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not session.get("donor_authenticated"):

            return redirect(
                url_for("donor.login")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


# =========================================================
# DONOR REGISTRATION
# =========================================================

@donor_bp.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "GET":

        return render_template(
            "donor_registration.html"
        )

    business_name = request.form.get(
        "business_name",
        ""
    ).strip()

    business_type = request.form.get(
        "business_type",
        ""
    ).strip()

    owner = request.form.get(
        "owner",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    address = request.form.get(
        "address",
        ""
    ).strip()

    city = request.form.get(
        "city",
        ""
    ).strip()

    state = request.form.get(
        "state",
        ""
    ).strip()

    postal_code = request.form.get(
        "postal_code",
        ""
    ).strip()

    year_established = request.form.get(
        "year_established",
        ""
    ).strip()

    food_service_since_year = request.form.get(
        "food_service_since_year",
        ""
    ).strip()

    event_name = request.form.get(
        "event_name",
        ""
    ).strip()

    event_type = request.form.get(
        "event_type",
        ""
    ).strip()

    event_date = request.form.get(
        "event_date",
        ""
    ).strip()

    if not business_name or not business_type or not owner:

        flash(
            "Please fill in all required business details.",
            "error"
        )

        return redirect(
            url_for("donor.register")
        )

    if not phone or not email:

        flash(
            "Phone number and email are required.",
            "error"
        )

        return redirect(
            url_for("donor.register")
        )

    if not address or not city:

        flash(
            "Address and city are required.",
            "error"
        )

        return redirect(
            url_for("donor.register")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            SELECT donor_application_id
            FROM donor_applications
            WHERE phone = %s
               OR email = %s
            LIMIT 1
            """,
            (
                phone,
                email
            )
        )

        existing = cursor.fetchone()

        if existing:

            flash(
                "An application with this phone number or email already exists.",
                "error"
            )

            return redirect(
                url_for("donor.register")
            )

        # -------------------------------------------------
        # GENERATE APPLICATION CODE
        # -------------------------------------------------

        while True:

            application_code = (
                "APP-"
                + "".join(
                    random.choices(
                        string.ascii_uppercase
                        + string.digits,
                        k=8
                    )
                )
            )

            cursor.execute(
                """
                SELECT donor_application_id
                FROM donor_applications
                WHERE application_code = %s
                LIMIT 1
                """,
                (application_code,)
            )

            if not cursor.fetchone():

                break

        # -------------------------------------------------
        # EVENT / PARTY REGISTRATION
        # -------------------------------------------------

        if business_type == "EVENT_PARTY":

            cursor.execute(
                """
                INSERT INTO donor_applications (
                    application_code,
                    business_name,
                    business_type,
                    owner,
                    phone,
                    email,
                    address,
                    city,
                    state,
                    postal_code,
                    year_established,
                    food_service_since_year,
                    event_name,
                    event_type,
                    event_date,
                    application_status
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    NULL, NULL, %s, %s, %s,
                    'PENDING_MOBILE_VERIFICATION'
                )
                """,
                (
                    application_code,
                    business_name,
                    business_type,
                    owner,
                    phone,
                    email,
                    address,
                    city,
                    state or None,
                    postal_code or None,
                    event_name or None,
                    event_type or None,
                    event_date or None
                )
            )

            application_id = cursor.lastrowid

            otp_code = str(
                random.randint(
                    100000,
                    999999
                )
            )

            expires_at = (
                datetime.now()
                + timedelta(minutes=5)
            )

            cursor.execute(
                """
                INSERT INTO event_otp_verifications (
                    donor_application_id,
                    mobile_number,
                    otp_code,
                    otp_status,
                    attempts,
                    expires_at
                )
                VALUES (
                    %s, %s, %s, 'PENDING', 0, %s
                )
                """,
                (
                    application_id,
                    phone,
                    otp_code,
                    expires_at
                )
            )

            mysql.connection.commit()

            session["event_application_id"] = (
                application_id
            )

            session["event_application_code"] = (
                application_code
            )

            session["event_otp"] = otp_code

            flash(
                "Registration submitted successfully. "
                "OTP generated successfully for testing.",
                "success"
            )

            return redirect(
                url_for(
                    "donor.event_mobile_verification"
                )
            )

        # -------------------------------------------------
        # NORMAL DONOR REGISTRATION
        # -------------------------------------------------

        cursor.execute(
            """
            INSERT INTO donor_applications (
                application_code,
                business_name,
                business_type,
                owner,
                phone,
                email,
                address,
                city,
                state,
                postal_code,
                year_established,
                food_service_since_year,
                event_name,
                event_type,
                event_date,
                application_status
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, NULL, NULL, NULL,
                'PENDING'
            )
            """,
            (
                application_code,
                business_name,
                business_type,
                owner,
                phone,
                email,
                address,
                city,
                state or None,
                postal_code or None,
                int(year_established)
                if year_established.isdigit()
                else None,
                int(food_service_since_year)
                if food_service_since_year.isdigit()
                else None
            )
        )

        mysql.connection.commit()

        flash(
            "Registration submitted successfully. "
            "Your application is now pending Admin verification.",
            "success"
        )

        return redirect(
            url_for("donor.register")
        )

    except Exception as error:

        if mysql.connection:

            mysql.connection.rollback()

        flash(
            f"Unable to submit registration: {error}",
            "error"
        )

        return redirect(
            url_for("donor.register")
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# EVENT / PARTY MOBILE VERIFICATION
# =========================================================

@donor_bp.route(
    "/event-mobile-verification",
    methods=["GET", "POST"]
)
def event_mobile_verification():

    application_id = session.get(
        "event_application_id"
    )

    if not application_id:

        flash(
            "No event verification session was found.",
            "error"
        )

        return redirect(
            url_for("donor.register")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            SELECT
                donor_application_id,
                application_code,
                business_name,
                phone,
                application_status
            FROM donor_applications
            WHERE donor_application_id = %s
            LIMIT 1
            """,
            (application_id,)
        )

        application = cursor.fetchone()

        if not application:

            flash(
                "Application could not be found.",
                "error"
            )

            return redirect(
                url_for("donor.register")
            )

        if request.method == "POST":

            entered_otp = request.form.get(
                "otp",
                ""
            ).strip()

            if not entered_otp:

                flash(
                    "Please enter the OTP.",
                    "error"
                )

                return render_template(
                    "event_mobile_verification.html",
                    application=application
                )

            cursor.execute(
                """
                SELECT
                    otp_verification_id,
                    otp_code,
                    otp_status,
                    expires_at
                FROM event_otp_verifications
                WHERE donor_application_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (application_id,)
            )

            otp_record = cursor.fetchone()

            if not otp_record:

                flash(
                    "OTP record was not found.",
                    "error"
                )

            elif otp_record["otp_status"] != "PENDING":

                flash(
                    "This OTP is no longer active.",
                    "error"
                )

            elif datetime.now() > otp_record["expires_at"]:

                cursor.execute(
                    """
                    UPDATE event_otp_verifications
                    SET otp_status = 'EXPIRED'
                    WHERE otp_verification_id = %s
                    """,
                    (
                        otp_record[
                            "otp_verification_id"
                        ],
                    )
                )

                mysql.connection.commit()

                flash(
                    "OTP has expired. Please submit the registration again.",
                    "error"
                )

            elif entered_otp != otp_record["otp_code"]:

                cursor.execute(
                    """
                    UPDATE event_otp_verifications
                    SET attempts = attempts + 1
                    WHERE otp_verification_id = %s
                    """,
                    (
                        otp_record[
                            "otp_verification_id"
                        ],
                    )
                )

                mysql.connection.commit()

                flash(
                    "Invalid OTP.",
                    "error"
                )

            else:

                cursor.execute(
                    """
                    UPDATE event_otp_verifications
                    SET
                        otp_status = 'VERIFIED',
                        verified_at = NOW()
                    WHERE otp_verification_id = %s
                    """,
                    (
                        otp_record[
                            "otp_verification_id"
                        ],
                    )
                )

                cursor.execute(
                    """
                    UPDATE donor_applications
                    SET application_status = 'PENDING'
                    WHERE donor_application_id = %s
                    """,
                    (application_id,)
                )

                mysql.connection.commit()

                session.pop(
                    "event_application_id",
                    None
                )

                session.pop(
                    "event_application_code",
                    None
                )

                session.pop(
                    "event_otp",
                    None
                )

                flash(
                    "Mobile number verified successfully. "
                    "Your application has been submitted for Admin verification.",
                    "success"
                )

                return redirect(
                    url_for("donor.register")
                )

        return render_template(
            "event_mobile_verification.html",
            application=application
        )

    except Exception as error:

        if mysql.connection:

            mysql.connection.rollback()

        return (
            "Unable to verify mobile number: "
            f"{error}"
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# DONOR ACCOUNT ACTIVATION
# =========================================================

@donor_bp.route(
    "/activate",
    methods=["GET", "POST"]
)
def activate():

    if request.method == "GET":

        return render_template(
            "donor_activation.html"
        )

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    new_password = request.form.get(
        "new_password",
        ""
    )

    confirm_password = request.form.get(
        "confirm_password",
        ""
    )

    if not phone or not new_password or not confirm_password:

        flash(
            "Phone number and both password fields are required.",
            "error"
        )

        return redirect(
            url_for("donor.activate")
        )

    if new_password != confirm_password:

        flash(
            "Passwords do not match.",
            "error"
        )

        return redirect(
            url_for("donor.activate")
        )

    if len(new_password) < 6:

        flash(
            "Password must contain at least 6 characters.",
            "error"
        )

        return redirect(
            url_for("donor.activate")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            SELECT
                da.donor_id,
                da.account_status,
                da.donor_code,
                dapp.donor_application_id,
                dapp.application_status,
                dapp.phone,
                dapp.business_name
            FROM donor_accounts da
            INNER JOIN donor_applications dapp
                ON da.donor_application_id =
                   dapp.donor_application_id
            WHERE dapp.phone = %s
            LIMIT 1
            """,
            (phone,)
        )

        donor = cursor.fetchone()

        if not donor:

            flash(
                "No donor account was found for this mobile number.",
                "error"
            )

            return redirect(
                url_for("donor.activate")
            )

        if donor["application_status"] != "APPROVED":

            flash(
                "Your application has not been approved by Admin yet.",
                "error"
            )

            return redirect(
                url_for("donor.activate")
            )

        if donor["account_status"] == "ACTIVE":

            flash(
                "This donor account is already active. "
                "Please use Donor Login.",
                "error"
            )

            return redirect(
                url_for("donor.login")
            )

        if donor["account_status"] != "PENDING":

            flash(
                "This donor account cannot currently be activated.",
                "error"
            )

            return redirect(
                url_for("donor.activate")
            )

        password_hash = generate_password_hash(
            new_password
        )

        cursor.execute(
            """
            UPDATE donor_accounts
            SET
                password_hash = %s,
                account_status = 'ACTIVE',
                activated_at = NOW()
            WHERE donor_id = %s
            """,
            (
                password_hash,
                donor["donor_id"]
            )
        )

        mysql.connection.commit()

        flash(
            "Donor account activated successfully. "
            "You can now log in using your registered mobile number and password.",
            "success"
        )

        return redirect(
            url_for("donor.login")
        )

    except Exception as error:

        if mysql.connection:

            mysql.connection.rollback()

        flash(
            f"Unable to activate account: {error}",
            "error"
        )

        return redirect(
            url_for("donor.activate")
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# DONOR LOGIN
# =========================================================

@donor_bp.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if session.get("donor_authenticated"):

        return redirect(
            url_for("donor.dashboard")
        )

    message = ""

    if request.method == "POST":

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not phone or not password:

            message = (
                "Mobile number and password are required."
            )

        else:

            cursor = None

            try:

                cursor = mysql.connection.cursor()

                cursor.execute(
                    """
                    SELECT
                        da.donor_id,
                        da.donor_code,
                        da.username,
                        da.password_hash,
                        da.account_status,
                        dapp.business_name,
                        dapp.phone,
                        dapp.application_status
                    FROM donor_accounts da
                    INNER JOIN donor_applications dapp
                        ON da.donor_application_id =
                           dapp.donor_application_id
                    WHERE dapp.phone = %s
                    LIMIT 1
                    """,
                    (phone,)
                )

                donor = cursor.fetchone()

                if not donor:

                    message = (
                        "No donor account was found for this mobile number."
                    )

                elif donor["application_status"] != "APPROVED":

                    message = (
                        "Your donor application has not been approved."
                    )

                elif donor["account_status"] == "PENDING":

                    message = (
                        "Your donor account is pending activation. "
                        "Please activate your account first."
                    )

                elif donor["account_status"] != "ACTIVE":

                    message = (
                        "This donor account is not active."
                    )

                elif not check_password_hash(
                    donor["password_hash"],
                    password
                ):

                    message = (
                        "Invalid mobile number or password."
                    )

                else:

                    session.clear()

                    session["donor_authenticated"] = True

                    session["donor_id"] = (
                        donor["donor_id"]
                    )

                    session["donor_code"] = (
                        donor["donor_code"]
                    )

                    session["donor_username"] = (
                        donor["username"]
                    )

                    session["donor_business_name"] = (
                        donor["business_name"]
                    )

                    cursor.execute(
                        """
                        UPDATE donor_accounts
                        SET last_login_at = NOW()
                        WHERE donor_id = %s
                        """,
                        (
                            donor["donor_id"],
                        )
                    )

                    mysql.connection.commit()

                    return redirect(
                        url_for("donor.dashboard")
                    )

            except Exception as error:

                message = (
                    f"Login failed: {error}"
                )

            finally:

                if cursor:

                    cursor.close()

    return render_template(
        "donor_login.html",
        message=message
    )


# =========================================================
# DECLARE SURPLUS
# =========================================================

@donor_bp.route(
    "/declare-surplus",
    methods=["GET", "POST"]
)
@donor_required
def declare_surplus():

    if request.method == "GET":

        return render_template(
            "declare_surplus.html"
        )

    food_type = request.form.get(
        "food_type",
        ""
    ).strip()

    quantity_value = request.form.get(
        "quantity",
        ""
    ).strip()

    quantity_unit = request.form.get(
        "quantity_unit",
        ""
    ).strip()

    preparation_date = request.form.get(
        "preparation_date",
        ""
    ).strip()

    preparation_time = request.form.get(
        "preparation_time",
        ""
    ).strip()

    served_to_customers = request.form.get(
        "served_to_customers",
        ""
    ).strip()

    handling_information = request.form.get(
        "handling_information",
        ""
    ).strip()

    storage_handling_information = request.form.get(
        "storage_handling_information",
        ""
    ).strip()

    applicable_consumption_date = request.form.get(
        "applicable_consumption_date",
        ""
    ).strip()

    applicable_consumption_time = request.form.get(
        "applicable_consumption_time",
        ""
    ).strip()

    available_from = request.form.get(
        "available_from",
        ""
    ).strip()

    available_until = request.form.get(
        "available_until",
        ""
    ).strip()

    donor_declaration = request.form.get(
        "donor_declaration"
    )

    donor_notes = request.form.get(
        "donor_notes",
        ""
    ).strip()

    # -----------------------------------------------------
    # BASIC VALIDATION
    # -----------------------------------------------------

    if food_type not in (
        "VEGETARIAN",
        "NON_VEGETARIAN"
    ):

        flash(
            "Please select a valid food type.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    if quantity_unit not in (
        "KG",
        "LITRES",
        "PIECES"
    ):

        flash(
            "Please select a valid quantity unit.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    try:

        quantity = float(
            quantity_value
        )

    except (TypeError, ValueError):

        flash(
            "Please enter a valid quantity.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    if quantity <= 0:

        flash(
            "Quantity must be greater than zero.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    if served_to_customers not in (
        "0",
        "1"
    ):

        flash(
            "Please specify whether the food was served to customers.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    if donor_declaration != "1":

        flash(
            "You must confirm the donor declaration before submitting.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    if not preparation_date or not preparation_time:

        flash(
            "Preparation date and preparation time are required.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    if not available_from or not available_until:

        flash(
            "Availability start and end times are required.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    # -----------------------------------------------------
    # VALIDATE DATE / TIME VALUES
    # -----------------------------------------------------

    try:

        datetime.strptime(
            preparation_date,
            "%Y-%m-%d"
        )

        datetime.strptime(
            preparation_time,
            "%H:%M"
        )

        available_from_dt = datetime.strptime(
            available_from,
            "%Y-%m-%dT%H:%M"
        )

        available_until_dt = datetime.strptime(
            available_until,
            "%Y-%m-%dT%H:%M"
        )

        if available_until_dt <= available_from_dt:

            flash(
                "Available-until time must be later than available-from time.",
                "error"
            )

            return redirect(
                url_for("donor.declare_surplus")
            )

        if (
            applicable_consumption_date
            and applicable_consumption_time
        ):

            datetime.strptime(
                applicable_consumption_date,
                "%Y-%m-%d"
            )

            datetime.strptime(
                applicable_consumption_time,
                "%H:%M"
            )

        elif (
            applicable_consumption_date
            or applicable_consumption_time
        ):

            flash(
                "Please provide both applicable consumption date and time.",
                "error"
            )

            return redirect(
                url_for("donor.declare_surplus")
            )

    except ValueError:

        flash(
            "Please enter valid date and time values.",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    # -----------------------------------------------------
    # CREATE RECOVERY ID AND SAVE SUBMISSION
    # -----------------------------------------------------

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        recovery_id = None

        for _ in range(20):

            candidate = (
                "REC-"
                + secrets.token_hex(5).upper()
            )

            cursor.execute(
                """
                SELECT food_submission_id
                FROM food_submissions
                WHERE recovery_id = %s
                LIMIT 1
                """,
                (candidate,)
            )

            if not cursor.fetchone():

                recovery_id = candidate

                break

        if not recovery_id:

            raise Exception(
                "Unable to generate a unique recovery ID."
            )

        cursor.execute(
            """
            INSERT INTO food_submissions (
                recovery_id,
                donor_id,
                food_type,
                quantity,
                quantity_unit,
                preparation_date,
                preparation_time,
                served_to_customers,
                handling_information,
                storage_handling_information,
                applicable_consumption_date,
                applicable_consumption_time,
                available_from,
                available_until,
                donor_declaration,
                donor_notes,
                status
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, 'SUBMITTED'
            )
            """,
            (
                recovery_id,
                session.get("donor_id"),
                food_type,
                quantity,
                quantity_unit,
                preparation_date,
                preparation_time,
                int(served_to_customers),
                handling_information or None,
                storage_handling_information or None,
                applicable_consumption_date or None,
                applicable_consumption_time or None,
                available_from_dt,
                available_until_dt,
                1,
                donor_notes or None
            )
        )

        mysql.connection.commit()

        flash(
            f"Surplus food declared successfully. "
            f"Recovery ID: {recovery_id}",
            "success"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    except Exception as error:

        if mysql.connection:

            mysql.connection.rollback()

        flash(
            f"Unable to declare surplus: {error}",
            "error"
        )

        return redirect(
            url_for("donor.declare_surplus")
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# RECOVERY MANAGEMENT
# =========================================================

@donor_bp.route(
    "/recovery-management"
)
@donor_required
def recovery_management():

    donor_id = session.get(
        "donor_id"
    )

    if not donor_id:

        session.clear()

        return redirect(
            url_for("donor.login")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            SELECT
                food_submission_id,
                recovery_id,
                food_type,
                quantity,
                quantity_unit,
                preparation_date,
                preparation_time,
                served_to_customers,
                handling_information,
                storage_handling_information,
                applicable_consumption_date,
                applicable_consumption_time,
                available_from,
                available_until,
                donor_declaration,
                donor_notes,
                status,
                created_at,
                updated_at
            FROM food_submissions
            WHERE donor_id = %s
            ORDER BY created_at DESC
            """,
            (donor_id,)
        )

        recovery_records = cursor.fetchall()

        return render_template(
            "recovery_management.html",
            recovery_records=recovery_records
        )

    except Exception as error:

        return (
            "Unable to load Recovery Management. "
            f"Error: {error}"
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# RECOVERY MATCHING
# =========================================================

@donor_bp.route(
    "/recovery-matches"
)
@donor_required
def recovery_matches():

    donor_id = session.get(
        "donor_id"
    )

    if not donor_id:

        session.clear()

        return redirect(
            url_for("donor.login")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        # -------------------------------------------------
        # FIND THE DONOR'S LATEST ACTIVE FOOD SUBMISSION
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                food_submission_id,
                recovery_id,
                food_type,
                quantity,
                quantity_unit,
                available_from,
                available_until,
                status
            FROM food_submissions
            WHERE donor_id = %s
              AND status IN (
                  'SUBMITTED',
                  'MATCHING',
                  'VERIFICATION_PENDING'
              )
              AND available_until >= NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (donor_id,)
        )

        food = cursor.fetchone()

        if not food:

            return render_template(
                "recovery_matches.html",
                food=None,
                matches=[]
            )

        # -------------------------------------------------
        # LOAD ACTIVE NGO REQUIREMENTS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                r.requirement_id,
                r.ngo_id,
                r.food_type_preference,
                r.required_quantity,
                r.quantity_unit,
                r.required_by,
                r.service_area,
                r.max_distance_km,
                r.requirement_status,
                r.notes,
                na.ngo_code,
                na.account_status
            FROM ngo_recovery_requirements r
            INNER JOIN ngo_accounts na
                ON r.ngo_id = na.ngo_id
            WHERE r.requirement_status = 'ACTIVE'
              AND na.account_status = 'ACTIVE'
              AND r.required_by >= NOW()
            ORDER BY r.required_by ASC
            """
        )

        requirements = cursor.fetchall()

        matches = []

        # -------------------------------------------------
        # TRANSPARENT AI-ASSISTED MATCHING
        #
        # Quantity       = 30%
        # Food Type      = 30%
        # Urgency        = 20%
        # Availability   = 20%
        #
        # Distance is currently not scored because the
        # required coordinate/location data is not yet
        # available in the current NGO account structure.
        # -------------------------------------------------

        for requirement in requirements:

            quantity_score = 0.0
            food_type_score = 0.0
            urgency_score = 0.0
            availability_score = 0.0

            # -------------------------------------------------
            # QUANTITY COMPATIBILITY
            # -------------------------------------------------

            if (
                requirement["quantity_unit"]
                == food["quantity_unit"]
            ):

                required_quantity = float(
                    requirement["required_quantity"]
                )

                food_quantity = float(
                    food["quantity"]
                )

                if food_quantity >= required_quantity:

                    quantity_score = 100.0

                elif food_quantity > 0:

                    quantity_score = round(
                        (
                            food_quantity
                            / required_quantity
                        ) * 100,
                        2
                    )

            # -------------------------------------------------
            # FOOD TYPE COMPATIBILITY
            # -------------------------------------------------

            preference = (
                requirement["food_type_preference"]
            )

            if preference == "ANY":

                food_type_score = 100.0

            elif preference == food["food_type"]:

                food_type_score = 100.0

            else:

                food_type_score = 0.0

            # -------------------------------------------------
            # URGENCY SCORE
            # -------------------------------------------------

            now = datetime.now()

            required_by = requirement[
                "required_by"
            ]

            hours_remaining = (
                required_by - now
            ).total_seconds() / 3600

            if hours_remaining <= 0:

                urgency_score = 0.0

            elif hours_remaining <= 2:

                urgency_score = 100.0

            elif hours_remaining <= 6:

                urgency_score = 80.0

            elif hours_remaining <= 12:

                urgency_score = 60.0

            elif hours_remaining <= 24:

                urgency_score = 40.0

            else:

                urgency_score = 20.0

            # -------------------------------------------------
            # AVAILABILITY COMPATIBILITY
            # -------------------------------------------------

            availability_start = food[
                "available_from"
            ]

            availability_end = food[
                "available_until"
            ]

            if (
                availability_start
                <= required_by
                <= availability_end
            ):

                availability_score = 100.0

            elif (
                required_by
                >= availability_start
                and required_by <= availability_end
            ):

                availability_score = 70.0

            elif required_by >= availability_start:

                availability_score = 70.0

            else:

                availability_score = 0.0

            # -------------------------------------------------
            # DISTANCE
            # -------------------------------------------------

            distance_km = None

            # -------------------------------------------------
            # OVERALL MATCH SCORE
            # -------------------------------------------------

            match_score = round(
                (
                    quantity_score * 0.30
                    + food_type_score * 0.30
                    + urgency_score * 0.20
                    + availability_score * 0.20
                ),
                2
            )

            # -------------------------------------------------
            # RECOMMENDATION REASON
            # -------------------------------------------------

            reasons = []

            if quantity_score >= 100:

                reasons.append(
                    "quantity requirement is fully compatible"
                )

            elif quantity_score > 0:

                reasons.append(
                    "available quantity partially meets the requirement"
                )

            else:

                reasons.append(
                    "quantity unit is not compatible"
                )

            if food_type_score == 100:

                reasons.append(
                    "food type preference is compatible"
                )

            else:

                reasons.append(
                    "food type preference does not match"
                )

            if urgency_score >= 80:

                reasons.append(
                    "recovery requirement is time-sensitive"
                )

            elif urgency_score >= 40:

                reasons.append(
                    "recovery requirement has moderate urgency"
                )

            else:

                reasons.append(
                    "recovery requirement has lower urgency"
                )

            if availability_score >= 70:

                reasons.append(
                    "food availability overlaps the required recovery time"
                )

            else:

                reasons.append(
                    "availability window has limited overlap"
                )

            recommendation_reason = (
                "; ".join(reasons)
            )

            # -------------------------------------------------
            # GENERATE UNIQUE MATCH CODE
            # -------------------------------------------------

            match_code = None

            # First check whether this exact combination
            # already has a match.
            cursor.execute(
                """
                SELECT
                    match_id,
                    match_code,
                    match_status
                FROM recovery_matches
                WHERE food_submission_id = %s
                  AND ngo_id = %s
                  AND (
                      requirement_id = %s
                      OR (
                          requirement_id IS NULL
                          AND %s IS NULL
                      )
                  )
                LIMIT 1
                """,
                (
                    food["food_submission_id"],
                    requirement["ngo_id"],
                    requirement["requirement_id"],
                    requirement["requirement_id"]
                )
            )

            existing_match = cursor.fetchone()

            # -------------------------------------------------
            # UPDATE EXISTING MATCH
            # -------------------------------------------------

            if existing_match:

                match_code = existing_match[
                    "match_code"
                ]

                # Do not overwrite an already progressed
                # match such as ASSIGNED, COMPLETED,
                # FAILED or CANCELLED.
                current_status = existing_match[
                    "match_status"
                ]

                if current_status in (
                    "RECOMMENDED",
                    "DECLINED"
                ):

                    cursor.execute(
                        """
                        UPDATE recovery_matches
                        SET
                            match_score = %s,
                            quantity_compatibility_score = %s,
                            food_type_compatibility_score = %s,
                            distance_km = %s,
                            urgency_score = %s,
                            availability_score = %s,
                            match_status = 'RECOMMENDED',
                            recommendation_reason = %s,
                            generated_at = NOW()
                        WHERE match_id = %s
                        """,
                        (
                            match_score,
                            quantity_score,
                            food_type_score,
                            distance_km,
                            urgency_score,
                            availability_score,
                            recommendation_reason,
                            existing_match["match_id"]
                        )
                    )

            else:

                # -------------------------------------------------
                # CREATE NEW MATCH CODE
                # -------------------------------------------------

                for _ in range(20):

                    candidate_match_code = (
                        "MAT-"
                        + secrets.token_hex(5).upper()
                    )

                    cursor.execute(
                        """
                        SELECT match_id
                        FROM recovery_matches
                        WHERE match_code = %s
                        LIMIT 1
                        """,
                        (candidate_match_code,)
                    )

                    if not cursor.fetchone():

                        match_code = candidate_match_code

                        break

                if not match_code:

                    raise Exception(
                        "Unable to generate a unique recovery match code."
                    )

                # -------------------------------------------------
                # INSERT NEW MATCH
                # -------------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO recovery_matches (
                        match_code,
                        food_submission_id,
                        ngo_id,
                        requirement_id,
                        match_score,
                        quantity_compatibility_score,
                        food_type_compatibility_score,
                        distance_km,
                        urgency_score,
                        availability_score,
                        match_status,
                        recommendation_reason
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        'RECOMMENDED',
                        %s
                    )
                    """,
                    (
                        match_code,
                        food["food_submission_id"],
                        requirement["ngo_id"],
                        requirement["requirement_id"],
                        match_score,
                        quantity_score,
                        food_type_score,
                        distance_km,
                        urgency_score,
                        availability_score,
                        recommendation_reason
                    )
                )

            # -------------------------------------------------
            # ADD MATCH TO PAGE RESULT
            # -------------------------------------------------

            matches.append({
                "match_code": match_code,

                "requirement_id":
                    requirement["requirement_id"],

                "ngo_id":
                    requirement["ngo_id"],

                "ngo_code":
                    requirement["ngo_code"],

                "food_type_preference":
                    requirement["food_type_preference"],

                "required_quantity":
                    requirement["required_quantity"],

                "quantity_unit":
                    requirement["quantity_unit"],

                "required_by":
                    requirement["required_by"],

                "service_area":
                    requirement["service_area"],

                "max_distance_km":
                    requirement["max_distance_km"],

                "match_score":
                    match_score,

                "quantity_compatibility_score":
                    quantity_score,

                "food_type_compatibility_score":
                    food_type_score,

                "distance_km":
                    distance_km,

                "urgency_score":
                    urgency_score,

                "availability_score":
                    availability_score,

                "recommendation_reason":
                    recommendation_reason
            })

        # -------------------------------------------------
        # MARK FOOD SUBMISSION AS MATCHING
        # -------------------------------------------------

        if requirements:

            cursor.execute(
                """
                UPDATE food_submissions
                SET status = 'MATCHING'
                WHERE food_submission_id = %s
                  AND status = 'SUBMITTED'
                """,
                (
                    food["food_submission_id"],
                )
            )

        # -------------------------------------------------
        # COMMIT ALL GENERATED MATCHES
        # -------------------------------------------------

        mysql.connection.commit()

        # -------------------------------------------------
        # SORT HIGHEST MATCH SCORE FIRST
        # -------------------------------------------------

        matches.sort(
            key=lambda item: item["match_score"],
            reverse=True
        )

        return render_template(
            "recovery_matches.html",
            food=food,
            matches=matches
        )

    except Exception as error:

        if mysql.connection:

            mysql.connection.rollback()

        return (
            "Unable to generate recovery matches. "
            f"Error: {error}"
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# DONOR DASHBOARD
# =========================================================

@donor_bp.route(
    "/dashboard"
)
@donor_required
def dashboard():

    return render_template(
        "donor_dashboard.html",
        donor_username=session.get(
            "donor_username"
        ),
        donor_code=session.get(
            "donor_code"
        )
    )


# =========================================================
# DONOR PROFILE
# =========================================================

@donor_bp.route(
    "/profile"
)
@donor_required
def profile():

    donor_id = session.get(
        "donor_id"
    )

    if not donor_id:

        session.clear()

        return redirect(
            url_for("donor.login")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            SELECT
                da.donor_id,
                da.donor_code,
                da.username,
                da.account_status,
                da.activated_at,
                da.last_login_at,

                dapp.application_code,
                dapp.business_name,
                dapp.business_type,
                dapp.owner,
                dapp.phone,
                dapp.email,
                dapp.address,
                dapp.city,
                dapp.state,
                dapp.postal_code,
                dapp.year_established,
                dapp.food_service_since_year,
                dapp.event_name,
                dapp.event_type,
                dapp.event_date,
                dapp.application_status,
                dapp.submitted_at,
                dapp.reviewed_at

            FROM donor_accounts da

            INNER JOIN donor_applications dapp
                ON da.donor_application_id =
                   dapp.donor_application_id

            WHERE da.donor_id = %s

            LIMIT 1
            """,
            (donor_id,)
        )

        donor = cursor.fetchone()

        if not donor:

            session.clear()

            flash(
                "Donor account information could not be found.",
                "error"
            )

            return redirect(
                url_for("donor.login")
            )

        return render_template(
            "donor_profile.html",
            donor=donor
        )

    except Exception as error:

        return (
            "Unable to load donor profile. "
            f"Error: {error}"
        )

    finally:

        if cursor:

            cursor.close()


# =========================================================
# DONOR LOGOUT
# =========================================================

@donor_bp.route(
    "/logout"
)
def logout():

    session.clear()

    return redirect(
        url_for("donor.login")
    )