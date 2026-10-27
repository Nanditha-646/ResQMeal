from functools import wraps
import secrets

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    session,
    request,
    flash,
    send_from_directory
)

from werkzeug.security import generate_password_hash

from app.db import mysql

import os


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("auth.admin_login"))
        return view_function(*args, **kwargs)

    return wrapped_view


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    return render_template(
        "admin_dashboard.html",
        admin_username=session.get("admin_username"),
        admin_code=session.get("admin_code")
    )


# ============================================================
# DONOR APPLICATION MANAGEMENT
# ============================================================

@admin_bp.route("/applications")
@admin_required
def applications():
    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                donor_application_id,
                application_code,
                business_name,
                business_type,
                owner,
                phone,
                email,
                city,
                event_name,
                event_type,
                event_date,
                application_status,
                submitted_at,
                reviewed_at
            FROM donor_applications
            ORDER BY submitted_at DESC
        """)

        applications = cursor.fetchall()

        return render_template(
            "admin_applications.html",
            applications=applications
        )

    except Exception as error:
        return f"Unable to load applications: {error}"

    finally:
        if cursor:
            cursor.close()


@admin_bp.route("/applications/<int:application_id>")
@admin_required
def application_details(application_id):
    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                donor_application_id,
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
                event_name,
                event_type,
                event_date,
                application_status,
                admin_review_notes,
                correction_message,
                submitted_at,
                reviewed_at
            FROM donor_applications
            WHERE donor_application_id = %s
            LIMIT 1
        """, (application_id,))

        application = cursor.fetchone()

        if not application:
            flash("Application not found.", "error")
            return redirect(url_for("admin.applications"))

        return render_template(
            "admin_application_details.html",
            application=application
        )

    except Exception as error:
        return f"Unable to load application details: {error}"

    finally:
        if cursor:
            cursor.close()


def generate_internal_username(application_code):
    base_username = "donor_" + application_code.lower().replace("-", "_")

    cursor = None

    try:
        cursor = mysql.connection.cursor()

        for number in range(20):
            candidate = (
                base_username
                if number == 0
                else f"{base_username}_{number}"
            )

            cursor.execute("""
                SELECT donor_id
                FROM donor_accounts
                WHERE username = %s
                LIMIT 1
            """, (candidate,))

            if not cursor.fetchone():
                return candidate

        raise Exception(
            "Unable to generate a unique internal donor username."
        )

    finally:
        if cursor:
            cursor.close()


def create_pending_donor_account(cursor, application):
    application_id = application["donor_application_id"]
    application_code = application["application_code"]

    cursor.execute("""
        SELECT
            donor_id,
            donor_code,
            username,
            account_status
        FROM donor_accounts
        WHERE donor_application_id = %s
        LIMIT 1
    """, (application_id,))

    existing_account = cursor.fetchone()

    if existing_account:
        return existing_account

    donor_code = None

    for _ in range(20):
        candidate = "DR-" + secrets.token_hex(4).upper()

        cursor.execute("""
            SELECT donor_id
            FROM donor_accounts
            WHERE donor_code = %s
            LIMIT 1
        """, (candidate,))

        if not cursor.fetchone():
            donor_code = candidate
            break

    if not donor_code:
        raise Exception("Unable to generate a unique donor code.")

    username = None
    base_username = "donor_" + application_code.lower().replace("-", "_")

    for number in range(20):
        candidate = (
            base_username
            if number == 0
            else f"{base_username}_{number}"
        )

        cursor.execute("""
            SELECT donor_id
            FROM donor_accounts
            WHERE username = %s
            LIMIT 1
        """, (candidate,))

        if not cursor.fetchone():
            username = candidate
            break

    if not username:
        raise Exception("Unable to generate a unique donor username.")

    random_secret = secrets.token_urlsafe(32)
    password_hash = generate_password_hash(random_secret)

    cursor.execute("""
        INSERT INTO donor_accounts (
            donor_code,
            donor_application_id,
            username,
            password_hash,
            account_status,
            activated_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            'PENDING',
            NULL
        )
    """, (
        donor_code,
        application_id,
        username,
        password_hash
    ))

    cursor.execute("""
        SELECT
            donor_id,
            donor_code,
            username,
            account_status
        FROM donor_accounts
        WHERE donor_application_id = %s
        LIMIT 1
    """, (application_id,))

    account = cursor.fetchone()

    if not account:
        raise Exception("Donor account was not created.")

    return account


