from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app,
)

from app.db import mysql

import os
import secrets
import logging

from decimal import Decimal, InvalidOperation
from datetime import datetime
from functools import wraps

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


ngo_bp = Blueprint("ngo", __name__, url_prefix="/ngo")

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024

REQUIRED_VERIFICATION_CHECKS = (
    "odour_condition",
    "food_condition_check",
    "packaging_condition",
    "storage_handling_condition",
    "quantity_check",
    "contamination_check",
)

DOCUMENT_TYPES = {
    "registration_certificate": "REGISTRATION_CERTIFICATE",
    "authorization_document": "PAN_DOCUMENT",
    "address_proof": "ADDRESS_PROOF",
    "representative_id_proof": "AUTHORIZED_REPRESENTATIVE_ID",
}


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_cursor():
    return mysql.connection.cursor()


def row_to_dict(row, cursor):
    if row is None:
        return None

    if isinstance(row, dict):
        return row

    columns = [column[0] for column in cursor.description]

    return dict(zip(columns, row))


def rows_to_dicts(rows, cursor):
    if not rows:
        return []

    if isinstance(rows[0], dict):
        return rows

    columns = [column[0] for column in cursor.description]

    return [dict(zip(columns, row)) for row in rows]


def execute_one(cursor, query, parameters=()):
    cursor.execute(query, parameters)
    return row_to_dict(cursor.fetchone(), cursor)


def execute_all(cursor, query, parameters=()):
    cursor.execute(query, parameters)
    return rows_to_dicts(cursor.fetchall(), cursor)


def generate_code(prefix):
    return f"{prefix}-{secrets.token_hex(5).upper()}"


def generate_ngo_code():
    return generate_code("NGO")


def generate_match_code():
    return generate_code("MAT")


def generate_verification_code():
    return generate_code("VER")


def generate_collection_code():
    return generate_code("COL")


def generate_distribution_code():
    return generate_code("DIS")


def allowed_document(filename):
    if not filename or "." not in filename:
        return False

    return filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS


def parse_decimal(value, field_name="quantity"):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.")

    if not number.is_finite():
        raise ValueError(f"Enter a valid {field_name}.")

    return number


def parse_optional_decimal(value, field_name="value"):
    if value is None or str(value).strip() == "":
        return None

    return parse_decimal(value, field_name)


def parse_datetime(value):
    if not value:
        return None

    for fmt in (
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue

    raise ValueError("Enter a valid date and time.")


def normalize_phone(phone):
    digits = "".join(
        character
        for character in str(phone or "")
        if character.isdigit()
    )

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    if len(digits) != 10:
        raise ValueError("Enter a valid 10-digit mobile number.")

    return digits


def ngo_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if (
            not session.get("ngo_id")
            or not session.get("ngo_authenticated")
        ):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("ngo.login"))

        return function(*args, **kwargs)

    return decorated_function


def get_active_representative(cursor, ngo_id):
    return execute_one(
        cursor,
        """
        SELECT *
        FROM ngo_representatives
        WHERE ngo_id = %s
          AND representative_status = 'ACTIVE'
          AND (
              authorized_from IS NULL
              OR authorized_from <= CURDATE()
          )
          AND (
              authorized_until IS NULL
              OR authorized_until >= CURDATE()
          )
        ORDER BY representative_id DESC
        LIMIT 1
        """,
        (ngo_id,),
    )


def verification_checks_passed(verification):
    if not verification:
        return False

    return (
        verification.get("odour_condition") == "PASS"
        and verification.get("food_condition_check") == "PASS"
        and verification.get("packaging_condition") == "ACCEPTABLE"
        and verification.get("storage_handling_condition") == "ACCEPTABLE"
        and verification.get("quantity_check") == "PASS"
        and verification.get("contamination_check") == "PASS"
    )


def get_latest_verification(cursor, match_id):
    return execute_one(
        cursor,
        """
        SELECT *
        FROM verification_records
        WHERE match_id = %s
        ORDER BY verification_id DESC
        LIMIT 1
        """,
        (match_id,),
    )


def get_match_for_ngo(cursor, match_id, ngo_id):
    return execute_one(
        cursor,
        """
        SELECT
            rm.*,
            fs.recovery_id,
            fs.donor_id,
            fs.food_type,
            fs.quantity,
            fs.quantity_unit,
            fs.preparation_date,
            fs.preparation_time,
            fs.served_to_customers,
            fs.handling_information,
            fs.storage_handling_information,
            fs.applicable_consumption_date,
            fs.applicable_consumption_time,
            fs.available_from,
            fs.available_until,
            fs.donor_notes,
            fs.status AS food_status
        FROM recovery_matches rm
        INNER JOIN food_submissions fs
            ON fs.food_submission_id = rm.food_submission_id
        WHERE rm.match_id = %s
          AND rm.ngo_id = %s
        LIMIT 1
        """,
        (match_id, ngo_id),
    )


def get_allocated_quantity(cursor, food_submission_id):
    result = execute_one(
        cursor,
        """
        SELECT COALESCE(SUM(accepted_quantity), 0)
            AS allocated_quantity
        FROM recovery_matches
        WHERE food_submission_id = %s
          AND match_status IN ('ASSIGNED', 'COMPLETED')
        """,
        (food_submission_id,),
    )

    return Decimal(
        str((result or {}).get("allocated_quantity") or 0)
    )


def get_remaining_food_quantity(
    cursor,
    food_submission_id,
    original_quantity,
):
    allocated = get_allocated_quantity(
        cursor,
        food_submission_id,
    )

    return max(
        Decimal("0"),
        Decimal(str(original_quantity)) - allocated,
    )


def _get_upload_folder():
    folder = os.path.join(
        current_app.root_path,
        "static",
        "uploads",
        "ngo_documents",
    )

    os.makedirs(folder, exist_ok=True)

    return folder


def _redirect_recovery():
    return redirect(url_for("ngo.recovery_management"))


# ============================================================
# NGO REGISTRATION
# ============================================================

