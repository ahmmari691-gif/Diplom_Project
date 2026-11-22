Educational project for the course Business Analysis, Astana IT University. Not a real product or service. All data are fictional.

# DELO DOMA
### Software Requirements Specification and Working Prototype

**Course:** Business Analysis  
**University:** Astana IT University  
**Academic Year:** 2026–2027  
**Team:** 01  
**Supervisor:** Nurkhat Ibadildin, Associate Professor

**GitHub Repository:** https://github.com/ahmmari691-gif/Diplom_Project

**Demonstration Video:** https://astanait-my.sharepoint.com/personal/241274_astanait_edu_kz/_layouts/15/stream.aspx?id=%2Fpersonal%2F241274%5Fastanait%5Fedu%5Fkz%2FDocuments%2FTeam01%5FFP%5FDemo%2Emp4&nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJPbmVEcml2ZUZvckJ1c2luZXNzIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFsTW9kZSI6InZpZXciLCJyZWZlcnJhbFZpZXciOiJNeUZpbGVzTGlua0NvcHkifX0&share=cQobPea%5Fbt8jRak%2DEvdg%5Fo5%2DEgUCfRCJ8Bd%5F54tF%5F8YfZB5n1Q&CID=3c3d202e%2D3b01%2D4a5c%2D8bd9%2D9a09a8c3b619&referrer=StreamWebApp%2EWeb&referrerScenario=AddressBarCopied%2Eview%2E037475fa%2D574f%2D4b31%2D8c0b%2D64c3d09d2ff2

---

## 1. Project Overview

Delo Doma is an educational web platform designed to support order coordination and daily operations for micro and small businesses.

Many small businesses manage customer requests through messaging applications and informal notes. This can make it difficult to maintain complete order information, track progress, and respond to customer enquiries.

Delo Doma provides a centralised system where businesses can publish their catalogues, receive structured customer requests, manage order statuses, and provide customers with private order-tracking links.

The platform also supports optional AI assistance through Google Gemini. Customers can receive business-specific information and help preparing order drafts, while business owners remain responsible for order acceptance and fulfilment.

The main purpose of the prototype is to demonstrate how software requirements can be implemented, traced, and validated through a working application.

## 2. Main Features

The platform includes six main functional areas:

1. **Account Access and Business Isolation:** Authentication, registration, role-based permissions, and protection of business information.
2. **Business Configuration and Catalogue:** Business profiles, product catalogues, public storefronts, and multilingual interfaces.
3. **AI Assistance and Reference Knowledge:** Business-specific assistance, document uploads, customer consent, and structured order drafts.
4. **Structured Orders and Fulfilment:** Order submission, server-side price calculation, order management, and status updates.
5. **Order Tracking and Privacy:** Private tracking links, cancellation rules, anonymisation, and audit logging.
6. **Platform Operations:** Manager invitations, platform analytics, campaigns, tasks, and user guidance.

Additional inventory-related functionality is present in the application, but the Final Project evaluation focuses on the requirements defined in the SRS.

## 3. User Roles and Access Rights

The system defines four user classes.

| User Role | Responsibilities |
|---|---|
| Customer | Browses public catalogues, submits orders, and tracks requests using private links. |
| Business Owner | Manages business information, products, reference files, and orders belonging to their business. |
| Platform Administrator | Has manager capabilities; additionally suspends/resumes businesses, invites/revokes managers, and reads platform audit events. |
| Platform Manager | Maintains public business profiles and reference documents; accesses aggregate statistics, campaigns, and tasks. |

Role-based permissions are enforced by the backend.

Business owners cannot access protected orders belonging to other businesses. Platform-level permissions do not automatically grant access to private customer order contents.

Customers do not need a staff account to browse catalogues or track individual orders.

### Updated ERD and test database baseline

The guest buyer (`core.User`) and authenticated owner/staff login (`core.Account`) are separate entities.
Buyers and businesses are related **only through orders**: `User → Order ← Business`.
The owner of a business is an `Account`, never the guest buyer.