# ============================================================
# NGO ACCOUNT CREATION
# ============================================================

def create_pending_ngo_account(cursor, application):
    """
    Create one pending NGO account after all four mandatory
    NGO documents have been verified.

    The account starts in PENDING status.
    The NGO will activate the account later and create
    its permanent password.
    """

    application_id = application["ngo_application_id"]
    application_code = application["application_code"]

    # --------------------------------------------------------
    # CHECK WHETHER AN ACCOUNT ALREADY EXISTS
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            ngo_id,
            ngo_code,
            username,
            account_status
        FROM ngo_accounts
        WHERE ngo_application_id = %s
        LIMIT 1
    """, (application_id,))

    existing_account = cursor.fetchone()

    if existing_account:
        return existing_account

    # --------------------------------------------------------
    # GENERATE UNIQUE NGO CODE
    # Example: NG-A82F91C4
    # --------------------------------------------------------

    ngo_code = None

    for _ in range(20):

        candidate = "NG-" + secrets.token_hex(4).upper()

        cursor.execute("""
            SELECT ngo_id
            FROM ngo_accounts
            WHERE ngo_code = %s
            LIMIT 1
        """, (candidate,))

        if not cursor.fetchone():
            ngo_code = candidate
            break

    if not ngo_code:
        raise Exception(
            "Unable to generate a unique NGO code."
        )

    # --------------------------------------------------------
    # GENERATE UNIQUE INTERNAL USERNAME
    # --------------------------------------------------------

    base_username = (
        "ngo_"
        + application_code.lower().replace("-", "_")
    )

    username = None

    for number in range(20):

        candidate = (
            base_username
            if number == 0
            else f"{base_username}_{number}"
        )

        cursor.execute("""
            SELECT ngo_id
            FROM ngo_accounts
            WHERE username = %s
            LIMIT 1
        """, (candidate,))

        if not cursor.fetchone():
            username = candidate
            break

    if not username:
        raise Exception(
            "Unable to generate a unique NGO username."
        )

    # --------------------------------------------------------
    # CREATE INITIAL RANDOM SECRET
    #
    # The random value is never shown to the NGO.
    # The account remains PENDING until the NGO activation
    # flow is implemented.
    # --------------------------------------------------------

    random_secret = secrets.token_urlsafe(32)

    password_hash = generate_password_hash(
        random_secret
    )

    # --------------------------------------------------------
    # INSERT NGO ACCOUNT
    # --------------------------------------------------------

    cursor.execute("""
        INSERT INTO ngo_accounts (
            ngo_code,
            ngo_application_id,
            username,
            password_hash,
            account_status,
            activated_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            'PENDING',
            NULL
        )
    """, (
        ngo_code,
        application_id,
        username,
        password_hash
    ))

    # --------------------------------------------------------
    # VERIFY ACCOUNT CREATION
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            ngo_id,
            ngo_code,
            username,
            account_status
        FROM ngo_accounts
        WHERE ngo_application_id = %s
        LIMIT 1
    """, (application_id,))

    account = cursor.fetchone()

    if not account:
        raise Exception(
            "NGO account was not created."
        )

    return account


# ============================================================
# DONOR APPROVAL
# ============================================================

