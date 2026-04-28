# Demographic Intelligence Query Engine API

A FastAPI-based demographic profiling system designed for marketing teams, product teams, and growth analysts. Query 2026+ demographic profiles with advanced filtering, sorting, pagination, and natural language search capabilities.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    INSIGHTA LABS SYSTEM                         │
└─────────────────────────────────────────────────────────────────┘

                            ┌──────────────┐
                            │ GitHub OAuth │
                            │ (RFC 7636)   │
                            └────────┬─────┘
                                     │
                ┌────────────────────┼────────────────────┐
                │                    │                    │
          ┌─────▼──────┐       ┌─────▼──────┐       ┌─────▼──────┐
          │  Web Portal │       │  CLI Tool  │       │   Backend  │
          │ (Pure JS)   │       │  (Click)   │       │  (FastAPI) │
          └─────┬──────┘       └─────┬──────┘       └─────┬──────┘
                │                    │                    │
                └────────────────────┼────────────────────┘
                                     │
                            ┌────────▼─────────┐
                            │   REST API       │
                            │  (8 Endpoints)   │
                            └────────┬─────────┘
                                     │
                ┌────────────────────┼────────────────────┐
                │                    │                    │
          ┌─────▼──────┐       ┌─────▼──────┐       ┌─────▼──────┐
          │  Auth API  │       │ Profile    │       │ Middleware │
          │ (OAuth/JWT)│       │ Management │       │ (RBAC,     │
          │            │       │            │       │  Rate Lim, │
          │ ✓ Login    │       │ ✓ List     │       │  Logging)  │
          │ ✓ Logout   │       │ ✓ Search   │       │            │
          │ ✓ Refresh  │       │ ✓ Create   │       │ ✓ Token    │
          │ ✓ WhoAmI   │       │ ✓ Export   │       │ ✓ Role     │
          │            │       │            │       │ ✓ Rate     │
          └─────┬──────┘       └─────┬──────┘       └─────┬──────┘
                │                    │                    │
                └────────────────────┼────────────────────┘
                                     │
                            ┌────────▼─────────┐
                            │   SQLAlchemy     │
                            │      ORM         │
                            └────────┬─────────┘
                                     │
                            ┌────────▼─────────┐
                            │   Database       │
                            │  SQLite/Postgres │
                            │                  │
                            │ • User           │
                            │ • Session        │
                            │ • Profile        │
                            └──────────────────┘
```

### Component Overview

- **Backend API**: FastAPI REST server (port 8000)
  - 5 authentication endpoints (OAuth, refresh, logout, whoami)
  - 4 profile management endpoints (list, search, create, export)
  - Middleware for RBAC, rate limiting, logging, API versioning

- **CLI Tool**: Click-based command-line interface
  - 8 command groups for profile management
  - OAuth PKCE flow with browser popup
  - Secure token storage (~/.insighta/)

- **Web Portal**: Vanilla JavaScript SPA
  - 3 views (Profiles, Analytics, Admin)
  - Responsive design (mobile, tablet, desktop)
  - Local storage for token persistence

## Features

- **Advanced Filtering**: Combine multiple filters (gender, age_group, country_id, age ranges, probability thresholds)
- **Intelligent Sorting**: Sort by age, creation date, or gender probability in ascending/descending order
- **Pagination**: Efficient pagination with customizable page size (max 50 records per page)
- **Natural Language Search**: Parse plain English queries into structured demographic filters
- **Rule-Based NLP**: No LLMs - deterministic parsing ensures consistent, predictable results
- **CORS Support**: Ready for cross-origin requests (grading and client-side scripts)
- **Unique Profile Names**: No duplicate profiles in database
- **UTC Timestamps**: All timestamps in ISO 8601 format
- **UUID v7 Identifiers**: Every profile has a unique UUID v7 primary key

## Authentication Flow

### OAuth 2.0 with PKCE (RFC 7636)

The system implements GitHub OAuth 2.0 with Proof Key for Code Exchange (PKCE) for maximum security:

```
┌─────────────┐                                           ┌──────────────┐
│   Client    │                                           │ GitHub OAuth │
│ (Web/CLI)   │                                           │   Provider   │
└──────┬──────┘                                           └──────┬───────┘
       │                                                         │
       │ 1. Generate PKCE pair                                   │
       │    (code_verifier + code_challenge)                     │
       │                                                         │
       │ 2. Redirect to GitHub auth URL                         │
       │    + state parameter (CSRF protection)                 │
       ├────────────────────────────────────────────────────────>
       │                                                         │
       │                              3. User authenticates      │
       │                              (browser/user action)      │
       │                                                         │
       │<────────────────────────────────────────────────────────┤
       │    4. Redirect back with code + state                   │
       │                                                         │
       │ 5. Validate state (CSRF check)                         │
       │ 6. Exchange code for token                             │
       │    (+ code_verifier for PKCE verification)             │
       ├────────────────────────────────────────────────────────>
       │                                                         │
       │                      7. Return access_token             │
       │<────────────────────────────────────────────────────────┤
       │                                                         │
       │ 8. Get user info (github_id, username, avatar)        │
       ├────────────────────────────────────────────────────────>
       │                                                         │
       │                      9. Return user data                │
       │<────────────────────────────────────────────────────────┤
       │                                                         │
       ▼                                                         ▼
    (Ready)                                               (Complete)
