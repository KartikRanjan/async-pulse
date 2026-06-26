# Request Lifecycle, Dependency Injection & Caching — Complete Flow

This document explains the **complete end-to-end authentication and caching flow** in AsyncPulse.

Topics covered:

- **DI Lifecycle**: Why services are per-request, not singletons
- **Authentication Flow**: Login → Token Usage → Logout
- **Cache-Aside Pattern**: How data persists across requests
- **Session Revocation**: How status changes immediately lock users out
- **Refresh Token Rotation**: Grace periods, breach detection, atomic rotation

> ### ⚠️ Note on example endpoints
>
> Some routes used in the diagrams below are **illustrative**, not yet implemented:
>
> | Endpoint in diagrams                                                    | Status                                                                                       |
> | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
> | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/logout-all` | ✅ Real                                                                                      |
> | `PATCH /users/{id}` (update), `DELETE /users/{id}` (superuser)          | ✅ Real, runs `get_current_user`                                                             |
> | `GET /users/`, `GET /users/{id}`                                        | ✅ Real, but currently **public** (no `get_current_user`)                                    |
> | `GET /users/me`                                                         | ❌ **Not implemented** — used as a representative "protected read" example                   |
> | `PATCH /users/{id}/status`                                              | ❌ **Not implemented** — `UserService.change_status` exists but isn't exposed as a route yet |
>
> The `get_current_user` flow shown applies to **any** route that declares
> `Depends(get_current_user)` (today: `PATCH`/`DELETE /users/{id}`, `POST /auth/logout-all`).
> Timing numbers in the performance section are illustrative, not measured.

---

## 1. Architecture Overview: Singletons vs Per-Request

```mermaid
graph TB
    subgraph "Server Startup (once)"
        Cache["🔄 CacheClient<br/>(Redis/Memory)<br/>SINGLETON"]
        Engine["🔌 SQLAlchemy Engine<br/>(Connection Pool)<br/>SINGLETON"]
    end

    subgraph "Every Request (fresh)"
        Session["📋 AsyncSession<br/>(per-request tx)"]
        Repo["📚 UserRepository<br/>AuthRepository"]
        Service["⚙️ UserService<br/>AuthService"]
    end

    Cache -->|shared| Service
    Engine -->|pool| Session
    Session -->|holds| Repo
    Repo -->|held by| Service

    style Cache fill:#90EE90
    style Engine fill:#90EE90
    style Session fill:#FFB6C1
    style Repo fill:#FFB6C1
    style Service fill:#FFB6C1
```

**Key insight:** Services are created per-request because they wrap an `AsyncSession`, which is request-scoped (each request = one transaction). The expensive resources (Redis, DB connections) live in singleton pools underneath.

| Framework    | Service Lifetime | How It Stays Safe                             |
| ------------ | ---------------- | --------------------------------------------- |
| Spring Boot  | Singleton        | Thread-bound transaction via `@Transactional` |
| ASP.NET Core | Scoped (per-req) | `DbContext` is scoped                         |
| NestJS       | Singleton        | ALS ambient context (nestjs-cls)              |
| **FastAPI**  | **Per-request**  | Wrapper is per-request, resources in pools    |

---

## 2. Complete Authentication Flow: Login → Use → Logout

### 2.1 Login Flow: Credentials → Token Pair → Session Created

```mermaid
sequenceDiagram
    participant Client as 🌐 Client
    participant Router as 🛣️ Login Router
    participant AuthSvc as ⚙️ AuthService
    participant UserSvc as 👤 UserService
    participant Cache as 🔴 Redis Cache
    participant DB as 🗄️ PostgreSQL

    Client->>Router: POST /auth/login<br/>(email, password)

    Router->>AuthSvc: authenticate(email, password, device_info, ip)

    AuthSvc->>UserSvc: get_user_by_email(email)
    UserSvc->>DB: SELECT * FROM users WHERE email=?
    DB-->>UserSvc: User (with hashed_password)
    UserSvc-->>AuthSvc: User

    AuthSvc->>AuthSvc: verify_password(input, hashed)

    alt ❌ Invalid
        AuthSvc-->>Router: InvalidCredentialsError
        Router-->>Client: 401 Unauthorized
    else ✅ Valid
        AuthSvc->>AuthSvc: Check status ∉ {SUSPENDED, BANNED}

        AuthSvc->>DB: SELECT active sessions (revoked_at IS NULL)

        alt Too many sessions (≥ 5)
            AuthSvc->>DB: Revoke oldest sessions
            AuthSvc->>Cache: delete old session:{id}
        end

        AuthSvc->>AuthSvc: Generate session_id (UUID)
        AuthSvc->>AuthSvc: Create access_token (JWT)
        AuthSvc->>AuthSvc: Create refresh_token (JWT, jti=session_id)

        AuthSvc->>DB: INSERT INTO sessions

        AuthSvc->>Cache: set_json(session:{session_id}, {id,user_id,expires_at,revoked_at}, ttl≈7d)

        AuthSvc-->>Router: TokenPair(access, refresh)
        Router->>Router: Set refresh as httpOnly cookie
        Router-->>Client: 200 OK + tokens + cookie
    end