@admin_bp.route(
    "/applications/<int:application_id>/approve",
    methods=["POST"]
)
@admin_required
def approve_application(application_id):
    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                donor_application_id,
                application_code,
                business_name,
                application_status
            FROM donor_applications
            WHERE donor_application_id = %s
            LIMIT 1
        """, (application_id,))

        application = cursor.fetchone()

        if not application:
            flash("Application not found.", "error")
            return redirect(url_for("admin.applications"))

        cursor.execute("""
            SELECT
                donor_id,
                donor_code,
                username,
                account_status
            FROM donor_accounts
            WHERE donor_application_id = %s
            LIMIT 1
        """, (application_id,))

        existing_account = cursor.fetchone()

        if application["application_status"] == "APPROVED":

            if existing_account:
                flash(
                    "This application is already approved and its donor account already exists.",
                    "error"
                )
            else:
                create_pending_donor_account(
                    cursor,
                    application
                )

                mysql.connection.commit()

                flash(
                    "Donor account created successfully. "
                    "The donor can now activate the account using their "
                    "registered mobile number and create a permanent password.",
                    "success"
                )

            return redirect(
                url_for(
                    "admin.application_details",
                    application_id=application_id
                )
            )

        if existing_account:
            flash(
                "A donor account already exists for this application.",
                "error"
            )

            return redirect(
                url_for(
                    "admin.application_details",
                    application_id=application_id
                )
            )

        create_pending_donor_account(
            cursor,
            application
        )

        cursor.execute("""
            UPDATE donor_applications
            SET
                application_status = 'APPROVED',
                admin_review_notes = %s,
                correction_message = NULL,
                reviewed_by_admin_id = %s,
                reviewed_at = NOW()
            WHERE donor_application_id = %s
        """, (
            "Application approved by Admin.",
            session.get("admin_id"),
            application_id
        ))

        mysql.connection.commit()

        flash(
            "Application approved successfully. "
            "Donor account created with status PENDING. "
            "The donor can activate the account using their "
            "registered mobile number and create a permanent password.",
            "success"
        )

        return redirect(
            url_for(
                "admin.application_details",
                application_id=application_id
            )
        )

    except Exception as error:

        if mysql.connection:
            mysql.connection.rollback()

        flash(
            f"Unable to approve application: {error}",
            "error"
        )

        return redirect(
            url_for(
                "admin.application_details",
                application_id=application_id
            )
        )

    finally:
        if cursor:
            cursor.close()


# ============================================================
# DONOR REJECTION
# ============================================================

@admin_bp.route(
    "/applications/<int:application_id>/reject",
    methods=["POST"]
)
@admin_required
def reject_application(application_id):
    cursor = None

    try:
        reason = request.form.get(
            "review_notes",
            ""
        ).strip()

        if not reason:
            flash(
                "Please provide a reason before rejecting the application.",
                "error"
            )

            return redirect(
                url_for(
                    "admin.application_details",
                    application_id=application_id
                )
            )

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                donor_application_id,
                application_status
            FROM donor_applications
            WHERE donor_application_id = %s
            LIMIT 1
        """, (application_id,))

        application = cursor.fetchone()

        if not application:
            flash("Application not found.", "error")
            return redirect(url_for("admin.applications"))

        cursor.execute("""
            UPDATE donor_applications
            SET
                application_status = 'REJECTED',
                admin_review_notes = %s,
                correction_message = NULL,
                reviewed_by_admin_id = %s,
                reviewed_at = NOW()
            WHERE donor_application_id = %s
        """, (
            reason,
            session.get("admin_id"),
            application_id
        ))

        mysql.connection.commit()

        flash(
            "Application rejected successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin.application_details",
                application_id=application_id
            )
        )

    except Exception as error:

        if mysql.connection:
            mysql.connection.rollback()

        flash(
            f"Unable to reject application: {error}",
            "error"
        )

        return redirect(
            url_for(
                "admin.application_details",
                application_id=application_id
            )
        )

    finally:
        if cursor:
            cursor.close()


# ============================================================
# DONOR CORRECTION REQUEST
# ============================================================