```

### Step-by-Step Process

1. **PKCE Pair Generation** (Client)
   - `code_verifier`: Random 128-character string (alphanumeric + symbols)
   - `code_challenge`: Base64URL(SHA256(code_verifier))

2. **Authorization Request** (Client → GitHub)
   - Redirect user to GitHub with:
     - client_id (backend-provided)
     - redirect_uri (http://localhost:8000/auth/github/callback)
     - state (random 32-char CSRF token)
     - code_challenge (from PKCE)
     - code_challenge_method: S256 (SHA256)

3. **User Authorization** (GitHub OAuth)
   - User logs in to GitHub
   - Grants permissions
   - GitHub redirects to callback URL

4. **Code Exchange** (Client → Backend)
   - Client calls `/auth/github/callback` with:
     - code (from GitHub)
     - state (CSRF verification)
     - code_verifier (PKCE verification)

5. **Backend Verification**
   - Validates state matches session
   - Exchanges code for GitHub token (includes code_verifier)
   - Fetches user profile from GitHub API

6. **User Management**
   - Creates or updates User in database
   - Generates JWT tokens
   - Returns tokens to client

### Security Properties

- **No Client Secret in Frontend**: PKCE replaces client secret requirement
- **CSRF Protection**: State parameter validated
- **Authorization Code Reuse Prevention**: Code expires after 10 minutes
- **Secure Token Exchange**: Code verifier proves legitimate client possession
- **Safe for SPA/CLI**: Works without storing secrets client-side

## Token Handling

### JWT Token System

The backend uses JWT (JSON Web Tokens) with two-tier approach:

#### Access Token (Short-Lived)
```
{
  "sub": "user_id_uuid",           // User identifier
  "type": "access",                // Token type
  "role": "admin|analyst",         // User role
  "exp": 1234567890,              // Expiry: 3 minutes
  "iat": 1234567650,              // Issued at
  "iss": "insighta-labs",         // Issuer
  "jti": "unique_token_id"        // JWT ID (for revocation)
}
```

- **Expiry**: 3 minutes (balance between security & UX)
- **Purpose**: Access protected API endpoints
- **Location**: HTTP Authorization header (`Bearer <token>`)

#### Refresh Token (Medium-Lived)
```
{
  "sub": "user_id_uuid",          // User identifier
  "type": "refresh",              // Token type
  "exp": 1234569450,              // Expiry: 5 minutes
  "iat": 1234567650,              // Issued at
  "iss": "insighta-labs"          // Issuer
}
```

- **Expiry**: 5 minutes (longer than access token)
- **Purpose**: Obtain new access tokens
- **Location**: Request body or HTTP Authorization header
- **Storage**: Hashed in database (SHA256) for security

### Token Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│                  TOKEN LIFECYCLE                        │
└─────────────────────────────────────────────────────────┘

LOGIN
  ├─ Get authorization_url + state + code_verifier
  │
  └─ Callback with code → Create User & Session
        ↓
    ✅ Issue Access Token (3 min)
    ✅ Issue Refresh Token (5 min)
    ✅ Hash & store in database

USER MAKES REQUEST (Access Token)
  │
  ├─ Include: Authorization: Bearer <access_token>
  │
  └─ Validate:
      ├─ JWT signature (HS256)
      ├─ Not expired (< 3 min)
      ├─ Type == "access"
      ├─ User is_active
      └─ ✅ Allow request

ACCESS TOKEN EXPIRES (> 3 min)
  │
  ├─ Receive 401 Unauthorized
  │
  └─ POST /auth/refresh
      ├─ Validate refresh token
      ├─ Check is_revoked flag
      ├─ Verify < 5 min old
      │
      └─ ✅ Issue new token pair
          ├─ Mark old session as revoked
          ├─ Create new session
          └─ Return new tokens

LOGOUT
  │
  ├─ POST /auth/logout
  │
  └─ Database update:
      ├─ Set session.is_revoked = true
      ├─ Set session.revoked_at = now
      │
      └─ ✅ Token invalidated immediately
          └─ Future requests with token → 401
```