```

**What's created:**

- Session in DB: `id`, `user_id`, `device_info`, `ip_address`, `created_at`, `expires_at`, `previous_session_id`
- Tokens: access (~30 min), refresh (~7 days)
- Cache: `session:{id}` holds only the validation projection — `id`, `user_id`, `expires_at`, `revoked_at` (TTL = `REFRESH_TOKEN_EXPIRE_DAYS`, ~7 days at login). Forensic/UI metadata stays in the DB and off the hot path.

---

### 2.2 Using a Token: Protected Request with Cache-Aside

```mermaid
sequenceDiagram
    participant Client as 🌐 Client
    participant Router as 🛣️ Protected Route
    participant GetUser as 🔐 get_current_user<br/>(dependency)
    participant Cache as 🔴 Redis
    participant DB as 🗄️ PostgreSQL
    participant Handler as 📊 Route Handler

    Client->>Router: PATCH /api/v1/users/{id}  (example protected route)<br/>Authorization: Bearer {token}

    note over Router,GetUser: 🔄 FastAPI resolves dependencies FIRST

    Router->>GetUser: Resolve Depends(get_current_user)

    GetUser->>GetUser: 1️⃣ decode_token(authorization)
    GetUser->>GetUser: Extract user_id, session_id

    note over GetUser,Cache: 2️⃣ SESSION CACHE-ASIDE
    GetUser->>Cache: get_json(session:{session_id})

    alt 💚 HIT
        Cache-->>GetUser: {...}
    else 🔴 MISS
        GetUser->>DB: SELECT * FROM sessions WHERE id=?
        DB-->>GetUser: SessionModel
        GetUser->>Cache: set_json(session:{id}, {...}, ttl=3600)
    end

    GetUser->>GetUser: Check is_active (not revoked, not expired)

    alt ❌ Invalid
        GetUser-->>Router: InvalidTokenError
        Router-->>Client: 401 Unauthorized
    else ✅ Valid
        note over GetUser,Cache: 3️⃣ USER CACHE-ASIDE
        GetUser->>Cache: get_json(user:{user_id})

        alt 💚 HIT
            Cache-->>GetUser: {...}
            GetUser->>GetUser: Reconstruct User<br/>(NO password)
        else 🔴 MISS
            GetUser->>DB: SELECT * FROM users WHERE id=?
            DB-->>GetUser: UserModel
            GetUser->>Cache: set_json(user:{id}, {id, email, status, role, ...}, ttl=3600)
        end

        GetUser->>GetUser: 4️⃣ Status gate<br/>reject: PENDING_VERIFICATION, SUSPENDED, BANNED

        alt ❌ Invalid
            GetUser-->>Router: InvalidTokenError
            Router-->>Client: 401 Unauthorized
        else ✅ Valid
            GetUser-->>Router: ✅ Return User

            note over Router,Handler: 🟢 NOW handler runs
            Router->>Handler: handler(current_user=<User>)
            Handler->>Handler: Business logic
            Handler-->>Router: Response
            Router-->>Client: 200 OK + data
        end
    end