@admin_bp.route(
    "/applications/<int:application_id>/correction",
    methods=["POST"]
)
@admin_required
def request_correction(application_id):
    cursor = None

    try:
        correction_message = request.form.get(
            "correction_message",
            ""
        ).strip()

        if not correction_message:
            flash(
                "Please provide the correction message.",
                "error"
            )

            return redirect(
                url_for(
                    "admin.application_details",
                    application_id=application_id
                )
            )

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                donor_application_id,
                application_status
            FROM donor_applications
            WHERE donor_application_id = %s
            LIMIT 1
        """, (application_id,))

        application = cursor.fetchone()

        if not application:
            flash("Application not found.", "error")
            return redirect(url_for("admin.applications"))

        cursor.execute("""
            UPDATE donor_applications
            SET
                application_status = 'CORRECTION_REQUIRED',
                correction_message = %s,
                admin_review_notes = %s,
                reviewed_by_admin_id = %s,
                reviewed_at = NOW()
            WHERE donor_application_id = %s
        """, (
            correction_message,
            "Correction requested by Admin.",
            session.get("admin_id"),
            application_id
        ))

        mysql.connection.commit()

        flash(
            "Correction request sent successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin.application_details",
                application_id=application_id
            )
        )

    except Exception as error:

        if mysql.connection:
            mysql.connection.rollback()

        flash(
            f"Unable to request correction: {error}",
            "error"
        )

        return redirect(
            url_for(
                "admin.application_details",
                application_id=application_id
            )
        )

    finally:
        if cursor:
            cursor.close()


# ============================================================
# NGO APPLICATION MANAGEMENT
# ============================================================

@admin_bp.route("/ngo-applications")
@admin_required
def ngo_applications():
    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                ngo_application_id,
                application_code,
                ngo_name,
                authorized_representative_name,
                phone,
                email,
                city,
                state,
                application_status,
                submitted_at,
                reviewed_at
            FROM ngo_applications
            ORDER BY submitted_at DESC
        """)

        applications = cursor.fetchall()

        return render_template(
            "admin_ngo_applications.html",
            applications=applications
        )

    except Exception as error:
        return f"Unable to load NGO applications: {error}"

    finally:
        if cursor:
            cursor.close()