See [ERD, role permissions and reset instructions](docs/erd/README.md).
This release intentionally replaces the initial migration for the approved disposable test database.
It **requires an empty database** and must not be applied over the previous migration history.
The startup guard rejects the old schema without deleting it.

## 4. Functional Requirements

The Final Project SRS defines **30 functional requirements (FR-01–FR-30)**.

The source-code review documented in the Final Project report identified implementation paths for 29 requirements (96.7%). FR-25 remains unimplemented.

### 4.1 Account Access and Business Isolation

| ID | Requirement | Source Review Status |
|---|---|---|
| FR-01 | User authentication | Implemented |
| FR-02 | Registration consent validation | Implemented |
| FR-03 | Server-side role-based permissions | Implemented |
| FR-04 | User logout and session invalidation | Implemented |
| FR-05 | Cross-business order isolation | Implemented |

### 4.2 Business Configuration and Catalogue

| ID | Requirement | Source Review Status |
|---|---|---|
| FR-06 | Business profile management | Implemented |
| FR-07 | Catalogue entry validation | Implemented |
| FR-08 | Public catalogue access | Implemented |
| FR-09 | Restrictions for paused businesses | Implemented |
| FR-10 | Russian, Kazakh, and English interface labels | Implemented; browser validation pending |

### 4.3 AI Assistance and Reference Knowledge

| ID | Requirement | Source Review Status |
|---|---|---|
| FR-11 | External AI consent verification | Implemented |
| FR-12 | Business-specific assistance context | Implemented |
| FR-13 | AI-generated order draft validation | Implemented |
| FR-14 | Direct ordering without external AI | Implemented |
| FR-15 | Reference-file management | Implemented; full format validation pending |

### 4.4 Structured Orders and Fulfilment

| ID | Requirement | Source Review Status |
|---|---|---|
| FR-16 | Order submission validation | Implemented |
| FR-17 | Server-side order total calculation | Implemented |
| FR-18 | Order creation and private tracking token | Implemented |
| FR-19 | Business owner order list | Implemented |
| FR-20 | Controlled order status transitions | Implemented |

### 4.5 Tracking, Cancellation and Privacy

| ID | Requirement | Source Review Status |
|---|---|---|
| FR-21 | Private order tracking | Implemented |
| FR-22 | Customer cancellation restrictions | Implemented; exact boundary test pending |
| FR-23 | Closed-order anonymisation | Implemented |
| FR-24 | Privacy-preserving audit logging | Implemented |
| FR-25 | Duplicate-submission prevention with idempotency keys | Not implemented |

### 4.6 Platform Operations and User Guidance

| ID | Requirement | Source Review Status |
|---|---|---|
| FR-26 | Manager invitations and access control | Implemented |
| FR-27 | Aggregate platform statistics | Implemented |
| FR-28 | Platform campaign and task management | Implemented |
| FR-29 | Multilingual site guidance | Implemented |
| FR-30 | Seller-responsibility notices | Implemented; visual verification pending |

**Implementation summary:**

- Total specified functional requirements: 30
- Requirements with identified implementation paths: 29
- Not implemented: FR-25
- Reported source implementation coverage: 96.7%

These statuses reflect the reviewed source baseline, not a claim that all requirements have completed acceptance testing.

## 5. Technology Stack

### Frontend

- React
- TypeScript
- Vite
- Responsive browser-based interface

### Backend

- Python 3.12+
- Django 5.2
- Server-side authentication and validation
- JSON-based application endpoints

### Database

- SQLite for local development and isolated automated tests
- PostgreSQL for hosted deployment

### Additional Technologies

- Google Gemini API for optional AI assistance
- Docker for application packaging
- Gunicorn for production WSGI serving
- WhiteNoise for static-file serving
- Render for optional hosted previews

The frontend communicates with Django through HTTP requests. Django is responsible for enforcing permissions, validating submitted data, calculating order totals, and applying order-status rules.

The structured ordering process does not require a successful external AI response.

## 6. Project Structure

The GitHub repository contains the application inside the `delo-doma 2` directory.

```text
Diplom_Project/
│
├── delo-doma 2/
│   ├── core/
│   ├── config/
│   ├── frontend/
│   │   └── src/
│   ├── requirements.txt
│   ├── manage.py
│   ├── run.py
│   ├── Dockerfile
│   └── README.md
│
└── render.yaml
```