```

**Cache strategy:**

- `session:{sid}`: 1 hour (authoritative lockout point)
- `user:{uid}`: 1 hour (identity, status, role — safe because session revocation is the real gate)
- Password: **NOT cached** (only needed at login, only read from DB there)

---

### 2.3 Refresh Token Rotation (RTR) with Grace Period & Breach Detection

```mermaid
sequenceDiagram
    participant Client as 🌐 Client
    participant Router as 🛣️ Refresh Router
    participant AuthSvc as ⚙️ AuthService
    participant Cache as 🔴 Redis
    participant DB as 🗄️ PostgreSQL

    Client->>Router: POST /auth/refresh<br/>refresh_token (body or cookie)

    Router->>AuthSvc: refresh_token(TokenRefreshRequest)

    AuthSvc->>AuthSvc: decode_token(refresh_token)<br/>Extract: user_id, session_id

    note over AuthSvc,DB: 1️⃣ AUTHORITATIVE READ (DB, not cache)
    AuthSvc->>DB: SELECT * FROM sessions WHERE id=?

    alt 🔴 Not found
        AuthSvc-->>Router: InvalidTokenError
        Router-->>Client: 401 Unauthorized
    else ⚠️ Revoked
        note over AuthSvc: revoked_ago = now - DB revoked_at
        alt ⏱️ Within 30s grace window
            note over AuthSvc,Cache: Benign concurrent race.<br/>Redis replay is UX-only.
            AuthSvc->>Cache: get_json(grace:{session_id})
            alt 💚 Cached pair present
                Cache-->>AuthSvc: {access, refresh}
                AuthSvc-->>Router: Return cached tokens (no rotation)
                Router-->>Client: 200 OK
            else 🔴 Miss / Redis outage
                AuthSvc-->>Router: InvalidTokenError ("please retry")
                Router-->>Client: 401 Unauthorized
            end
        else 🚨 Outside grace window
            note over AuthSvc: BREACH — genuine token reuse
            AuthSvc->>AuthSvc: logout_all(user_id)
            AuthSvc->>DB: Bulk revoke ALL active sessions
            AuthSvc->>Cache: Delete session:{id}, grace:{id} (each)
            AuthSvc-->>Router: InvalidTokenError
            Router-->>Client: 401 Unauthorized
        end
    else ✅ Active
        AuthSvc->>AuthSvc: Check is_expired
        AuthSvc->>AuthSvc: Validate user status

        note over AuthSvc,DB: 🔄 ATOMIC ROTATION
        AuthSvc->>DB: Revoke old session (set revoked_at=NOW())
        AuthSvc->>Cache: delete(session:{old_id})

        AuthSvc->>AuthSvc: Generate new session_id
        AuthSvc->>AuthSvc: remaining = chain expires_at - now<br/>Create tokens (refresh capped to remaining)

        AuthSvc->>DB: INSERT new session (inherits device_info, prev chain)
        AuthSvc->>DB: commit()

        AuthSvc->>Cache: set(session:{new_id}, {id,user_id,expires_at,revoked_at}, ttl=remaining)
        AuthSvc->>Cache: set(grace:{old_id}, {access,refresh}, ttl=30s)

        AuthSvc-->>Router: TokenPair(new access, new refresh)
        Router->>Router: Set new refresh cookie
        Router-->>Client: 200 OK + new tokens
    end