@admin_bp.route("/ngo-applications/<int:application_id>")
@admin_required
def ngo_application_details(application_id):
    cursor = None

    try:
        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                ngo_application_id,
                application_code,
                ngo_name,
                registered_address,
                city,
                state,
                postal_code,
                authorized_representative_name,
                phone,
                email,
                registration_number,
                registration_date,
                organization_description,
                application_status,
                admin_review_notes,
                correction_message,
                reviewed_by_admin_id,
                submitted_at,
                reviewed_at
            FROM ngo_applications
            WHERE ngo_application_id = %s
            LIMIT 1
        """, (application_id,))

        application = cursor.fetchone()

        if not application:
            flash(
                "NGO application not found.",
                "error"
            )

            return redirect(
                url_for("admin.ngo_applications")
            )

        cursor.execute("""
            SELECT
                ngo_document_id,
                ngo_application_id,
                document_type,
                document_number,
                original_filename,
                file_path,
                verification_status,
                admin_notes,
                verified_by_admin_id,
                verified_at,
                uploaded_at
            FROM ngo_documents
            WHERE ngo_application_id = %s
            ORDER BY ngo_document_id ASC
        """, (application_id,))

        documents = cursor.fetchall()

        return render_template(
            "admin_ngo_application_details.html",
            application=application,
            documents=documents
        )

    except Exception as error:
        return f"Unable to load NGO application details: {error}"

    finally:
        if cursor:
            cursor.close()


# ============================================================
# NGO DOCUMENT VERIFICATION
# ============================================================

@admin_bp.route(
    "/ngo-documents/<int:document_id>/verify",
    methods=["POST"]
)
@admin_required
def verify_ngo_document(document_id):

    status = request.form.get(
        "verification_status",
        ""
    ).strip().upper()

    admin_notes = request.form.get(
        "admin_notes",
        ""
    ).strip()

    allowed_statuses = {
        "VERIFIED",
        "CORRECTION_REQUIRED",
        "REJECTED"
    }

    if status not in allowed_statuses:
        flash(
            "Invalid document verification status.",
            "error"
        )

        return redirect(
            url_for("admin.ngo_applications")
        )

    if (
        status in {
            "CORRECTION_REQUIRED",
            "REJECTED"
        }
        and not admin_notes
    ):
        flash(
            "Please provide notes or a reason for this decision.",
            "error"
        )

        return redirect(
            url_for("admin.ngo_applications")
        )

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        # ----------------------------------------------------
        # FIND DOCUMENT
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                ngo_document_id,
                ngo_application_id,
                document_type
            FROM ngo_documents
            WHERE ngo_document_id = %s
            LIMIT 1
        """, (document_id,))

        document = cursor.fetchone()

        if not document:

            flash(
                "NGO document not found.",
                "error"
            )

            return redirect(
                url_for("admin.ngo_applications")
            )

        # ----------------------------------------------------
        # UPDATE DOCUMENT VERIFICATION
        # ----------------------------------------------------

        cursor.execute("""
            UPDATE ngo_documents
            SET
                verification_status = %s,
                admin_notes = %s,
                verified_by_admin_id = %s,
                verified_at = NOW()
            WHERE ngo_document_id = %s
        """, (
            status,
            admin_notes or None,
            session.get("admin_id"),
            document_id
        ))

        # ----------------------------------------------------
        # DETERMINE OVERALL NGO APPLICATION STATUS
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS total_documents,

                SUM(
                    CASE
                        WHEN verification_status = 'VERIFIED'
                        THEN 1
                        ELSE 0
                    END
                ) AS verified_documents,

                SUM(
                    CASE
                        WHEN verification_status = 'REJECTED'
                        THEN 1
                        ELSE 0
                    END
                ) AS rejected_documents,

                SUM(
                    CASE
                        WHEN verification_status = 'CORRECTION_REQUIRED'
                        THEN 1
                        ELSE 0
                    END
                ) AS correction_documents

            FROM ngo_documents

            WHERE ngo_application_id = %s
        """, (
            document["ngo_application_id"],
        ))

        summary = cursor.fetchone()

        total_documents = (
            summary["total_documents"]
            or 0
        )

        verified_documents = (
            summary["verified_documents"]
            or 0
        )

        rejected_documents = (
            summary["rejected_documents"]
            or 0
        )

        correction_documents = (
            summary["correction_documents"]
            or 0
        )

        new_application_status = "DOCUMENT_REVIEW"

        application_notes = None

        correction_message = None

        # ----------------------------------------------------
        # REJECTED HAS HIGHEST PRIORITY
        # ----------------------------------------------------

        if rejected_documents > 0:

            new_application_status = "REJECTED"

            application_notes = (
                "One or more NGO documents were rejected by Admin."
            )

        # ----------------------------------------------------
        # CORRECTION HAS SECOND PRIORITY
        # ----------------------------------------------------

        elif correction_documents > 0:

            new_application_status = "CORRECTION_REQUIRED"

            correction_message = (
                "One or more NGO documents require correction."
            )

            application_notes = (
                "Admin requested correction for one or more NGO documents."
            )

        # ----------------------------------------------------
        # ALL FOUR DOCUMENTS VERIFIED
        # ----------------------------------------------------

        elif (
            total_documents == 4
            and verified_documents == 4
        ):

            new_application_status = "VERIFIED"

            application_notes = (
                "All four mandatory NGO documents verified by Admin."
            )

        # ----------------------------------------------------
        # UPDATE NGO APPLICATION
        # ----------------------------------------------------

        cursor.execute("""
            UPDATE ngo_applications
            SET
                application_status = %s,
                admin_review_notes = %s,
                correction_message = %s,
                reviewed_by_admin_id = %s,
                reviewed_at = NOW()
            WHERE ngo_application_id = %s
        """, (
            new_application_status,
            application_notes,
            correction_message,
            session.get("admin_id"),
            document["ngo_application_id"]
        ))

        # ----------------------------------------------------
        # CREATE NGO ACCOUNT ONLY AFTER ALL FOUR DOCUMENTS
        # ARE VERIFIED
        # ----------------------------------------------------

        ngo_account_created = False

        if new_application_status == "VERIFIED":

            cursor.execute("""
                SELECT
                    ngo_application_id,
                    application_code
                FROM ngo_applications
                WHERE ngo_application_id = %s
                LIMIT 1
            """, (
                document["ngo_application_id"],
            ))

            verified_application = cursor.fetchone()

            if not verified_application:
                raise Exception(
                    "Verified NGO application could not be found."
                )

            existing_ngo_account = None

            cursor.execute("""
                SELECT
                    ngo_id,
                    ngo_code,
                    username,
                    account_status
                FROM ngo_accounts
                WHERE ngo_application_id = %s
                LIMIT 1
            """, (
                document["ngo_application_id"],
            ))

            existing_ngo_account = cursor.fetchone()

            if not existing_ngo_account:

                create_pending_ngo_account(
                    cursor,
                    verified_application
                )

                ngo_account_created = True

        # ----------------------------------------------------
        # COMMIT EVERYTHING TOGETHER
        # ----------------------------------------------------

        mysql.connection.commit()

        # ----------------------------------------------------
        # SUCCESS MESSAGE
        # ----------------------------------------------------

        if new_application_status == "VERIFIED":

            if ngo_account_created:

                flash(
                    "Document verified successfully. "
                    "All four mandatory NGO documents are verified. "
                    "A pending NGO account has been created.",
                    "success"
                )

            else:

                flash(
                    "Document verified successfully. "
                    "All four mandatory NGO documents are already verified "
                    "and the NGO account already exists.",
                    "success"
                )

        else:

            flash(
                (
                    "Document marked as "
                    f"{status.replace('_', ' ')} successfully."
                ),
                "success"
            )

        return redirect(
            url_for(
                "admin.ngo_application_details",
                application_id=document["ngo_application_id"]
            )
        )

    except Exception as error:

        if mysql.connection:
            mysql.connection.rollback()

        flash(
            f"Unable to verify NGO document: {error}",
            "error"
        )

        return redirect(
            url_for("admin.ngo_applications")
        )

    finally:

        if cursor:
            cursor.close()


# ============================================================
# VIEW NGO DOCUMENT
# ============================================================

@admin_bp.route(
    "/ngo-documents/<int:document_id>/view"
)
@admin_required
def view_ngo_document(document_id):

    cursor = None

    try:

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT
                ngo_document_id,
                original_filename,
                file_path
            FROM ngo_documents
            WHERE ngo_document_id = %s
            LIMIT 1
        """, (document_id,))

        document = cursor.fetchone()

        if not document:

            flash(
                "Document not found.",
                "error"
            )

            return redirect(
                url_for("admin.ngo_applications")
            )

        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                ".."
            )
        )

        uploads_root = os.path.join(
            project_root,
            "uploads",
            "ngo_documents"
        )

        relative_path = (
            document["file_path"]
            .replace("\\", "/")
        )

        path_parts = relative_path.split("/")

        if len(path_parts) < 2:

            flash(
                "Invalid document path.",
                "error"
            )

            return redirect(
                url_for("admin.ngo_applications")
            )

        application_folder = path_parts[0]

        filename = path_parts[-1]

        return send_from_directory(
            os.path.join(
                uploads_root,
                application_folder
            ),
            filename,
            as_attachment=False
        )

    except Exception as error:

        flash(
            f"Unable to open document: {error}",
            "error"
        )

        return redirect(
            url_for("admin.ngo_applications")
        )

    finally:

        if cursor:
            cursor.close()


# ============================================================
# ADMIN LOGOUT
# ============================================================

@admin_bp.route("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("auth.admin_login")
    )