**Main directories and files:**

- `core/` — Backend application logic, models, migrations, tests, and management commands.
- `config/` — Django configuration, settings, and URL routing.
- `frontend/src/` — React components, interface styling, and translations.
- `requirements.txt` — Python dependencies.
- `manage.py` — Django management commands.
- `run.py` — Local development launcher.
- `Dockerfile` — Application container configuration.
- `render.yaml` — Render deployment configuration.

## 7. Installation and Local Setup

The prototype is designed to run locally for educational demonstration and assessment.

### 7.1 Prerequisites

Install the following software:

- Python 3.12 or newer
- Node.js 22.12 or a newer supported version
- npm
- Git

### 7.2 Clone the Repository

Open a terminal and run:

```bash
git clone https://github.com/ahmmari691-gif/Diplom_Project.git
cd Diplom_Project
cd "delo-doma 2"
```

### 7.3 Create a Virtual Environment

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 7.4 Install Backend Dependencies

```bash
python -m pip install -r requirements.txt
```

### 7.5 Configure Environment Variables

The application supports local operation without an external AI API key.

For optional configuration, create a private `.env` file in the application directory. If an `.env.example` file is included in your local copy, you may copy it first.

Example local settings:

```dotenv
DJANGO_DEBUG=1
DELO_AI_MODE=local
```

Do not upload `.env` to GitHub.

The local launcher uses development settings and creates local secret files when needed.

### 7.6 Build the Frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

The frontend must be built before the Python launcher starts the application.

### 7.7 Start the Application

```bash
python run.py
```

The launcher applies database migrations, performs Django checks, and starts the local development server.

Open:

http://127.0.0.1:8000/

The website should now be accessible through the local browser.

### 7.8 Optional Demonstration Data

To initialise fictional demonstration records:

```bash
python run.py --demo
```

This command runs the local demonstration-data setup.

Only fictional records should be used.

## 8. Demonstration Accounts

The prototype supports several user roles. At least two authenticated roles must be demonstrated during the Final Project defense.

Complete this table using the actual fictional test accounts prepared for assessment.

| User Role | Demo Email | Demo Password |
|---|---|---|
| Business Owner | business@demo.local | Study-Business-2026 |
| Platform Manager | manager@demo.local | Study-Manager-2026 |
| Platform Administrator | admin@demo.local | Study-Admin-2026 |
| Customer | No account required | Private tracking token |

**Account preparation:**

A business-owner account can be created through the application's registration process.

An administrator account can be created locally using:

```bash
python manage.py createsuperuser
```

The Django administration interface is available at:

http://127.0.0.1:8000/django-admin/

A platform manager receives access through an invitation issued by a platform administrator.

All test credentials must be fictional and restricted to the educational demonstration environment. Do not use personal account credentials or enable these demonstration accounts in a publicly accessible production environment.

## 9. Main Use Case

The main use case demonstrates the customer-to-business ordering process.

**UC-1: Customer Order Submission and Fulfilment Tracking**

1. The business owner signs in and configures the business catalogue.
2. The customer opens the business's public storefront.
3. The customer selects an offering and enters the required order details.
4. The system validates the request and calculates the total using the stored catalogue price.
5. The system creates the order with status `New` and returns a private tracking link.
6. The business owner opens the order list and reviews the request.
7. The owner updates the status through permitted transitions.
8. The customer opens or reloads the tracking link to view the latest saved status.

**Order status progression:**

`New → Working → Ready → Done`

Customer cancellation is handled separately and is subject to the system's eligibility rules.

A submitted order is not automatically confirmed by the business. The order becomes accepted for processing when the owner starts the permitted fulfilment workflow.

**Related requirements:**

FR-01, FR-05, FR-08, FR-14, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, and FR-30.

## 10. Optional Google Gemini Integration

Delo Doma supports Google Gemini for business-specific assistance.

The assistant can help customers:

- Find information about a business.
- Understand available products or services.
- Prepare structured order drafts.
- Receive routine guidance.