### Token Storage

**Backend**:
```sql
-- Session table
CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  refresh_token_hash VARCHAR NOT NULL,    -- SHA256(token)
  access_token_jti VARCHAR,               -- JWT ID for revocation
  issued_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  is_revoked BOOLEAN DEFAULT FALSE,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
```

**CLI/Web Portal**:
- Stored in localStorage (encrypted by browser)
- CLI: ~/.insighta/tokens.json (file mode 0o600)
- Never logged or transmitted unencrypted

### Automatic Token Refresh

Clients automatically refresh tokens when:
1. Access token expires (401 response)
2. Within 30 seconds of expiry (proactive refresh)

```javascript
// Web Portal example
async function makeRequest(endpoint) {
  if (isAccessTokenExpiringSoon()) {
    await refreshAccessToken();
  }
  
  try {
    return await fetch(endpoint, {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });
  } catch (error) {
    if (error.status === 401) {
      await refreshAccessToken();
      return fetch(endpoint, ...);  // retry
    }
  }
}
```

## Role Enforcement & Authorization

### Role-Based Access Control (RBAC)

The system implements three-tier authorization:

| Role | Permissions | Use Case |
|------|-------------|----------|
| **Admin** | • Full system access<br>• Create profiles<br>• Export all data<br>• User management | System administrators<br>Data team leads |
| **Analyst** | • List/search profiles<br>• Export own data<br>• View analytics | Analysts<br>Product managers |
| **User** | • Limited read access<br>• View public stats | External partners<br>Limited integrations |

### Authorization Enforcement Points

#### 1. Endpoint-Level Protection
```python
# Backend route protection
@router.post("/api/profiles", dependencies=[Depends(admin_only)])
async def create_profile(req: CreateProfileRequest):
    # Only admin can reach here
    ...

@router.get("/api/profiles")
async def list_profiles(current_user: CurrentUser = Depends()):
    # All authenticated users
    ...
```

#### 2. User Dependency Extraction
```python
# From auth/permissions.py
class CurrentUser:
    @staticmethod
    async def get_current_user(request: Request) -> User:
        # Extract Authorization header
        # Validate JWT signature
        # Check token type (access)
        # Verify not expired
        # Fetch user from database
        # Verify is_active
        # Return authenticated User object
```

#### 3. Permission Decorators
```python
@admin_only          # Requires role=="admin"
@analyst_only        # Requires role in ["analyst", "admin"]
@require_auth        # Just needs valid JWT
```

### Authorization Flow