```

**RTR mechanics:**

- **Authoritative read**: Refresh reads the session row from the DB (not the cache). Rotation is a security-critical write that runs at most once per access-token lifetime, so the DB `revoked_at` is the source of truth.
- **Grace period**: 30-second window to handle benign concurrent retries, **gated on the DB `revoked_at` timestamp** — not on the presence of a Redis key. A Redis outage can therefore never trigger a false `logout_all`.
- **Redis replay**: Within the grace window, Redis is consulted only to return the identical new token pair to a losing concurrent caller. A miss is a safe `401` ("please retry"), never a breach.
- **Breach detection**: A revoked session replayed _outside_ the grace window → genuine reuse → `logout_all` (single atomic bulk revoke).

---

### 2.4 Logout & Automatic Revocation on Status Change

```mermaid
sequenceDiagram
    participant Client as 🌐 Client
    participant LogoutAPI as 📤 POST /logout
    participant ChangeStatusAPI as 👮 PATCH /users/{id}/status<br/>(illustrative — not yet wired)
    participant AuthSvc as ⚙️ AuthService
    participant UserSvc as 👤 UserService
    participant Cache as 🔴 Redis
    participant DB as 🗄️ PostgreSQL

    rect rgb(200, 230, 201)
        note right of Client: Scenario 1: User Initiates Logout
    end

    Client->>LogoutAPI: POST /auth/logout
    LogoutAPI->>AuthSvc: logout(session_id)
    AuthSvc->>DB: Revoke current session (set revoked_at=NOW())
    AuthSvc->>Cache: delete(session:{id})
    AuthSvc->>Cache: delete(grace:{id})
    LogoutAPI-->>Client: 204 No Content + clear cookie

    rect rgb(255, 200, 200)
        note right of Client: Scenario 2: Admin Suspends User<br/>(Automatic Revocation)
    end

    Client->>ChangeStatusAPI: PATCH /users/{uid}/status<br/>new_status: SUSPENDED

    ChangeStatusAPI->>UserSvc: change_status(uid, SUSPENDED)
    UserSvc->>DB: UPDATE users SET status='suspended'

    note over UserSvc: 🔗 Integrated session revocation
    UserSvc->>AuthSvc: session_revoker.revoke_user_sessions(uid)

    AuthSvc->>DB: SELECT all active sessions for user
    AuthSvc->>DB: UPDATE all sessions SET revoked_at=NOW()
    AuthSvc->>Cache: delete(session:{id}) for EACH
    AuthSvc->>Cache: delete(grace:{id}) for EACH

    UserSvc->>DB: commit()
    UserSvc->>Cache: delete(user:{uid})

    ChangeStatusAPI-->>Client: 200 OK + {updated user}

    rect rgb(255, 240, 200)
        note right of Client: When Suspended User Makes Request
    end

    Client->>ChangeStatusAPI: GET protected route<br/>(with old token)
    ChangeStatusAPI->>ChangeStatusAPI: get_current_user() runs

    note over ChangeStatusAPI: SESSION CHECK (authoritative)
    ChangeStatusAPI->>Cache: get_json(session:{id})
    Cache-->>ChangeStatusAPI: null (we deleted it)

    ChangeStatusAPI->>DB: SELECT * FROM sessions WHERE id=?
    DB-->>ChangeStatusAPI: {revoked_at: <timestamp>}

    ChangeStatusAPI->>ChangeStatusAPI: Check is_active<br/>(revoked? YES)
    ChangeStatusAPI-->>Client: ❌ 401 Unauthorized<br/>(BEFORE user cache ever checked)
```

**Key invariant:** Session revocation is the **authoritative lockout point**. Even if user cache is stale, a revoked session blocks everything.

---

## 3. Cache-Aside Pattern Explained

```mermaid
graph LR
    A["Request arrives<br/>for user data"] --> B["Check Redis<br/>get_json('user:{id}')<br/>"]

    B -->|Hit| C["💚 Reconstruct User<br/>from cached dict<br/>(no password)"]
    B -->|Miss| D["Query DB<br/>SELECT * FROM users WHERE id=?"]

    D --> E["Warm cache<br/>set_json('user:{id}', {...}, ttl=3600)"]
    E --> F["🎯 Return User"]
    C --> F

    F --> G["Request #2 (within 1 hour)<br/>Same user"]
    G --> H["Check Redis"]
    H -->|Hit| I["💚 Instant (no DB)"]
    H -->|Miss| J["DB hit (cache expired)"]

    style C fill:#C8E6C9
    style D fill:#FFCDD2
    style I fill:#A5D6A7
    style J fill:#FFB6C1