@ngo_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("ngo_registration.html")

    cursor = get_cursor()

    try:
        ngo_name = request.form.get("ngo_name", "").strip()
        registered_address = request.form.get(
            "registered_address", ""
        ).strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        postal_code = request.form.get("postal_code", "").strip()

        representative_name = request.form.get(
            "authorized_representative_name", ""
        ).strip()

        phone = normalize_phone(request.form.get("phone", ""))
        email = request.form.get("email", "").strip().lower()

        if not all([
            ngo_name,
            registered_address,
            city,
            state,
            postal_code,
            representative_name,
            email,
        ]):
            flash(
                "Complete all required registration fields.",
                "danger",
            )
            return redirect(url_for("ngo.register"))

        existing = execute_one(
            cursor,
            """
            SELECT ngo_application_id
            FROM ngo_applications
            WHERE phone = %s
            LIMIT 1
            """,
            (phone,),
        )

        if existing:
            flash(
                "An application already exists for this mobile number.",
                "warning",
            )
            return redirect(url_for("ngo.register"))

        cursor.execute(
            """
            INSERT INTO ngo_applications (
                application_code,
                ngo_name,
                registered_address,
                city,
                state,
                postal_code,
                authorized_representative_name,
                phone,
                email,
                application_status
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'APPLICATION_SUBMITTED'
            )
            """,
            (
                generate_ngo_code(),
                ngo_name,
                registered_address,
                city,
                state,
                postal_code,
                representative_name,
                phone,
                email,
            ),
        )

        application_id = cursor.lastrowid
        mysql.connection.commit()

        flash(
            "Registration submitted. Upload your four required documents.",
            "success",
        )

        return redirect(
            url_for(
                "ngo.upload_documents",
                application_id=application_id,
            )
        )

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO registration failed")

        flash(
            "Registration failed. Check the server error log.",
            "danger",
        )

        return redirect(url_for("ngo.register"))

    finally:
        cursor.close()


@ngo_bp.route("/registration-success")
def registration_success():
    return render_template("ngo_registration_success.html")


# ============================================================
# NGO DOCUMENT UPLOAD
# ============================================================

@ngo_bp.route(
    "/upload-documents/<int:application_id>",
    methods=["GET", "POST"],
)
def upload_documents(application_id):
    cursor = get_cursor()

    try:
        application = execute_one(
            cursor,
            """
            SELECT *
            FROM ngo_applications
            WHERE ngo_application_id = %s
            LIMIT 1
            """,
            (application_id,),
        )

        if not application:
            flash("NGO application was not found.", "danger")
            return redirect(url_for("ngo.register"))

        if request.method == "GET":
            return render_template(
                "ngo_document_upload.html",
                application=application,
                application_id=application_id,
            )

        if application.get("application_status") in {
            "VERIFIED",
            "ACTIVE_NGO",
            "REJECTED",
            "SUSPENDED",
        }:
            flash(
                "Documents cannot be uploaded for the current application status.",
                "warning",
            )
            return redirect(url_for("ngo.registration_success"))

        document_folder = _get_upload_folder()
        saved_files = []

        for form_name, document_type in DOCUMENT_TYPES.items():
            uploaded_file = request.files.get(form_name)

            if not uploaded_file or not uploaded_file.filename:
                flash(
                    "Upload all four required NGO documents.",
                    "danger",
                )
                return redirect(
                    url_for(
                        "ngo.upload_documents",
                        application_id=application_id,
                    )
                )

            if not allowed_document(uploaded_file.filename):
                flash(
                    "Documents must be PDF, PNG, JPG, or JPEG files.",
                    "danger",
                )
                return redirect(
                    url_for(
                        "ngo.upload_documents",
                        application_id=application_id,
                    )
                )

            uploaded_file.seek(0, os.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)

            if file_size > MAX_DOCUMENT_SIZE:
                flash(
                    "Each document must be 10 MB or smaller.",
                    "danger",
                )
                return redirect(
                    url_for(
                        "ngo.upload_documents",
                        application_id=application_id,
                    )
                )

            original_name = secure_filename(uploaded_file.filename)
            stored_name = (
                f"{application_id}_{secrets.token_hex(8)}_{original_name}"
            )

            saved_files.append({
                "file": uploaded_file,
                "document_type": document_type,
                "original_name": original_name,
                "stored_name": stored_name,
                "full_path": os.path.join(
                    document_folder,
                    stored_name,
                ),
            })

        written_paths = []

        try:
            for document in saved_files:
                document["file"].save(document["full_path"])
                written_paths.append(document["full_path"])

                document["relative_path"] = os.path.relpath(
                    document["full_path"],
                    current_app.root_path,
                ).replace("\\", "/")

            cursor.execute(
                """
                DELETE FROM ngo_documents
                WHERE ngo_application_id = %s
                """,
                (application_id,),
            )

            for document in saved_files:
                cursor.execute(
                    """
                    INSERT INTO ngo_documents (
                        ngo_application_id,
                        document_type,
                        original_filename,
                        stored_filename,
                        file_path,
                        verification_status
                    )
                    VALUES (%s, %s, %s, %s, %s, 'PENDING')
                    """,
                    (
                        application_id,
                        document["document_type"],
                        document["original_name"],
                        document["stored_name"],
                        document["relative_path"],
                    ),
                )

            cursor.execute(
                """
                UPDATE ngo_applications
                SET application_status = 'DOCUMENT_REVIEW'
                WHERE ngo_application_id = %s
                """,
                (application_id,),
            )

            mysql.connection.commit()

        except Exception:
            mysql.connection.rollback()

            for path in written_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    logger.exception(
                        "Unable to remove an uploaded file"
                    )

            raise

        flash(
            "All four documents were uploaded for admin review.",
            "success",
        )

        return redirect(url_for("ngo.registration_success"))

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO document upload failed")

        flash(
            "Document upload failed. Check the server error log.",
            "danger",
        )

        return redirect(
            url_for(
                "ngo.upload_documents",
                application_id=application_id,
            )
        )

    finally:
        cursor.close()


# ============================================================
# NGO ACCOUNT ACTIVATION
# ============================================================

