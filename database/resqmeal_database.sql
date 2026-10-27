-- ============================================================
-- RESQMEAL DATABASE
-- AI-Assisted Surplus Food Recovery & Redistribution System
-- ============================================================

CREATE DATABASE IF NOT EXISTS resqmeal_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_ai_ci;

USE resqmeal_db;


-- ============================================================
-- 1. ADMIN ACCOUNTS
-- ============================================================

CREATE TABLE admin_accounts (
    admin_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    admin_code VARCHAR(20) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    phone VARCHAR(20),
    status ENUM('ACTIVE', 'SUSPENDED') NOT NULL DEFAULT 'ACTIVE',
    two_factor_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- ============================================================
-- 2. ADMIN OTP / TWO-STEP VERIFICATION
-- ============================================================

CREATE TABLE admin_otp_verifications (
    otp_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    admin_id BIGINT UNSIGNED NOT NULL,
    otp_code_hash VARCHAR(255) NOT NULL,

    purpose ENUM(
        'LOGIN',
        'OTHER'
    ) NOT NULL DEFAULT 'LOGIN',

    expires_at DATETIME NOT NULL,
    verified_at DATETIME NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,

    status ENUM(
        'PENDING',
        'VERIFIED',
        'EXPIRED',
        'FAILED'
    ) NOT NULL DEFAULT 'PENDING',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_otp_admin
        FOREIGN KEY (admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 3. HOTEL / RESTAURANT DONOR APPLICATIONS
-- ============================================================

CREATE TABLE donor_applications (
    donor_application_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    application_code VARCHAR(30) NOT NULL UNIQUE,

    business_name VARCHAR(200) NOT NULL,

    business_type ENUM(
        'HOTEL',
        'RESTAURANT'
    ) NOT NULL,

    owner_authorized_name VARCHAR(150) NOT NULL,

    phone VARCHAR(20) NOT NULL,

    email VARCHAR(150) NOT NULL,

    address TEXT NOT NULL,

    city VARCHAR(100) NOT NULL,

    state VARCHAR(100) NOT NULL,

    postal_code VARCHAR(10),

    year_established YEAR,

    food_service_since_year YEAR,

    application_status ENUM(
        'APPLICATION_SUBMITTED',
        'DOCUMENT_REVIEW',
        'CORRECTION_REQUIRED',
        'VERIFIED',
        'ACTIVE_DONOR',
        'REJECTED',
        'SUSPENDED'
    ) NOT NULL DEFAULT 'APPLICATION_SUBMITTED',

    admin_review_notes TEXT NULL,

    correction_message TEXT NULL,

    reviewed_by_admin_id BIGINT UNSIGNED NULL,

    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    reviewed_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_donor_application_admin
        FOREIGN KEY (reviewed_by_admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 4. HOTEL / RESTAURANT DONOR DOCUMENTS
-- ============================================================

CREATE TABLE donor_documents (
    donor_document_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    donor_application_id BIGINT UNSIGNED NOT NULL,

    document_type ENUM(
        'BUSINESS_EXISTENCE',
        'PREMISES_PROOF',
        'FSSAI_LICENSE_REGISTRATION',
        'OTHER'
    ) NOT NULL,

    document_number VARCHAR(150) NULL,

    original_filename VARCHAR(255) NOT NULL,

    file_path VARCHAR(500) NOT NULL,

    verification_status ENUM(
        'PENDING',
        'VERIFIED',
        'CORRECTION_REQUIRED',
        'REJECTED'
    ) NOT NULL DEFAULT 'PENDING',

    admin_notes TEXT NULL,

    verified_by_admin_id BIGINT UNSIGNED NULL,

    verified_at DATETIME NULL,

    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_donor_document_application
        FOREIGN KEY (donor_application_id)
        REFERENCES donor_applications(donor_application_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_donor_document_admin
        FOREIGN KEY (verified_by_admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 5. HOTEL / RESTAURANT PHOTOS
-- ============================================================

CREATE TABLE donor_photos (
    donor_photo_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    donor_application_id BIGINT UNSIGNED NOT NULL,

    photo_type ENUM(
        'EXTERIOR',
        'BUSINESS_SIGNAGE',
        'PREMISES',
        'FOOD_SERVICE_AREA',
        'OTHER'
    ) NOT NULL,

    file_path VARCHAR(500) NOT NULL,

    verification_status ENUM(
        'PENDING',
        'VERIFIED',
        'CORRECTION_REQUIRED',
        'REJECTED'
    ) NOT NULL DEFAULT 'PENDING',

    admin_notes TEXT NULL,

    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_donor_photo_application
        FOREIGN KEY (donor_application_id)
        REFERENCES donor_applications(donor_application_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 6. ACTIVE DONOR ACCOUNTS
-- ============================================================

CREATE TABLE donor_accounts (
    donor_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    donor_code VARCHAR(30) NOT NULL UNIQUE,

    donor_application_id BIGINT UNSIGNED NOT NULL UNIQUE,

    username VARCHAR(100) NOT NULL UNIQUE,

    password_hash VARCHAR(255) NOT NULL,

    account_status ENUM(
        'PENDING',
        'ACTIVE',
        'SUSPENDED',
        'DISABLED'
    ) NOT NULL DEFAULT 'PENDING',

    activated_at DATETIME NULL,

    last_login_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_donor_account_application
        FOREIGN KEY (donor_application_id)
        REFERENCES donor_applications(donor_application_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 7. NGO APPLICATIONS
-- ============================================================

CREATE TABLE ngo_applications (
    ngo_application_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    application_code VARCHAR(30) NOT NULL UNIQUE,

    ngo_name VARCHAR(200) NOT NULL,

    registered_address TEXT NOT NULL,

    city VARCHAR(100) NOT NULL,

    state VARCHAR(100) NOT NULL,

    postal_code VARCHAR(10),

    authorized_representative_name VARCHAR(150) NOT NULL,

    phone VARCHAR(20) NOT NULL,

    email VARCHAR(150) NOT NULL,

    registration_number VARCHAR(150),

    registration_date DATE NULL,

    organization_description TEXT NULL,

    application_status ENUM(
        'APPLICATION_SUBMITTED',
        'DOCUMENT_REVIEW',
        'CORRECTION_REQUIRED',
        'VERIFIED',
        'ACTIVE_NGO',
        'REJECTED',
        'SUSPENDED'
    ) NOT NULL DEFAULT 'APPLICATION_SUBMITTED',

    admin_review_notes TEXT NULL,

    correction_message TEXT NULL,

    reviewed_by_admin_id BIGINT UNSIGNED NULL,

    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    reviewed_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_ngo_application_admin
        FOREIGN KEY (reviewed_by_admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 8. NGO DOCUMENTS
-- ============================================================

CREATE TABLE ngo_documents (
    ngo_document_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    ngo_application_id BIGINT UNSIGNED NOT NULL,

    document_type ENUM(
        'REGISTRATION_CERTIFICATE',
        'AUTHORIZATION_PROOF',
        'IDENTITY_PROOF',
        'OTHER'
    ) NOT NULL,

    document_number VARCHAR(150) NULL,

    original_filename VARCHAR(255) NOT NULL,

    file_path VARCHAR(500) NOT NULL,

    verification_status ENUM(
        'PENDING',
        'VERIFIED',
        'CORRECTION_REQUIRED',
        'REJECTED'
    ) NOT NULL DEFAULT 'PENDING',

    admin_notes TEXT NULL,

    verified_by_admin_id BIGINT UNSIGNED NULL,

    verified_at DATETIME NULL,

    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ngo_document_application
        FOREIGN KEY (ngo_application_id)
        REFERENCES ngo_applications(ngo_application_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ngo_document_admin
        FOREIGN KEY (verified_by_admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 9. NGO ACCOUNTS
-- ============================================================

CREATE TABLE ngo_accounts (
    ngo_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    ngo_code VARCHAR(30) NOT NULL UNIQUE,

    ngo_application_id BIGINT UNSIGNED NOT NULL UNIQUE,

    username VARCHAR(100) NOT NULL UNIQUE,

    password_hash VARCHAR(255) NOT NULL,

    account_status ENUM(
        'PENDING',
        'ACTIVE',
        'SUSPENDED',
        'DISABLED'
    ) NOT NULL DEFAULT 'PENDING',

    activated_at DATETIME NULL,

    last_login_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_ngo_account_application
        FOREIGN KEY (ngo_application_id)
        REFERENCES ngo_applications(ngo_application_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 10. NGO REPRESENTATIVES
-- ============================================================

CREATE TABLE ngo_representatives (
    representative_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    representative_code VARCHAR(30) NOT NULL UNIQUE,

    ngo_id BIGINT UNSIGNED NOT NULL,

    full_name VARCHAR(150) NOT NULL,

    phone VARCHAR(20) NOT NULL,

    email VARCHAR(150),

    representative_status ENUM(
        'ACTIVE',
        'INACTIVE'
    ) NOT NULL DEFAULT 'ACTIVE',

    authorized_from DATE NULL,

    authorized_until DATE NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_representative_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 11. NGO REPRESENTATIVE DOCUMENTS
-- ============================================================

CREATE TABLE ngo_representative_documents (
    representative_document_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    representative_id BIGINT UNSIGNED NOT NULL,

    document_type VARCHAR(100) NOT NULL,

    document_number VARCHAR(150),

    original_filename VARCHAR(255),

    file_path VARCHAR(500),

    verification_status ENUM(
        'PENDING',
        'VERIFIED',
        'REJECTED'
    ) NOT NULL DEFAULT 'PENDING',

    verified_by_admin_id BIGINT UNSIGNED NULL,

    verified_at DATETIME NULL,

    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_representative_document
        FOREIGN KEY (representative_id)
        REFERENCES ngo_representatives(representative_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_representative_document_admin
        FOREIGN KEY (verified_by_admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 12. NGO RECOVERY REQUIREMENTS
-- ============================================================

CREATE TABLE ngo_recovery_requirements (
    requirement_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    ngo_id BIGINT UNSIGNED NOT NULL,

    food_type_preference ENUM(
        'VEGETARIAN',
        'NON_VEGETARIAN',
        'ANY'
    ) NOT NULL DEFAULT 'ANY',

    required_quantity DECIMAL(10,2) NOT NULL,

    quantity_unit ENUM(
        'KG',
        'LITRES',
        'PIECES'
    ) NOT NULL,

    required_by DATETIME NOT NULL,

    service_area VARCHAR(200),

    max_distance_km DECIMAL(10,2),

    requirement_status ENUM(
        'ACTIVE',
        'FULFILLED',
        'CANCELLED',
        'EXPIRED'
    ) NOT NULL DEFAULT 'ACTIVE',

    notes TEXT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_requirement_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 13. SURPLUS FOOD SUBMISSIONS
-- ============================================================

CREATE TABLE food_submissions (
    food_submission_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    recovery_id VARCHAR(30) NOT NULL UNIQUE,

    donor_id BIGINT UNSIGNED NOT NULL,

    food_type ENUM(
        'VEGETARIAN',
        'NON_VEGETARIAN'
    ) NOT NULL,

    quantity DECIMAL(10,2) NOT NULL,

    quantity_unit ENUM(
        'KG',
        'LITRES',
        'PIECES'
    ) NOT NULL,

    preparation_date DATE NOT NULL,

    preparation_time TIME NOT NULL,

    served_to_customers BOOLEAN NOT NULL DEFAULT FALSE,

    handling_information TEXT NULL,

    storage_handling_information TEXT NULL,

    applicable_consumption_date DATE NULL,

    applicable_consumption_time TIME NULL,

    available_from DATETIME NOT NULL,

    available_until DATETIME NOT NULL,

    donor_declaration BOOLEAN NOT NULL DEFAULT FALSE,

    donor_notes TEXT NULL,

    status ENUM(
        'SUBMITTED',
        'MATCHING',
        'VERIFICATION_PENDING',
        'VERIFIED',
        'VERIFICATION_FAILED',
        'COLLECTED',
        'DISTRIBUTED',
        'CANCELLED',
        'EXPIRED'
    ) NOT NULL DEFAULT 'SUBMITTED',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_food_submission_donor
        FOREIGN KEY (donor_id)
        REFERENCES donor_accounts(donor_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 14. AI-ASSISTED RECOVERY MATCHES
-- ============================================================

CREATE TABLE recovery_matches (
    match_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    match_code VARCHAR(30) NOT NULL UNIQUE,

    food_submission_id BIGINT UNSIGNED NOT NULL,

    ngo_id BIGINT UNSIGNED NOT NULL,

    requirement_id BIGINT UNSIGNED NULL,

    match_score DECIMAL(5,2),

    quantity_compatibility_score DECIMAL(5,2),

    food_type_compatibility_score DECIMAL(5,2),

    distance_km DECIMAL(10,2),

    urgency_score DECIMAL(5,2),

    availability_score DECIMAL(5,2),

    match_status ENUM(
        'RECOMMENDED',
        'ASSIGNED',
        'DECLINED',
        'FAILED',
        'COMPLETED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'RECOMMENDED',

    recommendation_reason TEXT NULL,

    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    assigned_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_match_food
        FOREIGN KEY (food_submission_id)
        REFERENCES food_submissions(food_submission_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_match_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_match_requirement
        FOREIGN KEY (requirement_id)
        REFERENCES ngo_recovery_requirements(requirement_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 15. PHYSICAL VERIFICATION RECORDS
-- ============================================================

CREATE TABLE verification_records (
    verification_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    verification_code VARCHAR(30) NOT NULL UNIQUE,

    food_submission_id BIGINT UNSIGNED NOT NULL,

    match_id BIGINT UNSIGNED NULL,

    ngo_id BIGINT UNSIGNED NOT NULL,

    representative_id BIGINT UNSIGNED NOT NULL,

    verification_attempt_no INT UNSIGNED NOT NULL DEFAULT 1,

    source_identity_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    submitted_batch_information_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    preparation_information_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    applicable_date_information_confirmed BOOLEAN NOT NULL DEFAULT FALSE,

    packaging_condition ENUM(
        'ACCEPTABLE',
        'NOT_ACCEPTABLE',
        'NOT_CHECKED'
    ) NOT NULL DEFAULT 'NOT_CHECKED',

    storage_handling_condition ENUM(
        'ACCEPTABLE',
        'NOT_ACCEPTABLE',
        'NOT_CHECKED'
    ) NOT NULL DEFAULT 'NOT_CHECKED',

    observable_condition ENUM(
        'SUITABLE',
        'UNSUITABLE',
        'NOT_CHECKED'
    ) NOT NULL DEFAULT 'NOT_CHECKED',

    physically_verified_quantity DECIMAL(10,2) NOT NULL,

    accepted_quantity DECIMAL(10,2) NOT NULL DEFAULT 0,

    quantity_unit ENUM(
        'KG',
        'LITRES',
        'PIECES'
    ) NOT NULL,

    decision ENUM(
        'ACCEPT_AND_COLLECT',
        'REJECT'
    ) NOT NULL,

    rejection_reason TEXT NULL,

    representative_confirmation BOOLEAN NOT NULL DEFAULT FALSE,

    representative_confirmation_text TEXT NULL,

    remarks TEXT NULL,

    verification_datetime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        food_submission_id,
        verification_attempt_no
    ),

    CONSTRAINT fk_verification_food
        FOREIGN KEY (food_submission_id)
        REFERENCES food_submissions(food_submission_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_verification_match
        FOREIGN KEY (match_id)
        REFERENCES recovery_matches(match_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_verification_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_verification_representative
        FOREIGN KEY (representative_id)
        REFERENCES ngo_representatives(representative_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 16. COLLECTION RECORDS
-- ============================================================

CREATE TABLE collection_records (
    collection_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    collection_code VARCHAR(30) NOT NULL UNIQUE,

    food_submission_id BIGINT UNSIGNED NOT NULL,

    verification_id BIGINT UNSIGNED NOT NULL,

    ngo_id BIGINT UNSIGNED NOT NULL,

    representative_id BIGINT UNSIGNED NOT NULL,

    collected_quantity DECIMAL(10,2) NOT NULL,

    quantity_unit ENUM(
        'KG',
        'LITRES',
        'PIECES'
    ) NOT NULL,

    collection_datetime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    handover_confirmation BOOLEAN NOT NULL DEFAULT FALSE,

    handover_notes TEXT NULL,

    status ENUM(
        'COLLECTED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'COLLECTED',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_collection_food
        FOREIGN KEY (food_submission_id)
        REFERENCES food_submissions(food_submission_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_collection_verification
        FOREIGN KEY (verification_id)
        REFERENCES verification_records(verification_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_collection_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_collection_representative
        FOREIGN KEY (representative_id)
        REFERENCES ngo_representatives(representative_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 17. DISTRIBUTION RECORDS
-- ============================================================

CREATE TABLE distribution_records (
    distribution_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    distribution_code VARCHAR(30) NOT NULL UNIQUE,

    food_submission_id BIGINT UNSIGNED NOT NULL,

    collection_id BIGINT UNSIGNED NOT NULL,

    ngo_id BIGINT UNSIGNED NOT NULL,

    distributed_quantity DECIMAL(10,2) NOT NULL,

    quantity_unit ENUM(
        'KG',
        'LITRES',
        'PIECES'
    ) NOT NULL,

    distribution_datetime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    recipient_count INT UNSIGNED,

    distribution_notes TEXT NULL,

    distribution_confirmation BOOLEAN NOT NULL DEFAULT FALSE,

    status ENUM(
        'DISTRIBUTED',
        'PARTIALLY_DISTRIBUTED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'DISTRIBUTED',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_distribution_food
        FOREIGN KEY (food_submission_id)
        REFERENCES food_submissions(food_submission_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_distribution_collection
        FOREIGN KEY (collection_id)
        REFERENCES collection_records(collection_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_distribution_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 18. NOTIFICATIONS
-- ============================================================

CREATE TABLE notifications (
    notification_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    notification_code VARCHAR(30) NOT NULL UNIQUE,

    recipient_type ENUM(
        'ADMIN',
        'DONOR',
        'NGO'
    ) NOT NULL,

    admin_id BIGINT UNSIGNED NULL,

    donor_id BIGINT UNSIGNED NULL,

    ngo_id BIGINT UNSIGNED NULL,

    notification_type VARCHAR(100) NOT NULL,

    title VARCHAR(200) NOT NULL,

    message TEXT NOT NULL,

    related_entity_type VARCHAR(100) NULL,

    related_entity_id BIGINT UNSIGNED NULL,

    is_read BOOLEAN NOT NULL DEFAULT FALSE,

    read_at DATETIME NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_notification_admin
        FOREIGN KEY (admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_notification_donor
        FOREIGN KEY (donor_id)
        REFERENCES donor_accounts(donor_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_notification_ngo
        FOREIGN KEY (ngo_id)
        REFERENCES ngo_accounts(ngo_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 19. ADMIN AUDIT LOGS
-- ============================================================

CREATE TABLE admin_audit_logs (
    audit_log_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    admin_id BIGINT UNSIGNED NOT NULL,

    action_type VARCHAR(100) NOT NULL,

    target_entity_type VARCHAR(100) NOT NULL,

    target_entity_id BIGINT UNSIGNED NULL,

    action_summary TEXT NOT NULL,

    old_status VARCHAR(100) NULL,

    new_status VARCHAR(100) NULL,

    ip_address VARCHAR(45) NULL,

    user_agent TEXT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_admin
        FOREIGN KEY (admin_id)
        REFERENCES admin_accounts(admin_id)
        ON DELETE RESTRICT
);


-- ============================================================
-- INDEXES FOR FASTER SEARCHING
-- ============================================================

CREATE INDEX idx_donor_application_status
ON donor_applications(application_status);

CREATE INDEX idx_donor_document_status
ON donor_documents(verification_status);

CREATE INDEX idx_ngo_application_status
ON ngo_applications(application_status);

CREATE INDEX idx_ngo_document_status
ON ngo_documents(verification_status);

CREATE INDEX idx_food_submission_status
ON food_submissions(status);

CREATE INDEX idx_food_submission_donor
ON food_submissions(donor_id);

CREATE INDEX idx_food_submission_available_until
ON food_submissions(available_until);

CREATE INDEX idx_recovery_match_status
ON recovery_matches(match_status);

CREATE INDEX idx_recovery_match_ngo
ON recovery_matches(ngo_id);

CREATE INDEX idx_verification_decision
ON verification_records(decision);

CREATE INDEX idx_verification_food
ON verification_records(food_submission_id);

CREATE INDEX idx_collection_ngo
ON collection_records(ngo_id);

CREATE INDEX idx_distribution_ngo
ON distribution_records(ngo_id);

CREATE INDEX idx_notifications_recipient
ON notifications(recipient_type);

CREATE INDEX idx_notifications_read
ON notifications(is_read);

CREATE INDEX idx_audit_created
ON admin_audit_logs(created_at);

CREATE INDEX idx_audit_target
ON admin_audit_logs(
    target_entity_type,
    target_entity_id
);


-- ============================================================
-- COMPLETION MESSAGE
-- ============================================================

SELECT 'ResQMeal database created successfully.' AS message;