```

**Two keys involved:**

| Key             | Created By               | Cleared By                                  | TTL                                                                                      | Purpose                            |
| --------------- | ------------------------ | ------------------------------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------- |
| `session:{sid}` | login, refresh           | logout, logout_all, revocation, suspend/ban | ~7d at login; `remaining_ttl` on refresh; **3600s** when re-warmed by `get_current_user` | Session state & lockout            |
| `user:{uid}`    | get_current_user on miss | update_user, change_status, delete_user     | 1 hour                                                                                   | Identity (id, email, status, role) |

**Why no password hash in cache?** Only needed at login (read straight from DB). Caching it increases Redis exposure with zero benefit.

---

## 4. Why Caching Identity Is Secure

Even though `user:{id}` can be stale for up to 1 hour, it cannot keep a revoked user authenticated:

```mermaid
graph TD
    A["Admin suspends user"] --> B["change_status(SUSPENDED)"]

    B --> C["UPDATE users SET status='suspended'"]
    C --> D["🔗 Integrated: revoke_user_sessions()"]

    D --> E["Revoke ALL active sessions"]
    E --> F["DELETE session:{id} from cache"]
    E --> G["DELETE grace:{id} from cache"]
    E --> H["commit()"]

    H --> I["⏱️ User makes request with old token"]

    I --> J["get_current_user() runs"]
    J --> K["🔐 SESSION CHECK<br/>(authoritative point)"]

    K --> L["get_json(session:{id})"]
    L -->|Miss| M["Query DB"]
    M --> N["Found: revoked_at=<timestamp>"]

    N --> O["is_active = FALSE"]
    O --> P["❌ 401 Unauthorized<br/>(request rejected)"]
    P -->|Before user cache checked| Q["Even if user cache<br/>says ACTIVE, session<br/>revocation blocks it"]

    style K fill:#FFE082
    style P fill:#EF5350
    style Q fill:#E8F5E9
```

**Why this works:**

1. Session revocation is **immediate** (same transaction as status change)
2. Session cache is **deleted**
3. Session is checked **before** user status
4. Stale user cache cannot override revoked session

---

## 5. Request Lifecycle Diagram (Dependency Resolution → Handler)

```mermaid
graph TD
    A["HTTP Request<br/>protected route + Depends(get_current_user)<br/>Authorization: Bearer token"] -->|FastAPI router| B["Route declares<br/>Depends(get_current_user)"]

    B --> C["🔄 DEPENDENCY RESOLUTION PHASE<br/>(before handler runs)"]

    C --> D["FastAPI builds dependency chain:"]
    D --> D1["get_async_session()"]
    D --> D2["get_cache_client()"]
    D --> D3["get_auth_repository()"]
    D --> D4["get_user_service()"]

    D1 --> E["✅ All dependencies ready"]
    D2 --> E
    D3 --> E
    D4 --> E

    E --> F["get_current_user() EXECUTES<br/>(with all injected deps)"]

    F --> G["Step 1: Decode JWT"]
    G --> G1{Valid?}
    G1 -->|No| Z["❌ 401"]
    G1 -->|Yes| H["Step 2: SESSION cache-aside<br/>get(session:{sid})"]

    H --> H1{Cache?}
    H1 -->|Hit| H2["Load from cache"]
    H1 -->|Miss| H3["Load from DB<br/>Warm cache"]

    H2 --> H4["Check is_active"]
    H3 --> H4
    H4 --> H5{Valid?}
    H5 -->|No| Z
    H5 -->|Yes| I["Step 3: USER cache-aside<br/>get(user:{uid})"]

    I --> I1{Cache?}
    I1 -->|Hit| I2["Load from cache"]
    I1 -->|Miss| I3["Load from DB<br/>Warm cache"]

    I2 --> J["Step 4: Status gate<br/>Check: not PENDING/SUSPENDED/BANNED"]
    I3 --> J
    J --> J1{Valid?}
    J1 -->|No| Z
    J1 -->|Yes| K["✅ Return User"]

    K --> L["🟢 HANDLER EXECUTION PHASE<br/>(now handler body runs)"]
    L --> M["handler(current_user=<User>)"]
    M --> N["Business logic"]
    N --> O["Return response"]
    O --> P["✅ 200 OK"]

    Z --> Q["❌ Return error"]

    style C fill:#FFF3E0
    style F fill:#F3E5F5
    style H fill:#E8F5E9
    style I fill:#E8F5E9
    style L fill:#FFF9C4
    style P fill:#C8E6C9
    style Z fill:#FFCDD2