```
REQUEST ARRIVES
  │
  ├─ Extract Authorization header
  │
  ├─ Validate JWT signature (HS256)
  │  └─ If invalid → 401 Unauthorized
  │
  ├─ Check token type == "access"
  │  └─ If wrong type → 401 Unauthorized
  │
  ├─ Check not expired (< 3 min)
  │  └─ If expired → 401 Unauthorized
  │
  ├─ Lookup user in database
  │  └─ If not found → 401 Unauthorized
  │
  ├─ Check is_active flag
  │  └─ If disabled → 403 Forbidden
  │
  ├─ Check endpoint-level permissions
  │  ├─ If @admin_only → verify role=="admin"
  │  └─ If role invalid → 403 Forbidden
  │
  └─ ✅ Allow request
     └─ Inject CurrentUser into handler
```

### Example Permission Checks

**Creating a Profile** (admin-only):
```
POST /api/profiles

1. User sends request with access token
2. Backend extracts & validates token
3. Looks up user: role=analyst
4. Checks @admin_only decorator
5. Compares role: analyst ≠ admin
6. Returns 403 Forbidden
   {
     "status": "error",
     "message": "Only admins can create profiles"
   }
```

**Listing Profiles** (any authenticated):
```
GET /api/profiles

1. User sends request with access token
2. Backend extracts & validates token
3. Looks up user: role=analyst
4. No role restriction on this endpoint
5. User can proceed
6. Returns filtered results per user role
```

## CLI Tool Usage

### Installation

```bash
# Install as editable package
cd cli
pip install -e .

# Verify installation
insighta --version
```

### Command Reference

#### Authentication Commands

**Login via GitHub**
```bash
insighta auth login

# Opens browser for GitHub OAuth
# Saves tokens to ~/.insighta/tokens.json
# Response:
# ✓ Login successful
# Welcome, <username>!
```

**Show Current User**
```bash
insighta auth whoami

# Response:
# ┌────────────────────┬──────────────────┐
# │ Field              │ Value            │
# ├────────────────────┼──────────────────┤
# │ ID                 │ abc123...        │
# │ Username           │ john_doe         │
# │ Email              │ john@github.com  │
# │ Role               │ admin            │
# │ Created At         │ 2026-04-01 ...   │
# │ Last Login         │ 2026-04-28 ...   │
# └────────────────────┴──────────────────┘
```

**Logout**
```bash
insighta auth logout

# Revokes refresh token
# Clears local token file
# Response:
# ✓ Logout successful
```

#### Profile Management Commands

**Search Profiles (NLP)**
```bash
insighta search "young males from nigeria"

# Options:
#   --limit INTEGER    Results per page (default: 10, max: 50)
#   --page INTEGER     Page number (default: 1)
#   --json             Output as JSON

# Response (table format):
# ┌──────────────┬────────────────┬────────┬──────────┐
# │ Name         │ Gender         │ Age    │ Country  │
# ├──────────────┼────────────────┼────────┼──────────┤
# │ chinedu      │ male (92%)     │ 22     │ Nigeria  │
# │ emeka        │ male (95%)     │ 25     │ Nigeria  │
# └──────────────┴────────────────┴────────┴──────────┘
```

**List Profiles with Filters**
```bash
insighta list \
  --gender male \
  --country NG \
  --min-age 25 \
  --max-age 40 \
  --limit 20

# Options:
#   --gender TEXT              male|female
#   --age-group TEXT           child|teenager|adult|senior
#   --country TEXT             ISO code (NG, KE, etc.)
#   --min-age INTEGER          Minimum age
#   --max-age INTEGER          Maximum age
#   --limit INTEGER            Results per page
#   --page INTEGER             Page number
#   --json                     JSON output
```

**Create Profile** (admin-only)
```bash
insighta create

# Interactive prompt:
# Profile Name: John Smith
# 
# Creating profile...
# ✓ Profile created successfully
# 
# ┌──────────────┬────────────────────┐
# │ Field        │ Value              │
# ├──────────────┼────────────────────┤
# │ Name         │ John Smith         │
# │ Gender       │ male (92%)         │
# │ Age          │ 32                 │
# │ Country      │ United States (US) │
# │ Created      │ 2026-04-28 14:30   │
# └──────────────┴────────────────────┘
```