@ngo_bp.route("/activate", methods=["GET", "POST"])
def activate():
    if request.method == "GET":
        return render_template("ngo_activation.html")

    try:
        phone = normalize_phone(request.form.get("phone", ""))
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("ngo.activate"))

    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if len(password) < 8:
        flash(
            "Password must contain at least 8 characters.",
            "danger",
        )
        return redirect(url_for("ngo.activate"))

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("ngo.activate"))

    cursor = get_cursor()

    try:
        application = execute_one(
            cursor,
            """
            SELECT *
            FROM ngo_applications
            WHERE phone = %s
              AND application_status = 'VERIFIED'
            LIMIT 1
            FOR UPDATE
            """,
            (phone,),
        )

        if not application:
            flash(
                "No verified NGO application was found for that number.",
                "danger",
            )
            return redirect(url_for("ngo.activate"))

        existing_account = execute_one(
            cursor,
            """
            SELECT ngo_id
            FROM ngo_accounts
            WHERE ngo_application_id = %s
            LIMIT 1
            """,
            (application["ngo_application_id"],),
        )

        if existing_account:
            flash(
                "An account already exists. Please log in.",
                "info",
            )
            return redirect(url_for("ngo.login"))

        cursor.execute(
            """
            INSERT INTO ngo_accounts (
                ngo_code,
                ngo_application_id,
                username,
                password_hash,
                account_status,
                activated_at
            )
            VALUES (%s, %s, %s, %s, 'ACTIVE', NOW())
            """,
            (
                generate_ngo_code(),
                application["ngo_application_id"],
                phone,
                generate_password_hash(password),
            ),
        )

        ngo_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO ngo_representatives (
                representative_code,
                ngo_id,
                full_name,
                phone,
                email,
                representative_status,
                authorized_from
            )
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', CURDATE())
            """,
            (
                generate_code("REP"),
                ngo_id,
                application["authorized_representative_name"],
                application["phone"],
                application.get("email"),
            ),
        )

        cursor.execute(
            """
            UPDATE ngo_applications
            SET application_status = 'ACTIVE_NGO'
            WHERE ngo_application_id = %s
              AND application_status = 'VERIFIED'
            """,
            (application["ngo_application_id"],),
        )

        mysql.connection.commit()

        flash(
            "Your NGO account is active. You can now log in.",
            "success",
        )

        return redirect(url_for("ngo.login"))

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO activation failed")

        flash(
            "Account activation failed. Check the server error log.",
            "danger",
        )

        return redirect(url_for("ngo.activate"))

    finally:
        cursor.close()


# ============================================================
# NGO LOGIN
# ============================================================

@ngo_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("ngo_login.html")

    identifier = request.form.get(
        "phone",
        request.form.get("username", ""),
    ).strip()

    password = request.form.get("password", "")

    if not identifier or not password:
        flash(
            "Enter your mobile number and password.",
            "danger",
        )
        return redirect(url_for("ngo.login"))

    try:
        identifier = normalize_phone(identifier)
    except ValueError:
        flash(
            "Enter a valid registered mobile number.",
            "danger",
        )
        return redirect(url_for("ngo.login"))

    cursor = get_cursor()

    try:
        account = execute_one(
            cursor,
            """
            SELECT
                na.ngo_id,
                na.ngo_application_id,
                na.password_hash,
                na.account_status,
                app.ngo_name,
                app.phone,
                app.email
            FROM ngo_accounts na
            INNER JOIN ngo_applications app
                ON app.ngo_application_id = na.ngo_application_id
            WHERE app.phone = %s
            LIMIT 1
            """,
            (identifier,),
        )

        if (
            not account
            or account["account_status"] != "ACTIVE"
            or not check_password_hash(
                account["password_hash"],
                password,
            )
        ):
            flash(
                "Invalid credentials or inactive NGO account.",
                "danger",
            )
            return redirect(url_for("ngo.login"))

        session.clear()

        session["ngo_id"] = account["ngo_id"]
        session["ngo_application_id"] = account["ngo_application_id"]
        session["ngo_mobile"] = account["phone"]
        session["ngo_logged_in"] = True
        session["ngo_authenticated"] = True

        cursor.execute(
            """
            UPDATE ngo_accounts
            SET last_login_at = NOW()
            WHERE ngo_id = %s
            """,
            (account["ngo_id"],),
        )

        mysql.connection.commit()

        flash("Welcome to ResQMeal.", "success")

        return redirect(url_for("ngo.dashboard"))

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO login failed")

        flash("Login could not be completed.", "danger")

        return redirect(url_for("ngo.login"))

    finally:
        cursor.close()


# ============================================================
# NGO LOGOUT
# ============================================================

@ngo_bp.route("/logout")
def logout():
    session.pop("ngo_id", None)
    session.pop("ngo_application_id", None)
    session.pop("ngo_mobile", None)
    session.pop("ngo_logged_in", None)
    session.pop("ngo_authenticated", None)

    flash("You have been logged out.", "info")

    return redirect(url_for("ngo.login"))


# ============================================================
# NGO DASHBOARD
# ============================================================

@ngo_bp.route("/dashboard")
@ngo_required
def dashboard():
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        counts = execute_one(
            cursor,
            """
            SELECT
                COALESCE(SUM(match_status = 'RECOMMENDED'), 0)
                    AS recommended_count,
                COALESCE(SUM(match_status = 'ASSIGNED'), 0)
                    AS assigned_count,
                COALESCE(SUM(match_status = 'COMPLETED'), 0)
                    AS completed_count,
                COALESCE(SUM(match_status = 'FAILED'), 0)
                    AS failed_count
            FROM recovery_matches
            WHERE ngo_id = %s
            """,
            (ngo_id,),
        ) or {}

        requirements = execute_all(
            cursor,
            """
            SELECT *
            FROM ngo_recovery_requirements
            WHERE ngo_id = %s
            ORDER BY requirement_id DESC
            LIMIT 5
            """,
            (ngo_id,),
        )

        return render_template(
            "ngo_dashboard.html",
            counts=counts,
            requirements=requirements,
        )

    except Exception:
        logger.exception("NGO dashboard failed")

        flash(
            "Dashboard information could not be loaded.",
            "danger",
        )

        return render_template(
            "ngo_dashboard.html",
            counts={},
            requirements=[],
        )

    finally:
        cursor.close()


# ============================================================
# NGO RECOVERY REQUIREMENTS
# ============================================================

@ngo_bp.route(
    "/recovery-requirements",
    methods=["GET", "POST"],
)
@ngo_required
def recovery_requirements():
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        if request.method == "POST":
            food_type = request.form.get(
                "food_type_preference", "ANY"
            ).strip().upper()

            quantity = parse_decimal(
                request.form.get("required_quantity"),
                "required quantity",
            )

            unit = request.form.get(
                "quantity_unit", "KG"
            ).strip().upper()

            required_by = parse_datetime(
                request.form.get("required_by", "")
            )

            service_area = request.form.get(
                "service_area", ""
            ).strip()

            max_distance = parse_optional_decimal(
                request.form.get("max_distance_km"),
                "maximum distance",
            )

            notes = request.form.get("notes", "").strip()

            if food_type not in {
                "ANY",
                "VEGETARIAN",
                "NON_VEGETARIAN",
            }:
                raise ValueError("Invalid food preference.")

            if unit not in {"KG", "LITRES", "PIECES"}:
                raise ValueError("Invalid quantity unit.")

            if quantity <= 0:
                raise ValueError(
                    "Required quantity must be positive."
                )

            if not service_area:
                raise ValueError("Enter your service area.")

            if required_by and required_by < datetime.now():
                raise ValueError(
                    "Required-by date must be in the future."
                )

            if max_distance is not None and max_distance < 0:
                raise ValueError(
                    "Distance cannot be negative."
                )

            cursor.execute(
                """
                INSERT INTO ngo_recovery_requirements (
                    ngo_id,
                    food_type_preference,
                    required_quantity,
                    quantity_unit,
                    required_by,
                    service_area,
                    max_distance_km,
                    requirement_status,
                    notes
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s
                )
                """,
                (
                    ngo_id,
                    food_type,
                    quantity,
                    unit,
                    required_by,
                    service_area,
                    max_distance,
                    notes,
                ),
            )

            mysql.connection.commit()

            flash(
                "Recovery requirement saved successfully.",
                "success",
            )

            return redirect(
                url_for("ngo.recovery_requirements")
            )

        requirements = execute_all(
            cursor,
            """
            SELECT *
            FROM ngo_recovery_requirements
            WHERE ngo_id = %s
            ORDER BY requirement_id DESC
            """,
            (ngo_id,),
        )

        return render_template(
            "ngo_recovery_requirements.html",
            requirements=requirements,
        )

    except ValueError as error:
        mysql.connection.rollback()
        flash(str(error), "danger")

        return redirect(
            url_for("ngo.recovery_requirements")
        )

    except Exception:
        mysql.connection.rollback()
        logger.exception(
            "Saving NGO recovery requirement failed"
        )

        flash(
            "Could not save the requirement. Check the server error log.",
            "danger",
        )

        return redirect(
            url_for("ngo.recovery_requirements")
        )

    finally:
        cursor.close()


# ============================================================
# RECOVERY MATCHES
# Available opportunities are separate from accepted recoveries.
# ============================================================

@ngo_bp.route("/recovery-matches")
@ngo_required
def recovery_matches():
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        matches = execute_all(
            cursor,
            """
            SELECT
                rm.*,
                fs.recovery_id,
                fs.food_submission_id,
                fs.donor_id,
                fs.food_type,
                fs.quantity,
                fs.quantity_unit,
                fs.preparation_date,
                fs.preparation_time,
                fs.served_to_customers,
                fs.handling_information,
                fs.storage_handling_information,
                fs.applicable_consumption_date,
                fs.applicable_consumption_time,
                fs.available_from,
                fs.available_until,
                fs.donor_notes,
                fs.status AS food_status
            FROM recovery_matches rm
            INNER JOIN food_submissions fs
                ON fs.food_submission_id = rm.food_submission_id
            WHERE rm.ngo_id = %s
              AND rm.match_status = 'RECOMMENDED'
              AND fs.status IN (
                  'SUBMITTED',
                  'MATCHING',
                  'VERIFICATION_PENDING',
                  'VERIFIED'
              )
              AND (
                  fs.available_until IS NULL
                  OR fs.available_until >= NOW()
              )
            ORDER BY
                fs.available_until ASC,
                rm.created_at DESC,
                rm.match_id DESC
            """,
            (ngo_id,),
        )

        for match in matches:
            match["quantity_remaining"] = (
                get_remaining_food_quantity(
                    cursor,
                    match["food_submission_id"],
                    match["quantity"],
                )
            )

        matches = [
            match for match in matches
            if Decimal(str(match["quantity_remaining"])) > 0
        ]

        return render_template(
            "recovery_matches.html",
            matches=matches,
            available_matches=matches,
        )

    except Exception:
        logger.exception("NGO recovery matches failed")

        flash(
            "Unable to load Recovery Matches. Check the server error log.",
            "danger",
        )

        return render_template(
            "recovery_matches.html",
            matches=[],
            available_matches=[],
        )

    finally:
        cursor.close()


# ============================================================
# ACCEPT RECOVERY MATCH
# ============================================================

@ngo_bp.route(
    "/accept-recovery-match/<int:match_id>",
    methods=["POST"],
)
@ngo_required
def accept_recovery_match(match_id):
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        match = get_match_for_ngo(
            cursor,
            match_id,
            ngo_id,
        )

        if not match or match["match_status"] != "RECOMMENDED":
            flash(
                "This recovery match is no longer available.",
                "warning",
            )
            return redirect(url_for("ngo.recovery_matches"))

        cursor.execute(
            """
            SELECT *
            FROM food_submissions
            WHERE food_submission_id = %s
            FOR UPDATE
            """,
            (match["food_submission_id"],),
        )

        food = row_to_dict(cursor.fetchone(), cursor)

        if not food:
            raise ValueError("Food submission was not found.")

        if (
            food.get("available_until")
            and food["available_until"] < datetime.now()
        ):
            raise ValueError("The recovery window has expired.")

        if food["status"] not in {
            "SUBMITTED",
            "MATCHING",
            "VERIFICATION_PENDING",
            "VERIFIED",
        }:
            raise ValueError(
                "This food submission is not available for acceptance."
            )

        requested_quantity = parse_decimal(
            request.form.get(
                "accepted_quantity",
                str(food["quantity"]),
            ),
            "accepted quantity",
        )

        if requested_quantity <= 0:
            raise ValueError(
                "Accepted quantity must be positive."
            )

        remaining = get_remaining_food_quantity(
            cursor,
            food["food_submission_id"],
            food["quantity"],
        )

        if requested_quantity > remaining:
            raise ValueError(
                f"Only {remaining} {food['quantity_unit']} remains available."
            )

        notes = request.form.get(
            "decision_notes", ""
        ).strip()

        cursor.execute(
            """
            UPDATE recovery_matches
            SET match_status = 'ASSIGNED',
                accepted_quantity = %s,
                assigned_at = NOW(),
                decision_at = NOW(),
                decision_notes = %s
            WHERE match_id = %s
              AND ngo_id = %s
              AND match_status = 'RECOMMENDED'
            """,
            (
                requested_quantity,
                notes,
                match_id,
                ngo_id,
            ),
        )

        if cursor.rowcount != 1:
            raise ValueError(
                "The match could not be assigned."
            )

        # Do not globally change the food submission to
        # VERIFICATION_PENDING here. Other NGOs may still need
        # to claim the remaining unallocated quantity.

        if food["status"] in {"SUBMITTED", "MATCHING"}:
            cursor.execute(
                """
                UPDATE food_submissions
                SET status = 'MATCHING'
                WHERE food_submission_id = %s
                  AND status IN ('SUBMITTED', 'MATCHING')
                """,
                (food["food_submission_id"],),
            )

        mysql.connection.commit()

        flash(
            "Recovery accepted. Complete all six on-site "
            "verification checks before pickup.",
            "success",
        )

        return _redirect_recovery()

    except ValueError as error:
        mysql.connection.rollback()
        flash(str(error), "warning")
        return redirect(url_for("ngo.recovery_matches"))

    except Exception:
        mysql.connection.rollback()
        logger.exception("Accepting recovery match failed")

        flash(
            "Could not accept the recovery match.",
            "danger",
        )

        return redirect(url_for("ngo.recovery_matches"))

    finally:
        cursor.close()


# ============================================================
# DECLINE RECOVERY MATCH
# ============================================================

@ngo_bp.route(
    "/decline-recovery-match/<int:match_id>",
    methods=["POST"],
)
@ngo_required
def decline_recovery_match(match_id):
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        cursor.execute(
            """
            UPDATE recovery_matches
            SET match_status = 'DECLINED',
                decision_at = NOW(),
                decision_notes = %s
            WHERE match_id = %s
              AND ngo_id = %s
              AND match_status = 'RECOMMENDED'
            """,
            (
                request.form.get(
                    "decision_notes", ""
                ).strip(),
                match_id,
                ngo_id,
            ),
        )

        if cursor.rowcount != 1:
            mysql.connection.rollback()

            flash(
                "This match is no longer recommended.",
                "warning",
            )

            return redirect(url_for("ngo.recovery_matches"))

        mysql.connection.commit()

        flash("Recovery match declined.", "info")

        return redirect(url_for("ngo.recovery_matches"))

    except Exception:
        mysql.connection.rollback()
        logger.exception("Declining recovery match failed")

        flash(
            "Could not decline the recovery match.",
            "danger",
        )

        return redirect(url_for("ngo.recovery_matches"))

    finally:
        cursor.close()
        # ============================================================
# ON-SITE RECOVERY VERIFICATION
# ============================================================

@ngo_bp.route(
    "/verify-recovery/<int:match_id>",
    methods=["GET", "POST"],
)
@ngo_required
def verify_recovery(match_id):
    ngo_id = session["ngo_id"]

    if request.method == "GET":
        return _redirect_recovery()

    cursor = get_cursor()

    try:
        # Lock the food submission before checking allocations.
        # This helps prevent concurrent updates from over-allocating it.
        preliminary_match = get_match_for_ngo(
            cursor,
            match_id,
            ngo_id,
        )

        if not preliminary_match:
            raise ValueError("Recovery record not found.")

        cursor.execute(
            """
            SELECT *
            FROM food_submissions
            WHERE food_submission_id = %s
            FOR UPDATE
            """,
            (preliminary_match["food_submission_id"],),
        )

        food = row_to_dict(cursor.fetchone(), cursor)

        match = get_match_for_ngo(
            cursor,
            match_id,
            ngo_id,
        )

        if not food or not match:
            raise ValueError("Recovery record not found.")

        if match["match_status"] != "ASSIGNED":
            raise ValueError(
                "Only assigned recoveries can be verified."
            )

        if match.get("available_until") and (
            match["available_until"] < datetime.now()
        ):
            raise ValueError("The recovery window has expired.")

        # A shared food status may change because another NGO
        # completes its allocation. Verification eligibility is
        # therefore checked using this match's own status.
        if food["status"] not in {
            "MATCHING",
            "VERIFICATION_PENDING",
            "VERIFIED",
            "COLLECTED",
        }:
            raise ValueError(
                "This food submission is no longer recoverable."
            )

        odour = request.form.get(
            "odour_condition", ""
        ).strip().upper()

        food_condition = request.form.get(
            "food_condition_check", ""
        ).strip().upper()

        packaging = request.form.get(
            "packaging_condition", ""
        ).strip().upper()

        storage = request.form.get(
            "storage_handling_condition", ""
        ).strip().upper()

        quantity_check = request.form.get(
            "quantity_check", ""
        ).strip().upper()

        contamination = request.form.get(
            "contamination_check", ""
        ).strip().upper()

        if odour not in {"PASS", "FAIL"}:
            raise ValueError("Complete the odour check.")

        if food_condition not in {"PASS", "FAIL"}:
            raise ValueError("Complete the food condition check.")

        if packaging not in {"ACCEPTABLE", "NOT_ACCEPTABLE"}:
            raise ValueError("Complete the packaging check.")

        if storage not in {"ACCEPTABLE", "NOT_ACCEPTABLE"}:
            raise ValueError(
                "Complete the storage and handling check."
            )

        if quantity_check not in {"PASS", "FAIL"}:
            raise ValueError("Complete the quantity check.")

        if contamination not in {"PASS", "FAIL"}:
            raise ValueError(
                "Complete the visible contamination check."
            )

        passed = (
            odour == "PASS"
            and food_condition == "PASS"
            and packaging == "ACCEPTABLE"
            and storage == "ACCEPTABLE"
            and quantity_check == "PASS"
            and contamination == "PASS"
        )

        representative_name = request.form.get(
            "representative_name", ""
        ).strip()

        if not representative_name:
            raise ValueError(
                "Enter the authorized representative's name."
            )

        representative_phone = normalize_phone(
            request.form.get("representative_phone", "")
        )

        physically_verified_quantity = parse_decimal(
            request.form.get(
                "physically_verified_quantity", ""
            ),
            "physically verified quantity",
        )

        original_quantity = Decimal(str(food["quantity"]))

        if (
            physically_verified_quantity <= 0
            or physically_verified_quantity > original_quantity
        ):
            raise ValueError(
                "Physically verified quantity must be positive "
                "and cannot exceed the submitted quantity."
            )

        accepted_quantity = Decimal("0")

        if passed:
            accepted_quantity = parse_decimal(
                request.form.get("accepted_quantity", ""),
                "accepted quantity",
            )

            if (
                accepted_quantity <= 0
                or accepted_quantity > physically_verified_quantity
            ):
                raise ValueError(
                    "Accepted quantity must be positive and cannot "
                    "exceed the physically verified quantity."
                )

            remaining = get_remaining_food_quantity(
                cursor,
                food["food_submission_id"],
                food["quantity"],
            )

            if accepted_quantity > remaining:
                raise ValueError(
                    f"Only {remaining} {food['quantity_unit']} "
                    "remains unallocated."
                )

        representative = execute_one(
            cursor,
            """
            SELECT *
            FROM ngo_representatives
            WHERE ngo_id = %s
              AND phone = %s
              AND representative_status = 'ACTIVE'
              AND (
                  authorized_from IS NULL
                  OR authorized_from <= CURDATE()
              )
              AND (
                  authorized_until IS NULL
                  OR authorized_until >= CURDATE()
              )
            LIMIT 1
            FOR UPDATE
            """,
            (ngo_id, representative_phone),
        )

        if not representative:
            raise ValueError(
                "The representative must be registered and "
                "currently authorized for this NGO."
            )

        if (
            representative["full_name"].strip().casefold()
            != representative_name.casefold()
        ):
            raise ValueError(
                "The representative name does not match "
                "the registered record."
            )

        remarks = request.form.get("remarks", "").strip()

        attempt = execute_one(
            cursor,
            """
            SELECT COALESCE(MAX(verification_attempt_no), 0) + 1
                AS next_attempt
            FROM verification_records
            WHERE food_submission_id = %s
            FOR UPDATE
            """,
            (food["food_submission_id"],),
        )

        attempt_no = int(attempt["next_attempt"])

        decision = "ACCEPT_AND_COLLECT" if passed else "REJECT"

        rejection_reason = (
            None
            if passed
            else "One or more mandatory verification checks failed."
        )

        cursor.execute(
            """
            INSERT INTO verification_records (
                verification_code,
                food_submission_id,
                match_id,
                ngo_id,
                representative_id,
                verification_attempt_no,
                source_identity_confirmed,
                submitted_batch_information_confirmed,
                preparation_information_confirmed,
                applicable_date_information_confirmed,
                packaging_condition,
                storage_handling_condition,
                observable_condition,
                physically_verified_quantity,
                accepted_quantity,
                quantity_unit,
                decision,
                rejection_reason,
                representative_confirmation,
                representative_confirmation_text,
                remarks,
                verification_datetime,
                odour_condition,
                food_condition_check,
                contamination_check,
                quantity_check
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                1, 1, 1, 1,
                %s, %s, %s, %s, %s, %s,
                %s, %s, 1, %s, %s, NOW(),
                %s, %s, %s, %s
            )
            """,
            (
                generate_verification_code(),
                food["food_submission_id"],
                match_id,
                ngo_id,
                representative["representative_id"],
                attempt_no,
                packaging,
                storage,
                "SUITABLE" if food_condition == "PASS" else "UNSUITABLE",
                physically_verified_quantity,
                accepted_quantity,
                food["quantity_unit"],
                decision,
                rejection_reason,
                f"Confirmed by {representative_name} ({representative_phone}).",
                remarks,
                odour,
                food_condition,
                contamination,
                quantity_check,
            ),
        )

        if passed:
            cursor.execute(
                """
                UPDATE recovery_matches
                SET accepted_quantity = %s,
                    decision_notes = %s
                WHERE match_id = %s
                  AND ngo_id = %s
                  AND match_status = 'ASSIGNED'
                """,
                (
                    accepted_quantity,
                    remarks,
                    match_id,
                    ngo_id,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    "Unable to update the verified recovery quantity."
                )

            # Do not set the shared food status to VERIFIED here:
            # another NGO may have an independent allocation.
        else:
            cursor.execute(
                """
                UPDATE recovery_matches
                SET match_status = 'FAILED',
                    decision_at = NOW(),
                    decision_notes = %s
                WHERE match_id = %s
                  AND ngo_id = %s
                  AND match_status = 'ASSIGNED'
                """,
                (
                    "On-site verification failed.",
                    match_id,
                    ngo_id,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    "Unable to record the failed recovery."
                )

        mysql.connection.commit()

        if passed:
            flash(
                "Verification passed. Pickup can now be confirmed.",
                "success",
            )
        else:
            flash(
                "Verification failed. Pickup is disabled for this recovery.",
                "danger",
            )

        return _redirect_recovery()

    except ValueError as error:
        mysql.connection.rollback()
        flash(str(error), "warning")
        return _redirect_recovery()

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO recovery verification failed")

        flash(
            "Unable to save verification. Check the server error log.",
            "danger",
        )

        return _redirect_recovery()

    finally:
        cursor.close()


# ============================================================
# CONFIRM PICKUP
# ============================================================

@ngo_bp.route(
    "/confirm-pickup/<int:match_id>",
    methods=["POST"],
)
@ngo_required
def confirm_pickup(match_id):
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        preliminary_match = get_match_for_ngo(
            cursor,
            match_id,
            ngo_id,
        )

        if not preliminary_match:
            raise ValueError("Recovery record not found.")

        cursor.execute(
            """
            SELECT *
            FROM food_submissions
            WHERE food_submission_id = %s
            FOR UPDATE
            """,
            (preliminary_match["food_submission_id"],),
        )

        food = row_to_dict(cursor.fetchone(), cursor)

        match = get_match_for_ngo(
            cursor,
            match_id,
            ngo_id,
        )

        if not food or not match:
            raise ValueError("Recovery record not found.")

        if match["match_status"] != "ASSIGNED":
            raise ValueError(
                "Only assigned recoveries can be collected."
            )

        verification = get_latest_verification(
            cursor,
            match_id,
        )

        if not verification_checks_passed(verification):
            raise ValueError(
                "All six verification checks must pass before pickup."
            )

        if verification.get("decision") != "ACCEPT_AND_COLLECT":
            raise ValueError(
                "This verification does not authorize pickup."
            )

        verified_quantity = Decimal(
            str(verification.get("accepted_quantity") or 0)
        )

        if verified_quantity <= 0:
            raise ValueError(
                "The verified accepted quantity is invalid."
            )

        representative = execute_one(
            cursor,
            """
            SELECT *
            FROM ngo_representatives
            WHERE representative_id = %s
              AND ngo_id = %s
              AND representative_status = 'ACTIVE'
              AND (
                  authorized_from IS NULL
                  OR authorized_from <= CURDATE()
              )
              AND (
                  authorized_until IS NULL
                  OR authorized_until >= CURDATE()
              )
            LIMIT 1
            FOR UPDATE
            """,
            (
                verification["representative_id"],
                ngo_id,
            ),
        )

        if not representative:
            raise ValueError(
                "The verifying representative is no longer authorized."
            )

        existing_collection = execute_one(
            cursor,
            """
            SELECT collection_id
            FROM collection_records
            WHERE verification_id = %s
              AND status = 'COLLECTED'
            LIMIT 1
            FOR UPDATE
            """,
            (verification["verification_id"],),
        )

        if existing_collection:
            raise ValueError(
                "Pickup has already been recorded."
            )

        # A match can only be collected once. Do not update the
        # shared food status to COLLECTED while other allocations
        # may still be waiting.
        cursor.execute(
            """
            INSERT INTO collection_records (
                collection_code,
                food_submission_id,
                verification_id,
                ngo_id,
                representative_id,
                collected_quantity,
                quantity_unit,
                collection_datetime,
                handover_confirmation,
                handover_notes,
                status
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                NOW(), 1, %s, 'COLLECTED'
            )
            """,
            (
                generate_collection_code(),
                match["food_submission_id"],
                verification["verification_id"],
                ngo_id,
                representative["representative_id"],
                verified_quantity,
                food["quantity_unit"],
                request.form.get("handover_notes", "").strip(),
            ),
        )

        mysql.connection.commit()

        flash(
            "Pickup confirmed successfully.",
            "success",
        )

        return _redirect_recovery()

    except ValueError as error:
        mysql.connection.rollback()
        flash(str(error), "warning")
        return _redirect_recovery()

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO pickup confirmation failed")

        flash(
            "Unable to confirm pickup. Check the server error log.",
            "danger",
        )

        return _redirect_recovery()

    finally:
        cursor.close()


# ============================================================
# CONFIRM DISTRIBUTION
# ============================================================

@ngo_bp.route(
    "/confirm-distribution/<int:match_id>",
    methods=["POST"],
)
@ngo_required
def confirm_distribution(match_id):
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        match = get_match_for_ngo(
            cursor,
            match_id,
            ngo_id,
        )

        if not match:
            raise ValueError("Recovery record not found.")

        cursor.execute(
            """
            SELECT *
            FROM collection_records
            WHERE food_submission_id = %s
              AND ngo_id = %s
              AND status = 'COLLECTED'
            ORDER BY collection_datetime DESC, collection_id DESC
            LIMIT 1
            FOR UPDATE
            """,
            (
                match["food_submission_id"],
                ngo_id,
            ),
        )

        collection = row_to_dict(cursor.fetchone(), cursor)

        if not collection:
            raise ValueError(
                "Confirm pickup before distribution."
            )

        verification = execute_one(
            cursor,
            """
            SELECT *
            FROM verification_records
            WHERE verification_id = %s
              AND match_id = %s
              AND ngo_id = %s
            LIMIT 1
            """,
            (
                collection["verification_id"],
                match_id,
                ngo_id,
            ),
        )

        if not verification_checks_passed(verification):
            raise ValueError(
                "Distribution requires a successful verification."
            )

        distribution_summary = execute_one(
            cursor,
            """
            SELECT COALESCE(SUM(distributed_quantity), 0)
                AS distributed_quantity
            FROM distribution_records
            WHERE collection_id = %s
              AND status IN (
                  'DISTRIBUTED',
                  'PARTIALLY_DISTRIBUTED'
              )
            """,
            (collection["collection_id"],),
        )

        already_distributed = Decimal(
            str(
                (distribution_summary or {}).get(
                    "distributed_quantity"
                ) or 0
            )
        )

        collected_quantity = Decimal(
            str(collection["collected_quantity"])
        )

        remaining_quantity = (
            collected_quantity - already_distributed
        )

        if remaining_quantity <= 0:
            raise ValueError(
                "The collected quantity has already been distributed."
            )

        distributed_quantity = parse_decimal(
            request.form.get("distributed_quantity", ""),
            "distributed quantity",
        )

        if (
            distributed_quantity <= 0
            or distributed_quantity > remaining_quantity
        ):
            raise ValueError(
                "Distributed quantity must be positive and cannot "
                "exceed the remaining collected quantity."
            )

        try:
            recipient_count = int(
                request.form.get("recipient_count", "").strip()
            )
        except (ValueError, TypeError):
            recipient_count = 0

        if recipient_count <= 0:
            raise ValueError("Enter a valid recipient count.")

        new_total_distributed = (
            already_distributed + distributed_quantity
        )

        distribution_status = (
            "DISTRIBUTED"
            if new_total_distributed == collected_quantity
            else "PARTIALLY_DISTRIBUTED"
        )

        cursor.execute(
            """
            INSERT INTO distribution_records (
                distribution_code,
                food_submission_id,
                collection_id,
                ngo_id,
                distributed_quantity,
                quantity_unit,
                distribution_datetime,
                recipient_count,
                distribution_notes,
                distribution_confirmation,
                status
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                NOW(), %s, %s, 1, %s
            )
            """,
            (
                generate_distribution_code(),
                match["food_submission_id"],
                collection["collection_id"],
                ngo_id,
                distributed_quantity,
                collection["quantity_unit"],
                recipient_count,
                request.form.get("distribution_notes", "").strip(),
                distribution_status,
            ),
        )

        if distribution_status == "DISTRIBUTED":
            cursor.execute(
                """
                UPDATE recovery_matches
                SET match_status = 'COMPLETED'
                WHERE match_id = %s
                  AND ngo_id = %s
                  AND match_status = 'ASSIGNED'
                """,
                (match_id, ngo_id),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    "Unable to complete the recovery."
                )

        # Update the shared food status only when all active allocations
        # have completed. Remaining, unallocated food stays available.
        totals = execute_one(
            cursor,
            """
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN match_status IN ('ASSIGNED', 'COMPLETED')
                        THEN accepted_quantity
                        ELSE 0
                    END
                ), 0) AS allocated_quantity,
                COALESCE(SUM(
                    CASE
                        WHEN match_status = 'COMPLETED'
                        THEN accepted_quantity
                        ELSE 0
                    END
                ), 0) AS completed_quantity
            FROM recovery_matches
            WHERE food_submission_id = %s
            """,
            (match["food_submission_id"],),
        ) or {}

        allocated = Decimal(
            str(totals.get("allocated_quantity") or 0)
        )

        completed = Decimal(
            str(totals.get("completed_quantity") or 0)
        )

        original_quantity = Decimal(str(match["quantity"]))

        if (
            allocated >= original_quantity
            and completed >= allocated
        ):
            cursor.execute(
                """
                UPDATE food_submissions
                SET status = 'DISTRIBUTED'
                WHERE food_submission_id = %s
                  AND status NOT IN (
                      'CANCELLED',
                      'EXPIRED',
                      'VERIFICATION_FAILED'
                  )
                """,
                (match["food_submission_id"],),
            )

        mysql.connection.commit()

        flash(
            "Distribution recorded successfully."
            if distribution_status == "DISTRIBUTED"
            else "Partial distribution recorded successfully.",
            "success",
        )

        return _redirect_recovery()

    except ValueError as error:
        mysql.connection.rollback()
        flash(str(error), "warning")
        return _redirect_recovery()

    except Exception:
        mysql.connection.rollback()
        logger.exception("NGO distribution confirmation failed")

        flash(
            "Unable to record distribution. Check the server error log.",
            "danger",
        )

        return _redirect_recovery()

    finally:
        cursor.close()


# ============================================================
# RECOVERY MANAGEMENT
# ============================================================

@ngo_bp.route("/recovery-management")
@ngo_required
def recovery_management():
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        recoveries = execute_all(
            cursor,
            """
            SELECT
                rm.*,
                fs.recovery_id,
                fs.donor_id,
                fs.food_type,
                fs.quantity,
                fs.quantity_unit,
                fs.preparation_date,
                fs.preparation_time,
                fs.served_to_customers,
                fs.handling_information,
                fs.storage_handling_information,
                fs.applicable_consumption_date,
                fs.applicable_consumption_time,
                fs.available_from,
                fs.available_until,
                fs.donor_notes,
                fs.status AS food_status
            FROM recovery_matches rm
            INNER JOIN food_submissions fs
                ON fs.food_submission_id = rm.food_submission_id
            WHERE rm.ngo_id = %s
              AND rm.match_status IN (
                  'ASSIGNED',
                  'COMPLETED',
                  'FAILED',
                  'CANCELLED'
              )
            ORDER BY
                CASE
                    WHEN rm.match_status = 'ASSIGNED' THEN 0
                    WHEN rm.match_status = 'COMPLETED' THEN 1
                    ELSE 2
                END,
                rm.created_at DESC,
                rm.match_id DESC
            """,
            (ngo_id,),
        )

        for recovery in recoveries:
            match_id = recovery["match_id"]

            verification = get_latest_verification(
                cursor,
                match_id,
            )

            recovery["verification"] = verification

            recovery["verification_passed"] = (
                verification_checks_passed(verification)
            )

            collection = None

            if verification:
                collection = execute_one(
                    cursor,
                    """
                    SELECT *
                    FROM collection_records
                    WHERE verification_id = %s
                      AND ngo_id = %s
                      AND status = 'COLLECTED'
                    ORDER BY collection_id DESC
                    LIMIT 1
                    """,
                    (
                        verification["verification_id"],
                        ngo_id,
                    ),
                )

            recovery["collection"] = collection

            distribution = execute_one(
                cursor,
                """
                SELECT COALESCE(SUM(distributed_quantity), 0)
                    AS distributed_quantity
                FROM distribution_records
                WHERE collection_id = %s
                  AND ngo_id = %s
                  AND status IN (
                      'DISTRIBUTED',
                      'PARTIALLY_DISTRIBUTED'
                  )
                """,
                (
                    collection["collection_id"] if collection else 0,
                    ngo_id,
                ),
            ) or {}

            recovery["distributed_quantity"] = (
                distribution.get("distributed_quantity") or 0
            )

            recovery["status"] = recovery.get("food_status")

            if collection:
                collected = Decimal(
                    str(collection.get("collected_quantity") or 0)
                )

                distributed = Decimal(
                    str(recovery["distributed_quantity"])
                )

                recovery["quantity_remaining"] = max(
                    Decimal("0"),
                    collected - distributed,
                )
            else:
                recovery["quantity_remaining"] = Decimal("0")

        return render_template(
            "recovery_management.html",
            recovery_records=recoveries,
            recoveries=recoveries,
            matches=recoveries,
        )

    except Exception:
        logger.exception("NGO recovery management failed")

        flash(
            "Unable to load Recovery Management. Check the server error log.",
            "danger",
        )

        return render_template(
            "recovery_management.html",
            recovery_records=[],
            recoveries=[],
            matches=[],
        )

    finally:
        cursor.close()


# ============================================================
# BATCH VERIFICATIONS
# ============================================================

@ngo_bp.route("/batch-verifications")
@ngo_required
def batch_verifications():
    return redirect(url_for("ngo.recovery_management"))


# ============================================================
# NOTIFICATIONS
# ============================================================

@ngo_bp.route("/notifications")
@ngo_required
def notifications():
    return redirect(url_for("ngo.dashboard"))


# ============================================================
# NGO PROFILE
# ============================================================

@ngo_bp.route("/profile")
@ngo_required
def profile():
    ngo_id = session["ngo_id"]
    cursor = get_cursor()

    try:
        ngo = execute_one(
            cursor,
            """
            SELECT
                na.ngo_id,
                na.ngo_code,
                na.username,
                na.account_status,
                na.activated_at,
                na.last_login_at,
                na.created_at AS account_created_at,
                app.ngo_application_id,
                app.application_code,
                app.ngo_name,
                app.registered_address,
                app.city,
                app.state,
                app.postal_code,
                app.authorized_representative_name,
                app.phone,
                app.email,
                app.registration_number,
                app.registration_date,
                app.organization_description,
                app.application_status,
                app.admin_review_notes,
                app.correction_message,
                app.submitted_at,
                app.reviewed_at
            FROM ngo_accounts na
            INNER JOIN ngo_applications app
                ON app.ngo_application_id = na.ngo_application_id
            WHERE na.ngo_id = %s
            LIMIT 1
            """,
            (ngo_id,),
        )

        if not ngo:
            flash("NGO profile not found.", "warning")
            return redirect(url_for("ngo.dashboard"))

        return render_template(
            "ngo_profile.html",
            ngo=ngo,
            profile=ngo,
        )

    except Exception:
        logger.exception("NGO profile loading failed")

        flash(
            "Unable to load the NGO profile.",
            "danger",
        )

        return redirect(url_for("ngo.dashboard"))

    finally:
        cursor.close()