```

---

## 6. Performance: Cache Hits Save DB Queries

```mermaid
graph LR
    subgraph "Request #1 — Cache MISS (cold start)"
        direction TB
        A1["🚀 Decode JWT"]
        A2["🔴 session cache MISS"]
        A3["💾 DB query: session"]
        A4["✅ Warm session cache"]
        A5["🔴 user cache MISS"]
        A6["💾 DB query: user"]
        A7["✅ Warm user cache"]
        A8["🟢 Handler runs"]
        A1 --> A2 --> A3 --> A4 --> A5 --> A6 --> A7 --> A8
    end

    subgraph "Request #2 — Cache HIT (within TTL)"
        direction TB
        B1["🚀 Decode JWT"]
        B2["💚 session HIT (Redis)"]
        B3["💚 user HIT (Redis)"]
        B4["🟢 Handler runs"]
        B1 --> B2 --> B3 --> B4
    end

    subgraph "Cost comparison"
        C1["Request #1\n2 DB queries\n~10ms"]
        C2["Request #2\n0 DB queries\n~3ms ⚡"]
    end

    style A3 fill:#FFCDD2
    style A6 fill:#FFCDD2
    style B2 fill:#C8E6C9
    style B3 fill:#C8E6C9
    style C1 fill:#FFF9C4
    style C2 fill:#A5D6A7
```

|                | Request #1 (cold)     | Request #2+ (warm) |
| -------------- | --------------------- | ------------------ |
| Session lookup | DB query + warm cache | Redis hit only     |
| User lookup    | DB query + warm cache | Redis hit only     |
| DB queries     | 2                     | 0                  |
| Relative speed | baseline              | ~3x faster         |

> Numbers are illustrative. Actual latency depends on Redis/DB network conditions.

---

## 7. State Machine: Complete Authentication States

```mermaid
stateDiagram-v2
    [*] --> Unauthenticated

    Unauthenticated --> LoginCreds: User submits email/pwd

    LoginCreds --> InvalidCreds: ❌ Mismatch
    LoginCreds --> UserSuspended: ❌ Status=SUSPENDED
    LoginCreds --> UserBanned: ❌ Status=BANNED

    InvalidCreds --> Unauthenticated
    UserSuspended --> Unauthenticated
    UserBanned --> Unauthenticated

    LoginCreds --> Authenticated: ✅ Valid + Status OK

    Authenticated --> AccessTokenIssued: JWT tokens created
    AccessTokenIssued --> SessionCreated: Session in DB + cache
    SessionCreated --> CanUseToken: Ready for requests

    CanUseToken --> ProtectedRoute: any Depends(get_current_user) route
    ProtectedRoute --> SessionValid: get_current_user()
    SessionValid --> UserStatusValid: Not SUSPENDED/BANNED
    UserStatusValid --> RequestGranted: ✅ 200 OK

    RequestGranted --> CanUseToken

    CanUseToken --> AccessExpired: JWT expired
    AccessExpired --> RefreshFlow: Use refresh token

    RefreshFlow --> GracePeriod: Revoked < 30s ago? (DB ts)
    GracePeriod --> ReturnCached: ✅ Replay cached pair (or 401 retry)
    GracePeriod --> RotateToken: Active session, do rotation

    RotateToken --> RevokeOld: Mark old revoked
    RevokeOld --> CreateNew: New session + tokens
    CreateNew --> CanUseToken

    RefreshFlow --> TokenReuse: ⚠️ Replayed after revoke
    TokenReuse --> BreachDetected: 🚨 Breach!
    BreachDetected --> RevokeAll: Revoke ALL sessions
    RevokeAll --> ForceLogout: Global logout
    ForceLogout --> Unauthenticated

    CanUseToken --> UserLogout: POST /logout
    UserLogout --> RevokeSession: Mark session revoked
    RevokeSession --> ClearCache: Delete caches
    ClearCache --> Unauthenticated

    CanUseToken --> AdminAction: Admin suspends user
    AdminAction --> AutoRevokeAll: Revoke all sessions
    AutoRevokeAll --> Unauthenticated

    note right of BreachDetected
        RTR Breach Detection:
        Stale token used after rotation
        = likely compromise
    end note

    note right of ForceLogout
        All sessions revoked immediately
        User locked out everywhere
    end note