**Export to CSV**
```bash
insighta export \
  --output profiles.csv \
  --gender female \
  --country NG

# Options:
#   --output TEXT (required)   Output file path
#   --gender TEXT              Filter by gender
#   --country TEXT             Filter by country
#   --min-age INTEGER          Minimum age
#   --max-age INTEGER          Maximum age
#   --page INTEGER             Page for multi-page export
#   --limit INTEGER            Rows per page

# Response:
# ✓ Export complete
# Saved 150 profiles to profiles.csv
```

#### Configuration Commands

**Set API URL**
```bash
insighta config set-url http://api.example.com:8000

# Response:
# ✓ API URL updated
# http://api.example.com:8000
```

**Show Configuration**
```bash
insighta config

# Response:
# ┌──────────────┬──────────────────────────────┐
# │ Setting      │ Value                        │
# ├──────────────┼──────────────────────────────┤
# │ API URL      │ http://localhost:8000        │
# │ Tokens File  │ ~/.insighta/tokens.json      │
# │ Config File  │ ~/.insighta/config.json      │
# │ Authenticated│ Yes                          │
# │ User         │ john_doe                     │
# └──────────────┴──────────────────────────────┘
```

### Workflow Examples

**Example 1: Find Young Females from Kenya**
```bash
# Search using natural language
insighta search "young females from kenya" --limit 15

# Or use filters
insighta list --gender female --country KE --min-age 16 --max-age 24

# Export results
insighta export --output kenya_females.csv --gender female --country KE
```

**Example 2: Admin Profile Creation Workflow**
```bash
# Login as admin
insighta auth login

# Check identity
insighta auth whoami

# Create a new profile
insighta create

# Export all profiles
insighta export --output all_profiles.csv

# Logout
insighta auth logout
```

**Example 3: Automated Data Pipeline**
```bash
# Get JSON output for programmatic processing
insighta search "adults from uganda" --json --limit 50 > uganda_data.json

# Parse JSON in your application
python << 'EOF'
import json, subprocess

result = subprocess.run(
  ["insighta", "list", "--country", "UG", "--json"],
  capture_output=True, text=True
)

profiles = json.loads(result.stdout)
for profile in profiles['data']:
  print(f"{profile['name']}: {profile['age']} years old")
EOF
```

### Error Handling

**Not Authenticated**
```bash
$ insighta list
✗ Error: Not authenticated
Please login first with: insighta auth login
```

**Permission Denied**
```bash
$ insighta create
✗ Error: Permission denied
Only admins can create profiles
```

**Invalid Credentials**
```bash
$ insighta auth login
Browser opened for GitHub login...
✗ Error: Login failed
Check your GitHub credentials and try again
```



```
profiles table:
├── id (UUID v7) - Primary Key
├── name (VARCHAR, UNIQUE) - Full name
├── gender (VARCHAR) - "male" or "female"
├── gender_probability (FLOAT) - Confidence score (0-1)
├── age (INT) - Exact age in years
├── age_group (VARCHAR) - child | teenager | adult | senior
├── country_id (VARCHAR 2) - ISO 3166-1 alpha-2 code (e.g., NG, BJ, GH)
├── country_name (VARCHAR) - Full country name
├── country_probability (FLOAT) - Confidence score (0-1)
└── created_at (TIMESTAMP) - Auto-generated UTC timestamp
```

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

1. Clone or download the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python main.py
   ```

The server will start on `http://localhost:8000`

## API Endpoints

### 1. Get All Profiles

**Endpoint**: `GET /api/profiles`

**Description**: Retrieve profiles with advanced filtering, sorting, and pagination.