AI-generated information is validated by the backend before it is used in the order workflow.

### Gemini Configuration

In the private `.env` file, configure:

```dotenv
DELO_AI_MODE=gemini
GEMINI_API_KEY=YOUR_PRIVATE_API_KEY
GEMINI_MODEL=YOUR_AVAILABLE_MODEL
```

Replace the placeholders with valid private configuration values.

The provider can also be selected by starting the local launcher with:

```bash
python run.py --gemini
```

The exact model and usage limits depend on the Google account and API configuration.

External AI processing requires appropriate consent from both the customer and the selected business.

If Gemini is unavailable, the customer can still submit orders using the standard structured form.

AI responses do not independently confirm orders or replace business-owner decisions.

## 11. Testing and Validation

Testing connects the implemented prototype with the functional requirements documented in the SRS.

### 11.1 Development Checks

After building the frontend, run:

```bash
python manage.py check
```

To run the Django test suite:

```bash
python manage.py test
```

### 11.2 Reported Test Results

The Final Project report documents the following results for the reviewed baseline:

| Indicator | Reported Result |
|---|---|
| Functional requirements | 30 |
| Requirements with identified implementation paths | 29 |
| Documented acceptance cases | 20 |
| Acceptance cases marked Pass | 18 |
| Automated tests in the selected regression run | 27 passed |
| Browser acceptance case TC-19 | Pending |
| Duplicate-submission case TC-20 | Not executed |

The automated regression results were recorded on November 13, 2026, using commit `1e3044c`, Python 3.12, Django 5.2.18, and an isolated SQLite database.

These results describe the tested baseline and should be rechecked after subsequent code changes.

### 11.3 Tested Areas

The documented acceptance tests cover:

- Authentication and logout.
- Registration and role-based access.
- Cross-business isolation.
- Business profile and catalogue persistence.
- Public catalogue access.
- Order validation and server-calculated prices.
- Customer tracking authorisation.
- Order status updates.
- Cancellation restrictions.
- Order anonymisation and audit logging.
- Reference-file management.
- External AI consent and draft validation.
- Manager invitations.
- Platform analytics and operations.
- Multilingual site guidance.

External Gemini tests use mocked provider responses and do not establish the availability of the live provider.

### 11.4 Remaining Validation Activities

The following activities remain outstanding in the documented baseline:

- Complete responsive and multilingual browser testing (TC-19).
- Validate required keyboard-accessible controls.
- Test the main workflow with at least three independent participants outside the project team.
- Verify the final demonstration environment.
- Test live Gemini integration separately with fictional inputs and confirmed consent.
- Implement and validate duplicate-submission protection (FR-25).

The detailed requirements traceability matrix and test results are provided in Appendices F and G of the Final Project report.

## 12. Security, Privacy and Data Protection

Delo Doma includes technical measures intended to protect business and customer information.

The documented design includes:

- Server-side authentication.
- Role-based access control.
- Cross-business data isolation.
- Server-side order validation.
- Password hashing.
- Private tracking tokens.
- Encrypted sensitive order information.
- Consent checks before external AI processing.
- Order anonymisation.
- Privacy-preserving audit records.

The Kazakhstan Law on Personal Data and Their Protection is considered a design constraint in the SRS.

The educational prototype is not presented as a certified or production-compliant system.

### Data and Safety Rules

- Use fictional names, contact details, and order records.
- Do not collect personal data from real customers.
- Do not process real payments.
- Do not upload real business documents containing confidential information.
- Do not expose API keys or private environment variables.
- Do not make the prototype publicly accessible for real customer use.
- Use the prototype only in authorised educational testing and demonstration environments.

Private files such as `.env`, `.local/`, databases containing test records, and uploaded reference documents must not be committed to the repository.

Before committing changes, verify that the project's `.gitignore` excludes sensitive files.

## 13. Deployment

The prototype can run locally without paid hosting.

Localhost is the default environment for Final Project assessment.

A hosted preview may be configured for controlled educational demonstrations, subject to the course's data and safety restrictions.

### 13.1 Production Configuration Considerations

Public-facing deployment requires appropriate configuration, including:

- A WSGI server such as Gunicorn.
- HTTPS configuration.
- Secure private environment variables.
- Database configuration and backups.
- Django allowed hosts and CSRF origins.
- Static-file collection and serving.
- Restricted access to private information.

GitHub Pages alone cannot run the Django backend.

### 13.2 Render Configuration

The repository contains a `render.yaml` configuration for Docker-based deployment with PostgreSQL.

To configure an optional preview in Render:

1. Connect the GitHub repository to Render.
2. Select **New** and then **Blueprint**.
3. Select the repository and review the proposed services.
4. Verify that the plan does not require payment.
5. Configure private environment variables before deployment.

The existing Blueprint is configured with a Docker web service and PostgreSQL database.

Free-tier restrictions, service availability, and database retention depend on Render's current service terms. The configuration was developed for a temporary preview rather than permanent production hosting.

Render generates independent server secrets. The `DATA_ENCRYPTION_SECRET` must remain consistent while using the same encrypted database records.

No real customer data or private local credentials should be migrated to the hosted preview.

The default hosted configuration uses local assistance; Gemini can be configured separately through private environment variables.

## 14. Demonstration Video

**Video:** [INSERT UNIVERSITY ONEDRIVE VIDEO LINK]

**Required filename:** `Team01_FP_Demo.mp4`

The demonstration video must be no longer than three minutes and show:

1. Authentication using at least two different user roles.
2. The main customer-to-owner ordering workflow.
3. Customer order submission.
4. Data saved and retrieved from the system.
5. Order management and status changes.
6. Updated order information visible to the customer.
7. Functional requirement IDs demonstrated in the video.

The video must not expose passwords, API keys, `.env` contents, or personal data.

It must be uploaded to the university OneDrive with viewing access configured according to the Final Project requirements.

## 15. Known Limitations and Future Improvements

The current prototype has several limitations documented in the SRS.

**Known limitations:**

- FR-25 duplicate-submission prevention is not implemented.
- Full responsive and multilingual browser acceptance testing remains incomplete.
- Independent user testing remains outstanding in the reviewed report.
- Live Gemini performance and response quality require further verification.
- Some requirements require additional boundary and negative testing.

**Planned improvements:**

- Implement idempotency-key protection against duplicate orders.
- Complete browser-based acceptance testing.
- Improve external AI reliability and response evaluation.
- Clarify cancellation behaviour in additional order states.
- Strengthen data-export and recovery procedures.
- Continue validating the system against measurable usability and performance criteria.

These improvements represent planned work rather than completed functionality.

## 16. Open-Source Technologies and Credits

Delo Doma uses open-source technologies and supporting tools, including:

- Django — https://www.djangoproject.com/
- React — https://react.dev/
- TypeScript — https://www.typescriptlang.org/
- Vite — https://vite.dev/
- PostgreSQL — https://www.postgresql.org/
- SQLite — https://www.sqlite.org/
- Gunicorn — https://gunicorn.org/
- WhiteNoise — https://whitenoise.readthedocs.io/

These technologies are governed by their respective licences.

Any additional third-party source code, templates, or UI kits reused in the application must be credited and used in accordance with their licences.

Google Gemini is an external AI service rather than a component owned by the project team.

## 17. Project Team

| Student | Group |
|---|---|
| Dana Dyseneva | ITM-2402 |
| Sabina Dyseneva | ITM-2402 |
| Mariya Akhmetshina | ITM-2402 |

**Supervisor:** Nurkhat Ibadildin, Associate Professor

**University:** Astana IT University

**Course:** Business Analysis

**Academic Year:** 2026–2027

## 18. Academic Use Notice

Delo Doma was developed as an educational prototype for the Business Analysis course at Astana IT University.

The project demonstrates requirements specification, software design, implementation, requirements traceability, and validation.

It is not a commercial product or a service offered to real customers.

All demonstration and testing activities must follow the university's project ethics, privacy, and safety requirements.
The project demonstrates requirements specification, software design, implementation, requirements traceability, and validation.

It is not a commercial product or a service offered to real customers.

All demonstration and testing activities must follow the university's project ethics, privacy, and safety requirements.