```

---

## 8. Key Invariants & Safety Properties

### Invariant 1: Session Revocation is Authoritative

- Even if user cache is stale, a revoked session blocks access
- Revocation is immediate (same transaction as status change)
- Cache is deleted to ensure DB is read on next attempt

### Invariant 2: Password Never Cached

- Password hash only needed at login
- Never read in authenticated request path
- Reduces Redis exposure surface

### Invariant 3: Grace Period Prevents Storms

- 30-second window for benign concurrent retry detection, gated on the DB `revoked_at` timestamp
- Redis is a UX optimization only; a miss yields a safe 401, never a false breach
- Prevents rotation loops from network retries

### Invariant 4: Per-Request Services Are Safe

- Services hold no request-scoped state
- Shared resources (Redis, DB pool) are singletons
- Service instantiation cost is negligible

---

## 9. Known wrinkle / future cleanup

The cache-aside **mechanics** for the user currently live inline inside
`get_current_user` (`modules/auth/authentication.py`). That's business/data-access
logic in the wrong layer. The cleaner design is to move it into `UserService`:

```python
# users/service.py  (proposed)
async def get_user_by_id_cached(self, user_id: str) -> User | None:
    """Fetch a user by ID with cache-aside."""
    ...
```

Then `get_current_user` stays a thin guard:

```python
user = await user_service.get_user_by_id_cached(user_id)
```

The call site does not change — `get_current_user` is still the per-request entry
point routes inject. Only the responsibility for the cache read/write moves down
into the service layer where data access belongs.

---

## TL;DR — Quick Reference

| Component             | Lifetime    | When Created          | When Destroyed                                                                 |
| --------------------- | ----------- | --------------------- | ------------------------------------------------------------------------------ |
| `CacheClient`         | Singleton   | Server startup        | Server shutdown                                                                |
| `SQLAlchemy Engine`   | Singleton   | Server startup        | Server shutdown                                                                |
| `AsyncSession`        | Per-request | Request start         | Request end                                                                    |
| `UserService`         | Per-request | Dependency resolution | Request end                                                                    |
| `session:{sid}` cache | TTL         | Login/refresh         | Logout/revoke; else ~7d (login), `remaining_ttl` (refresh), or 3600s (re-warm) |
| `user:{uid}` cache    | TTL         | First access          | Invalidation or 1 hour                                                         |
| `grace:{sid}` cache   | TTL         | Rotation              | Grace timeout or 30s                                                           |

**Flow summary:**

1. Client sends request with token
2. FastAPI resolves dependencies (cheap, no I/O)
3. `get_current_user` runs: decode token → session check (cache-aside) → user check (cache-aside) → status gate
4. Handler runs with validated `User`
5. Response sent
6. Service instance garbage-collected, caches remain in Redis
7. Next request reuses warm caches (fast, no DB)