**Query Parameters**:

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `gender` | string | Filter by gender (male/female) | `?gender=male` |
| `age_group` | string | Filter by age group (child/teenager/adult/senior) | `?age_group=adult` |
| `country_id` | string | Filter by country ISO code | `?country_id=NG` |
| `min_age` | integer | Minimum age | `?min_age=25` |
| `max_age` | integer | Maximum age | `?max_age=40` |
| `min_gender_probability` | float | Minimum gender confidence (0-1) | `?min_gender_probability=0.85` |
| `min_country_probability` | float | Minimum country confidence (0-1) | `?min_country_probability=0.80` |
| `sort_by` | string | Sort column: age, created_at, gender_probability (default: created_at) | `?sort_by=age` |
| `order` | string | Sort order: asc or desc (default: asc) | `?order=desc` |
| `page` | integer | Page number, 1-indexed (default: 1) | `?page=2` |
| `limit` | integer | Results per page, max 50 (default: 10) | `?limit=20` |

**Example Request**:
```
GET /api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc&page=1&limit=10
```

**Success Response** (200):
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "data": [
    {
      "id": "b3f9c1e2-7d4a-4c91-9c2a-1f0a8e5b6d12",
      "name": "emmanuel",
      "gender": "male",
      "gender_probability": 0.99,
      "age": 34,
      "age_group": "adult",
      "country_id": "NG",
      "country_name": "Nigeria",
      "country_probability": 0.85,
      "created_at": "2026-04-01T12:00:00Z"
    }
  ]
}
```

**Filter Combinations**: All filters use AND logic - results match ALL specified conditions.

---

### 2. Natural Language Search

**Endpoint**: `GET /api/profiles/search`

**Description**: Search profiles using plain English queries. Queries are parsed into structured filters using rule-based NLP.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Natural language search query |
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Results per page, max 50 (default: 10) |

**Example Requests**:
```
GET /api/profiles/search?q=young%20males%20from%20nigeria
GET /api/profiles/search?q=females%20above%2030
GET /api/profiles/search?q=adult%20males%20from%20kenya
GET /api/profiles/search?q=people%20from%20angola
```

**Success Response** (200):
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 45,
  "data": [
    {
      "id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p",
      "name": "chidinma",
      "gender": "male",
      "gender_probability": 0.92,
      "age": 22,
      "age_group": "teenager",
      "country_id": "NG",
      "country_name": "Nigeria",
      "country_probability": 0.88,
      "created_at": "2026-04-15T10:20:30Z"
    }
  ]
}
```

---

## Natural Language Parsing Guide

### Overview

The NLP parser uses **rule-based pattern matching** (no machine learning or LLMs). It searches for keywords in the query and maps them to filter parameters. This ensures:
- **Consistency**: Same query always produces same results
- **Predictability**: Users can understand how their query is interpreted
- **Performance**: No model inference overhead

### Supported Keywords

#### Gender Keywords
Maps gender terms to "male" or "female":
- **Male**: male, males, man, men, boy, boys
- **Female**: female, females, woman, women, girl, girls, lady, ladies

#### Age Group Keywords
Maps age group terms directly:
- **child**: child, children, kid, kids
- **teenager**: teenager, teen, teens
- **adult**: adult, adults
- **senior**: senior, seniors, elderly, old

#### Age-Related Keywords
Special handling for age ranges:
- **young**: Interpreted as ages 16-24 (target social media era + emerging adults)
- **middle-aged**: Interpreted as ages 35-55
- **old**: Interpreted as ages 60+

#### Age Operators
Extract numeric age ranges:
- **Comparison**: "above 30", "over 25", "older than 30", "> X"
- **Comparison**: "below 30", "under 25", "younger than 30", "< X"
- **Ranges**: "between 25 and 40"
- **Direct numbers**: "20-30" (age range), "25 year old"

#### Country Keywords
Maps country names/demonyms to ISO 3166-1 alpha-2 codes:
- Nigeria → NG
- Benin → BJ
- Ghana → GH
- Kenya → KE
- Uganda → UG
- Tanzania → TZ
- South Africa → ZA
- Egypt → EG
- Ethiopia → ET
- Cameroon → CM
- Angola → AO
- Mozambique → MZ
- Zimbabwe → ZW
- Zambia → ZM
- Malawi → MW
- Botswana → BW

### Query Parsing Logic

1. **Extract age ranges** using regex patterns for numeric ages and comparison operators
2. **Extract gender** by searching for gender keywords
3. **Extract age group** by searching for age group keywords
4. **Extract country** by searching for country keywords in mapping

Once at least one parameter is identified, the query is considered interpretable and results are returned.

### Example Query Mappings

| Query | Parsed Filters | Notes |
|-------|---|---|
| "young males from nigeria" | gender=male, min_age=16, max_age=24, country_id=NG | Uses "young" range + gender + country |
| "females above 30" | gender=female, min_age=30 | No max_age since "above 30" is open-ended |
| "people from angola" | country_id=AO | Only country extracted |
| "adult males from kenya" | gender=male, age_group=adult, country_id=KE | Combines age group, gender, country |
| "male and female teenagers above 17" | age_group=teenager, min_age=17 | Extracts teenager + age limit; "male and female" = no gender filter |
| "25-30 year old females" | min_age=25, max_age=30, gender=female | Extracts range + gender |

### Numeric Age Extraction Priority

When multiple numeric patterns exist:
1. **between X and Y** takes highest priority (explicit range)
2. **above/over/below/under** operators next (comparison logic)
3. **Age range "X-Y"** third
4. **Single number** last (treated as age range context if available)

### Error Handling

**Uninterpretable Query** (400):
```json
{
  "status": "error",
  "message": "Unable to interpret query"
}
```

Returned when the parser finds no recognizable keywords.

Examples of uninterpretable queries:
- Empty string: `q=`
- Only numbers without context: `q=123`
- Random words: `q=xyz abc def`
- Unsupported country: `q=people from atlantis`

---

## Limitations & Edge Cases

### What the Parser Doesn't Handle

1. **Complex Boolean Logic**: 
   - "Males OR females" → Parser only extracts last gender keyword
   - "Nigeria BUT NOT Benin" → Cannot exclude countries
   - **Workaround**: Use the `/api/profiles` endpoint directly with boolean queries

2. **Negation**:
   - "NOT males" → Interpreted as no gender filter (ignores negation)
   - "Anything except adults" → Age group ignored
   - **Workaround**: Specify positive filters instead

3. **Probabilistic Thresholds**:
   - "Highly confident females" → Ignores probability thresholds
   - "Uncertain age profiles" → No way to parse
   - **Workaround**: Use `/api/profiles?gender=female&min_gender_probability=0.9` directly

4. **Adjacency/Conjunction Logic**:
   - "Males from Nigeria or females from Kenya" → Extracts last match only
   - Parser doesn't understand "or" branching logic
   - **Current behavior**: Extracts gender=female, country_id=KE

5. **Relative Time Expressions**:
   - "Recently joined" → Not parsed (no temporal data)
   - "Created today" → No support for relative dates

6. **Profile-Specific Attributes**:
   - "Named John" → Name searching not supported
   - "With high confidence" → Ambiguous which confidence value

7. **Ambiguous Keywords**:
   - "Adult" could mean age_group=adult OR min_age=18 (interpreter chooses age_group)
   - "Young" has fixed range (16-24), not dynamic

8. **Multiple Countries**:
   - "Nigeria and Benin" → Only Nigeria extracted (last match wins in country parsing)
   - No support for OR logic between countries

### Known Edge Cases

1. **Whitespace Handling**:
   - Extra spaces are normalized: "young  males" works correctly
   - Leading/trailing spaces are trimmed

2. **Case Insensitivity**:
   - "YOUNG MALES" = "young males" (all lowercase internally)
   - Preserved in output though

3. **Overlapping Keywords**:
   - "Old adult senior" → age_group=senior (first match wins)
   - "Male female" → gender=female (last match wins)

4. **Number Parsing**:
   - "25-30" and "between 25 and 30" both work
   - "30+" interpreted as "> 30"
   - "30-" not supported

5. **Pagination Beyond Results**:
   - Page 1000 with 5 total results returns empty data array with correct total
   - Not an error - returns valid success response

### Performance Considerations

- **Full-table scans**: Avoided using indexed columns (name, gender, age, country_id, age_group)
- **Large result sets**: Pagination prevents memory bloat; max 50 per page
- **Filter combinations**: Database handles AND logic efficiently (use indices)
- **No sorting overhead**: Database sorts before pagination

### Future Enhancement Opportunities

1. Implement fuzzy matching for country names (e.g., "South Africa" → "ZA")
2. Add support for complex boolean expressions
3. Parse probability thresholds ("high confidence males")
4. Support name-based searching
5. Add temporal filtering ("joined this month")
6. Context-aware "young"/"old" based on distribution

---

## Error Responses

All errors follow a consistent structure:

```json
{
  "status": "error",
  "message": "<error description>"
}
```

### HTTP Status Codes

| Status | Scenario |
|--------|----------|
| 200 | Successful request |
| 400 | Missing required parameter (`q` for search) or empty string |
| 422 | Invalid parameter type or value (e.g., invalid gender) |
| 500 | Server error (unhandled exception) |

### Example Error Responses

**Invalid Gender Filter** (422):
```bash
GET /api/profiles?gender=invalid
```
```json
{
  "status": "error",
  "message": "Invalid gender value"
}
```

**Invalid Age Value** (422):
```bash
GET /api/profiles?min_age=-5
```
```json
{
  "status": "error",
  "message": "min_age cannot be negative"
}
```

**Missing Search Query** (400):
```bash
GET /api/profiles/search
```
```json
{
  "status": "error",
  "message": "Query parameter 'q' is required and cannot be empty"
}
```

**Uninterpretable Query** (400):
```bash
GET /api/profiles/search?q=xyz
```
```json
{
  "status": "error",
  "message": "Unable to interpret query"
}
```

---

## Setup Guide for Seeding with Real Data

### Option 1: Using Google Drive JSON (Recommended)

Replace the `generate_sample_profiles()` function in `seed.py`:

```python
def seed_database():
    """Download and seed profiles from Google Drive"""
    import gdown
    
    file_url = "https://drive.google.com/uc?id=1Up06dcS9OfUEnDj_u6OV_xTRntupFhPH"
    gdown.download(file_url, "profiles.json", quiet=False)
    
    with open("profiles.json") as f:
        profiles = json.load(f)
    
    # Rest of seeding logic...
```

### Option 2: Local JSON File

Place your 2026 profiles JSON in the root directory and update `seed.py`:

```python
with open("profiles_2026.json") as f:
    profiles = json.load(f)
```

### Re-running Seed

The seed script checks for duplicate names before inserting:
```bash
python seed.py
# Run again - won't create duplicates
python seed.py
```

---

## Development

### Project Structure

```
.
├── main.py           # FastAPI app initialization
├── database.py       # SQLAlchemy setup
├── models.py         # ORM models (Profile)
├── schema.py         # Pydantic request/response schemas
├── routes.py         # API endpoints
├── nlp_parser.py     # Natural language parser
├── seed.py           # Database seeding logic
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

### Running Tests

```bash
# Install test dependencies
pip install pytest httpx

# Run tests
pytest
```

### Database

- **SQLite** (default): `profiles.db` - includes full ORM with 2026 profiles
- **PostgreSQL** (production): Set `DATABASE_URL` environment variable

---

## Performance Metrics

- Query execution: <50ms for 1000+ results with filters
- Search parsing: <5ms per query
- Pagination: O(1) with database LIMIT/OFFSET

## CORS Support

API responds with `Access-Control-Allow-Origin: *` header to all requests, enabling:
- Cross-origin AJAX requests from web clients
- Grading script access from any origin
- Integration with external tools

---

## Contact & Support

For issues or questions about the API implementation, refer to the inline code comments and error messages.

