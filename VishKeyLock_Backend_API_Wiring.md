# VishKeyLock / mSafe Backend → Android App Wiring Specification

**Generated from the backend files supplied in this conversation.**

> Scope: Django REST Framework backend, Manager App, Owner App, DPC/User App, FCM command layer, device telemetry, uploads, and deployment configuration.

---

## 1. Backend architecture

### Main API base

Production host configured in the backend:

`https://api.msafe.shop`

The Django URL configuration exposes:

| Area | Base path |
|---|---|
| Authentication | `/api/auth/` |
| Owner App | `/api/owner/` |
| Manager App | `/api/manager/` |
| Users/domain APIs | `/api/` |
| DPC/system APIs | `/api/system/` |
| Admin | `/admin/` |
| Agent APK | `/download/msafe-agent.apk` |

Manager QR provisioning embeds this APK URL:

`https://api.msafe.shop/api/manager/download/msafe-agent.apk`

---

# 2. Authentication

## JWT

Configured globally through DRF:

- Authentication: `JWTAuthentication`
- Access token lifetime: **60 minutes**
- Refresh token lifetime: **7 days**
- Default permission: authenticated users

### Login

`POST /api/auth/token/`

Expected to be handled by:

`CustomTokenObtainPairView`

The exact request/response serializer was not included in the supplied files, so the Android implementation should follow the actual `users.views.CustomTokenObtainPairView` response once that file is available.

Typical JWT flow:

```text
Android Login
    ↓
POST /api/auth/token/
    ↓
access + refresh
    ↓
Authorization: Bearer <access>
    ↓
API requests
```

### Refresh

`POST /api/auth/token/refresh/`

Used when the access token expires.

### Android token storage

Store:

- `access`
- `refresh`

Use:

```http
Authorization: Bearer <access_token>
```

Do not put JWT tokens in URLs.

---

# 3. Roles

The backend effectively has:

### Owner

Identified by:

- `IsOwner` permission (implementation not supplied)
- superuser behavior exists elsewhere
- owner profile
- owner APIs

### Manager

Identified by:

```python
hasattr(request.user, "manager_profile")
```

through `IsManager`.

### DPC/device

System device endpoints currently use `AllowAny`, with a device-specific `X-DEVICE-TOKEN` only enforced by the heartbeat endpoint.

---

# 4. OWNER APP API MAP

Base:

`/api/owner/`

Authentication:

```http
Authorization: Bearer <owner_access_token>
```

---

## 4.1 List all users

`GET /api/owner/users/`

Permission:

- authenticated
- owner

Returns customers across managers.

Supports search:

```text
?search=<name>
?search=<phone>
?search=<imei>
?search=<manager_username>
```

Ordering fields:

```text
?ordering=created_at
?ordering=name
```

### Android use

Owner dashboard / all-users screen.

---

## 4.2 Get one user

`GET /api/owner/users/{id}/`

Permission: Owner

Use for user/device detail screen.

---

## 4.3 User share text

`GET /api/owner/users/{id}/share_text/`

Returns:

```json
{
  "text": "User Details:\nName: ...\nPhone: ...\nManager: ...\nIMEI1: ..."
}
```

The generated text can contain:

- customer name
- phone
- manager username
- IMEI1
- IMEI2
- SIM1
- SIM2
- Google Maps location URL

### Android use

Owner → User Details → Share / WhatsApp.

---

# 5. OWNER MANAGER API

Base:

`/api/owner/managers/`

This is a `ModelViewSet`.

### Available standard routes

```text
GET     /api/owner/managers/
POST    /api/owner/managers/
GET     /api/owner/managers/{id}/
PUT     /api/owner/managers/{id}/
PATCH   /api/owner/managers/{id}/
DELETE  /api/owner/managers/{id}/
```

Permission: Owner.

---

## 5.1 Create manager

`POST /api/owner/managers/`

Manager serializer accepts:

```json
{
  "username": "manager1",
  "password": "password",
  "email": "manager@example.com",
  "phone": "9999999999",
  "photo": "<file>",
  "default_lock_message": "Device locked.",
  "default_lock_logo": "<file>"
}
```

Response includes:

```text
id
username
email
phone
photo
default_lock_message
default_lock_logo
total_keys
used_keys
keys_remaining
```

`total_keys`, `used_keys`, and `keys_remaining` are read-only in `ManagerProfileSerializer`.

---

## 5.2 List managers

`GET /api/owner/managers/`

Use for Owner → Managers.

---

## 5.3 Manager details

`GET /api/owner/managers/{id}/`

---

## 5.4 Update manager

`PUT /api/owner/managers/{id}/`

or

`PATCH /api/owner/managers/{id}/`

---

## 5.5 Delete manager

`DELETE /api/owner/managers/{id}/`

Important: deleting the manager profile may cascade to its Django user depending on the actual user/profile relationships. Verify before exposing this as a destructive Owner UI action.

---

# 6. OWNER FORCE UNENROLL

`POST /api/owner/users/{id}/force_delete/`

Permission:

- authenticated
- owner

### Successful response

```json
{
  "detail": "Force unenroll queued.",
  "audit_log_id": 123
}
```

### Flow

```text
Owner App
  ↓
POST force_delete
  ↓
Device → DPC_STATUS_UNENROLL_PENDING
  ↓
AuditLog created
  ↓
FcmCommand(UNENROLL)
  ↓
Celery
  ↓
FCM
  ↓
DPC
  ↓
ACK
  ↓
reconcile_command_ack_task
  ↓
Device becomes UNENROLLED
Customer becomes inactive
```

This is an asynchronous operation. The Android UI should show **pending**, not immediately assume deletion succeeded.

---

# 7. OWNER PROFILE

`GET /api/owner/profile/`

Permission: authenticated.

Response:

```json
{
  "id": 1,
  "username": "owner",
  "phone": "9999999999",
  "photo": "/media/owners/photos/..."
}
```

---

# 8. OWNER FCM DEVICE REGISTRATION

A view exists:

`OwnerRegisterDeviceView`

with intended endpoint:

`POST /api/owner/devices/register/`

Expected body:

```json
{
  "fcm_token": "<firebase-token>",
  "platform": "android"
}
```

Response:

```json
{
  "id": 1,
  "fcm_token": "...",
  "platform": "android",
  "is_active": true
}
```

### IMPORTANT

The supplied `owner.urls` **does not wire `OwnerRegisterDeviceView`**.

Therefore this endpoint is currently **not reachable through the supplied URL configuration** unless another URL file wires it.

This must be fixed before Owner push notifications can reliably register the Owner App.

---

# 9. MANAGER APP API MAP

Base:

`/api/manager/`

Authentication:

```http
Authorization: Bearer <manager_access_token>
```

---

# 10. MANAGER CUSTOMERS / USERS

Router:

```text
/api/manager/users/
```

ViewSet:

`ManagerCustomerViewSet`

Permissions:

- authenticated
- manager
- manager-of-customer

---

## 10.1 List manager users

`GET /api/manager/users/`

Only active customers belonging to the logged-in manager are returned.

Search fields:

```text
name
phone
device__imei1
device__imei2
```

Ordering:

```text
created_at
name
```

Android use:

Manager → Customers list.

---

## 10.2 Create customer

`POST /api/manager/users/`

This is the most important Manager enrollment endpoint.

Before creation:

```text
keys_remaining > 0
```

Otherwise:

```http
400
{
  "detail": "No enrollment keys left."
}
```

On successful creation:

1. Customer is created.
2. Enrollment token is generated.
3. Token is associated with customer.
4. Manager `used_keys` is incremented.
5. QR enrollment data is returned.

Response shape:

```json
{
  "customer": {
    "...": "CustomerSerializer response"
  },
  "enrollment": {
    "token": "...",
    "manager_id": 123,
    "imei1": "123456789012345"
  }
}
```

### Android flow

```text
Manager checks keys
       ↓
Create User form
       ↓
POST /api/manager/users/
       ↓
customer + enrollment token
       ↓
Generate/show enrollment QR
       ↓
Factory reset target phone
       ↓
Android provisioning
       ↓
DPC installed
       ↓
DPC registers device
```

---

# 11. MANAGER USER DETAIL

`GET /api/manager/users/{id}/`

Returns a manager-owned customer.

---

# 12. MANAGER USER UPDATE

`PUT /api/manager/users/{id}/`

or

`PATCH /api/manager/users/{id}/`

Uses:

`CustomerCreateUpdateSerializer`

---

# 13. MANAGER USER DELETE

The standard `ModelViewSet` exposes:

`DELETE /api/manager/users/{id}/`

However, the supplied custom business flow for removing a device is **not this route**.

For DPC removal, use:

`POST /api/manager/users/{id}/delete_user/`

The Android app should not assume normal REST DELETE means "unenroll DPC".

---

# 14. MANAGER QR PNG

`GET /api/manager/users/{id}/qr_png/`

Permission:

- authenticated
- manager
- manager owns customer

Requires a linked device and an enrollment token.

Returns:

```text
image/png
```

### QR payload

The QR contains Android provisioning properties including:

```json
{
  "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME":
    "com.vashu.msafe.agent/.AdminReceiver",

  "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION":
    "https://api.msafe.shop/api/manager/download/msafe-agent.apk",

  "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM":
    "<APK SHA-256>",

  "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
    "token": "<enrollment-token>",
    "manager_id": 123,
    "imei1": "..."
  }
}
```

### DPC wiring requirement

The Android DPC package/component must exactly match:

```text
com.vashu.msafe.agent/.AdminReceiver
```

If the actual Android package/component differs, provisioning will fail.

---

# 15. MANAGER LOCK

`POST /api/manager/users/{id}/lock/`

Optional body:

```json
{
  "message": "Your device is locked.",
  "logo_url": "https://..."
}
```

If `message` is missing, manager's:

`default_lock_message`

is used.

### Response

```http
202
{
  "detail": "Lock command queued."
}
```

### Important

`202 Accepted` means the command was queued, **not that the phone is already locked**.

### Flow

```text
Manager App
 ↓
POST lock
 ↓
Device.lock_status = PENDING_LOCK
 ↓
AuditLog(PENDING)
 ↓
FcmCommand(LOCK)
 ↓
Celery
 ↓
FCM
 ↓
DPC
 ↓
DPC sends ACK
 ↓
/api/system/devices/ack/
 ↓
reconcile task
 ↓
Device.lock_status = LOCKED
 ↓
Manager + Owner notification
```

---

# 16. MANAGER UNLOCK

`POST /api/manager/users/{id}/unlock/`

Response:

```json
{
  "detail": "Unlock command queued."
}
```

Status:

`202 Accepted`

Final state is determined only after DPC ACK.

---

# 17. MANAGER UNENROLL / DELETE USER

`POST /api/manager/users/{id}/delete_user/`

Response:

```json
{
  "detail": "Unenroll command queued."
}
```

Status:

`202 Accepted`

The DPC receives:

```text
action = UNENROLL
forced_by_owner = false
```

After successful ACK:

```text
DPC status → UNENROLLED
lock status → UNLOCKED
customer.is_active → false
```

---

# 18. MANAGER PROFILE

Router:

`/api/manager/profile/`

### GET

`GET /api/manager/profile/`

Returns:

```json
{
  "id": 1,
  "username": "...",
  "email": "...",
  "phone": "...",
  "photo": "...",
  "default_lock_message": "...",
  "default_lock_logo": "...",
  "total_keys": 100,
  "used_keys": 10,
  "keys_remaining": 90
}
```

### PATCH

The ViewSet implements:

`PATCH /api/manager/profile/{pk}/`

The `pk` is effectively ignored because `get_object()` always returns the logged-in manager profile.

For Android, use the actual profile ID returned by GET, but the backend implementation should ideally be changed to a clean `/profile/` update endpoint.

---

# 19. MANAGER FCM REGISTRATION

A view exists:

`ManagerRegisterDeviceView`

Intended body:

```json
{
  "fcm_token": "<firebase-token>"
}
```

Response:

```json
{
  "detail": "Manager device registered.",
  "manager_id": 1,
  "fcm_token": "..."
}
```

### IMPORTANT

The supplied `manager.urls` **does not include `ManagerRegisterDeviceView`**.

Therefore this endpoint is currently unreachable from the shown URL configuration.

This must be wired before Manager App push notifications can reliably register its FCM token.

---

# 20. MANAGER DASHBOARD

`GET /api/manager/dashboard/`

Returns an array:

```json
[
  {
    "device_id": "IMEI1",
    "customer": "Customer Name",
    "phone": "9999999999",
    "battery": 75,
    "online": true,
    "lock_status": "...",
    "location": {
      "lat": 22.123,
      "lng": 75.123,
      "time": "..."
    }
  }
]
```

### Android use

Manager Dashboard:

- user count
- online/offline
- battery
- location
- lock status

---

# 21. MANAGER DEVICE MAP

`GET /api/manager/devices/map/`

Returns:

```json
[
  {
    "imei": "...",
    "name": "...",
    "phone": "...",
    "lat": 22.123,
    "lng": 75.123,
    "battery": 80,
    "online": true
  }
]
```

### Android use

Map screen.

---

# 22. DPC / SYSTEM API

Base:

`/api/system/`

These endpoints are intended for the DPC/device agent.

---

# 23. HEALTH

`GET /api/system/health/`

Permission:

`AllowAny`

Response:

```json
{
  "status": "ok",
  "time": "...",
  "fcm_commands": {
    "pending": 0,
    "sent": 0,
    "acked": 0,
    "failed": 0
  }
}
```

Useful for:

- server health screen
- debugging
- monitoring

---

# 24. DPC DEVICE REGISTRATION

`POST /api/system/devices/register/`

Permission:

`AllowAny`

Body:

```json
{
  "imei_1": "123456789012345",
  "imei_2": "123456789012346",
  "device_id": "unique-device-id",
  "fcm_token": "firebase-token"
}
```

Required:

- `imei_1`
- `device_id`
- `fcm_token`

Response:

```json
{
  "registered": true,
  "device_id": "...",
  "device_token": "..."
}
```

### Critical

The returned:

```text
device_token
```

must be securely stored by the DPC.

Heartbeat uses:

```http
X-DEVICE-TOKEN: <device_token>
```

---

# 25. DPC HEARTBEAT

`POST /api/system/devices/heartbeat/`

Permission:

`AllowAny`

Required:

```http
X-DEVICE-TOKEN: <device_token>
```

Body:

```json
{
  "device_id": "...",
  "battery": 80,
  "network": "wifi",
  "android_version": "14",
  "charging": true
}
```

Response:

```json
{
  "status": "ok"
}
```

The server updates:

- last_seen
- IP
- battery
- network
- Android version
- charging state
- Redis online state

Online cache expires after:

`120 seconds`

### DPC recommendation

Heartbeat more frequently than 120 seconds if the Android app is expected to appear continuously online.

---

# 26. DPC LOCATION

`POST /api/system/devices/location/`

Body is validated by:

`LocationPingSerializer`

The expected model fields include:

```json
{
  "device": "<device reference>",
  "latitude": 22.123456,
  "longitude": 75.123456,
  "accuracy_m": 5.5,
  "sim_numbers": [],
  "captured_at": "2026-08-08T10:00:00Z"
}
```

After saving, backend updates:

- last latitude
- last longitude
- last location time

and Redis:

```text
device_location:<device_id>
```

### IMPORTANT SECURITY GAP

This endpoint is `AllowAny` and the shown view does not verify `X-DEVICE-TOKEN`.

The DPC should not rely on this endpoint as currently written for secure device authentication. Backend hardening is recommended.

---

# 27. DPC COMMAND ACK

`POST /api/system/devices/ack/`

Permission:

`AllowAny`

Request:

```json
{
  "action": "LOCK",
  "command_id": 123,
  "fcm_message_id": "...",
  "status": "SUCCESS",
  "payload": {
    "details": "..."
  }
}
```

`command_id` OR `fcm_message_id` can identify the command.

Response:

```json
{
  "ok": true
}
```

### ACK flow

```text
DPC executes command
       ↓
POST /api/system/devices/ack/
       ↓
CommandAck created
       ↓
Celery reconcile task
       ↓
Domain state updated
       ↓
Manager + Owner notification
```

---

# 28. DPC LOCK ACK RESULT

When:

```text
action = LOCK
status = SUCCESS
```

Backend sets:

```text
Device.lock_status = LOCKED
```

Failure results in:

```text
Device.lock_status = UNLOCKED
```

---

# 29. DPC UNLOCK ACK RESULT

Success:

```text
Device.lock_status = UNLOCKED
```

Failure:

```text
Device.lock_status = LOCKED
```

---

# 30. DPC UNENROLL ACK RESULT

Success:

```text
Device.dpc_status = UNENROLLED
Device.lock_status = UNLOCKED
Customer.is_active = false
```

Failure:

```text
Device.dpc_status = ENROLLED
```

---

# 31. FILE UPLOAD / S3 PRESIGN

`GET /api/system/uploads/presign/`

or

`POST /api/system/uploads/presign/`

Permission:

- authenticated
- owner or manager

Request:

```json
{
  "filename": "logo.png",
  "content_type": "image/png"
}
```

Response:

```json
{
  "url": "...",
  "fields": {
    "...": "..."
  }
}
```

The generated upload key is:

```text
uploads/YYYY/MM/DD/<uuid>.<extension>
```

Maximum upload size:

**20 MB**

### Android upload flow

```text
Android
 ↓
GET/POST presign
 ↓
receive url + fields
 ↓
multipart POST directly to S3
 ↓
save/use resulting object URL/key
```

---

# 32. APK DOWNLOAD

Two routes are present.

### Public root route

`GET /download/msafe-agent.apk`

### Manager route

`GET /api/manager/download/msafe-agent.apk`

Both call `download_agent`.

Expected file:

```text
download/msafe-agent.apk
```

Response:

```text
application/vnd.android.package-archive
```

---

# 33. QR → DPC COMPLETE PROVISIONING FLOW

The intended full flow is:

```text
OWNER
  │
  ├── creates manager
  │
  └── allocates enrollment keys
          │
          ▼
MANAGER APP
  │
  ├── login
  ├── check keys_remaining
  ├── create customer
  │       │
  │       └── EnrollmentToken generated
  │
  └── GET qr_png
          │
          ▼
       QR CODE
          │
          ▼
TARGET ANDROID PHONE
  │
  ├── factory reset
  ├── scan provisioning QR
  ├── download msafe-agent.apk
  ├── install Device Owner
  └── AdminReceiver receives:
       token
       manager_id
       imei1
          │
          ▼
DPC
  │
  ├── register
  │    POST /api/system/devices/register/
  │
  ├── save device_token
  │
  ├── heartbeat
  │
  ├── location
  │
  └── FCM command handling
          │
          ▼
BACKEND
```

---

# 34. LOCK FLOW

```text
Manager/Owner
    │
    │ POST lock
    ▼
Backend
    │
    ├── PENDING_LOCK
    ├── AuditLog
    ├── FcmCommand(LOCK)
    └── Celery task
          │
          ▼
       Firebase FCM
          │
          ▼
         DPC
          │
          ├── enforce kiosk/lock
          └── ACK SUCCESS
                  │
                  ▼
        /api/system/devices/ack/
                  │
                  ▼
       reconcile_command_ack_task
                  │
                  ├── LOCKED
                  ├── AuditLog SUCCESS
                  └── notification
```

---

# 35. UNLOCK FLOW

Same architecture:

```text
Manager
 ↓
POST /api/manager/users/{id}/unlock/
 ↓
PENDING_UNLOCK
 ↓
FcmCommand(UNLOCK)
 ↓
Celery
 ↓
FCM
 ↓
DPC
 ↓
ACK
 ↓
Device = UNLOCKED
```

---

# 36. UNENROLL FLOW

```text
Manager
 ↓
POST /api/manager/users/{id}/delete_user/

OR

Owner
 ↓
POST /api/owner/users/{id}/force_delete/

 ↓
DPC_STATUS_UNENROLL_PENDING
 ↓
FcmCommand(UNENROLL)
 ↓
FCM
 ↓
DPC
 ↓
ACK SUCCESS
 ↓
DPC_STATUS_UNENROLLED
Customer.is_active = false
```

---

# 37. FCM COMMAND MODEL

Supported actions:

```text
LOCK
UNLOCK
UNENROLL
MESSAGE
LOCATION
REBOOT
PLAY_SOUND
```

Current Manager/Owner views explicitly create:

```text
LOCK
UNLOCK
UNENROLL
```

The other actions exist in the model but are not exposed by the supplied Owner/Manager API views.

---

# 38. FCM COMMAND STATUS

```text
PENDING
   ↓
SENT
   ↓
ACKED
```

Failure:

```text
PENDING/SENT
   ↓
FAILED
```

Commands retry through Celery.

Maximum retries in `send_fcm_command_task`:

**5**

---

# 39. DEVICE REGISTRATION MODEL

Important fields:

```text
id
user
manager_id
imei_1
imei_2
device_id
fcm_token
device_token
last_seen
last_ip
battery_level
network_type
android_version
is_charging
last_latitude
last_longitude
last_location_time
is_active
created_at
updated_at
```

Android DPC should maintain:

```text
device_id
imei_1
imei_2
fcm_token
device_token
```

---

# 40. MANAGER PROFILE DATA

```text
user
phone
photo
default_lock_message
default_lock_logo
total_keys
used_keys
fcm_token
```

Computed:

```text
keys_remaining = total_keys - used_keys
```

---

# 41. OWNER DEVICE MODEL

Stores:

```text
user
fcm_token
platform
is_active
```

Intended for Owner App push registration.

---

# 42. LOCATION DATA

`LocationPing` stores:

```text
device
latitude
longitude
accuracy_m
sim_numbers
captured_at
received_at
```

Current/latest location is also cached in Redis.

---

# 43. IMPORTANT ANDROID DATA MODELS

## Auth

```text
LoginRequest
    username
    password

TokenResponse
    access
    refresh
```

---

## Manager profile

```text
ManagerProfile
    id
    username
    email
    phone
    photo
    default_lock_message
    default_lock_logo
    total_keys
    used_keys
    keys_remaining
```

---

## Enrollment response

```text
CreateCustomerResponse
    customer
    enrollment:
        token
        manager_id
        imei1
```

---

## Device dashboard

```text
DashboardDevice
    device_id
    customer
    phone
    battery
    online
    lock_status
    location
```

---

## Map device

```text
MapDevice
    imei
    name
    phone
    lat
    lng
    battery
    online
```

---

## DPC registration

```text
DeviceRegisterRequest
    imei_1
    imei_2
    device_id
    fcm_token

DeviceRegisterResponse
    registered
    device_id
    device_token
```

---

## Heartbeat

```text
HeartbeatRequest
    device_id
    battery
    network
    android_version
    charging
```

---

## ACK

```text
CommandAckRequest
    action
    command_id
    fcm_message_id
    status
    payload
```

---

# 44. API → ANDROID SCREEN MAPPING

## Owner App

| Android screen/action | API |
|---|---|
| Login | `POST /api/auth/token/` |
| Refresh session | `POST /api/auth/token/refresh/` |
| Owner profile | `GET /api/owner/profile/` |
| Managers | `GET /api/owner/managers/` |
| Create manager | `POST /api/owner/managers/` |
| Manager detail | `GET /api/owner/managers/{id}/` |
| Edit manager | `PATCH /api/owner/managers/{id}/` |
| Delete manager | `DELETE /api/owner/managers/{id}/` |
| All users | `GET /api/owner/users/` |
| User detail | `GET /api/owner/users/{id}/` |
| Share user | `GET /api/owner/users/{id}/share_text/` |
| Force unenroll | `POST /api/owner/users/{id}/force_delete/` |
| Register Owner FCM | **Not currently wired** |

---

## Manager App

| Android screen/action | API |
|---|---|
| Login | `POST /api/auth/token/` |
| Refresh | `POST /api/auth/token/refresh/` |
| Profile | `GET /api/manager/profile/` |
| Update profile | `PATCH /api/manager/profile/{id}/` |
| Customer list | `GET /api/manager/users/` |
| Search customer | `GET /api/manager/users/?search=...` |
| Create customer | `POST /api/manager/users/` |
| Customer detail | `GET /api/manager/users/{id}/` |
| Edit customer | `PATCH /api/manager/users/{id}/` |
| Generate QR | `GET /api/manager/users/{id}/qr_png/` |
| Lock | `POST /api/manager/users/{id}/lock/` |
| Unlock | `POST /api/manager/users/{id}/unlock/` |
| Unenroll | `POST /api/manager/users/{id}/delete_user/` |
| Dashboard | `GET /api/manager/dashboard/` |
| Map | `GET /api/manager/devices/map/` |
| Register Manager FCM | **Not currently wired** |

---

## DPC/User App

| DPC action | API |
|---|---|
| Register device | `POST /api/system/devices/register/` |
| Heartbeat | `POST /api/system/devices/heartbeat/` |
| Send location | `POST /api/system/devices/location/` |
| ACK command | `POST /api/system/devices/ack/` |
| Receive LOCK | FCM data message |
| Receive UNLOCK | FCM data message |
| Receive UNENROLL | FCM data message |
| Receive MESSAGE | Model supports it, API command creation not supplied |
| Receive REBOOT | Model supports it, API command creation not supplied |
| Receive PLAY_SOUND | Model supports it, API command creation not supplied |

---

# 45. FCM DATA MESSAGE FORMAT

`send_fcm_command_task` sends data containing:

```json
{
  "action": "LOCK",
  "command_id": 123,
  "user_id": 5,
  "device_id": "device-id",
  "imei_1": "123456789012345",
  "payload": {
    "audit_log_id": 10,
    "customer_id": 20,
    "device_id": 30,
    "manager_id": 4,
    "message": "Device locked",
    "logo_url": "https://..."
  }
}
```

### DPC must parse

At minimum:

```text
action
command_id
device_id
payload
```

---

# 46. LOCK UI PAYLOAD

Manager lock sends:

```json
{
  "message": "...",
  "logo_url": "..."
}
```

The DPC lock screen should therefore be capable of displaying:

- custom message
- custom logo

If no custom message is supplied, backend uses manager default message.

---

# 47. REDIS

Redis is used for:

### Online state

```text
device_online:<device_id>
```

TTL:

`120 seconds`

### Location

```text
device_location:<device_id>
```

TTL:

`600 seconds`

Android does not communicate with Redis directly.

---

# 48. CELERY

Backend asynchronous processing requires Celery.

Used for:

- FCM command sending
- FCM retries
- ACK reconciliation
- stale command retry

The Android apps only interact with the HTTP API and Firebase; they do not interact with Celery.

---

# 49. DATABASE

Configured for a Django database URL:

```text
DATABASE_URL
```

Docker configuration includes PostgreSQL 16.

---

# 50. DEPLOYMENT SERVICES

Current Docker architecture:

```text
PostgreSQL
     │
     ├── Django/Gunicorn
     │
Redis ─┼── Celery Worker
     │
     └── Celery Beat
```

The Android apps only need:

```text
HTTPS API
Firebase FCM
```

They should never connect directly to PostgreSQL or Redis.

---

# 51. CRITICAL BACKEND ISSUES FOUND

These should be addressed before final Android wiring.

## 51.1 Manager key allocation is not actually implemented

The Owner Manager API uses:

`ManagerProfileSerializer`

but:

```text
total_keys = read_only
used_keys = read_only
keys_remaining = read_only
```

There is no supplied Owner endpoint/action such as:

```text
POST /api/owner/managers/{id}/allocate_keys/
```

Therefore the desired Owner → allocate keys workflow is **not exposed by the supplied API**.

This is a major missing API.

---

## 51.2 Manager FCM registration endpoint is not wired

`ManagerRegisterDeviceView` exists, but `manager.urls` does not include it.

Result:

```text
Manager App FCM registration → currently unavailable
```

Add a URL before relying on manager push notifications.

---

## 51.3 Owner FCM registration endpoint is not wired

`OwnerRegisterDeviceView` exists, but `owner.urls` does not include it.

Result:

```text
Owner App FCM registration → currently unavailable
```

---

## 51.4 Device location authentication is weak

`DeviceLocationPingView` uses:

```text
AllowAny
```

and does not verify:

```text
X-DEVICE-TOKEN
```

This should be hardened so arbitrary clients cannot submit location data.

---

## 51.5 Device ACK authentication is weak

`DeviceAckView` uses:

```text
AllowAny
```

A malicious client could potentially submit ACKs for known command IDs.

The ACK endpoint should authenticate the originating DPC/device.

---

## 51.6 Device registration is unauthenticated

`DeviceRegisterView` uses:

```text
AllowAny
```

The enrollment token supplied by the provisioning flow is not checked by this view.

This is a major security consideration.

The DPC registration flow should ideally prove:

```text
valid enrollment token
+
expected manager
+
expected IMEI
```

before registration is accepted.

---

## 51.7 Device registration identity is inconsistent

Different code creates `DeviceRegistration` using different `device_id` values.

Manager lock/unlock:

```text
device_id = device.imei1
```

Owner force delete:

```text
device_id = str(device.id)
```

Initial DPC registration:

```text
device_id = request.data["device_id"]
```

This can result in multiple registrations for the same physical device.

A single canonical device identity must be chosen.

---

## 51.8 FCM uses legacy HTTP API

The FCM helper sends:

```text
https://fcm.googleapis.com/fcm/send
```

using:

```text
FCM_SERVER_KEY
```

This is legacy FCM architecture and should be migrated to the current Firebase HTTP v1/service-account approach before production deployment.

---

## 51.9 APK checksum is hard-coded

The QR provisioning payload contains a hard-coded APK checksum.

Whenever the DPC APK changes, the checksum must be updated.

Otherwise Android provisioning can fail.

---

## 51.10 QR APK URL and root APK URL are duplicated

Both exist:

```text
/download/msafe-agent.apk
/api/manager/download/msafe-agent.apk
```

The QR uses the manager path.

Keep one canonical provisioning URL to reduce deployment mistakes.

---

## 51.11 Profile PATCH URL is awkward

`ManagerProfileViewSet` uses a `ViewSet` where:

```text
partial_update()
```

ignores the supplied `pk`.

A cleaner API would be:

```text
PATCH /api/manager/profile/
```

---

## 51.12 Owner profile permission is broader than necessary

`OwnerProfileView` uses:

```text
IsAuthenticated
```

instead of `IsOwner`.

Any authenticated user could potentially reach the view before the `owner_profile` check.

Use an explicit owner permission.

---

## 51.13 Default accounts need production hardening

The startup script creates:

```text
admin / admin123
owner / owner123
manager / manager123
```

These credentials must never remain unchanged in production.

---

# 52. MISSING / NOT CONFIRMED FROM SUPPLIED FILES

The following files/endpoints were referenced but not supplied, so they cannot be accurately documented yet:

### Users app

Not supplied:

```text
users.urls
users.models
users.serializers
users.views
users.permissions
users.utils
```

Therefore the complete `/api/` endpoint set is not known.

In particular, the following are referenced:

```text
Customer
Device
AuditLog
EnrollmentToken
CustomerSerializer
CustomerCreateUpdateSerializer
CustomTokenObtainPairView
IsManagerOfCustomer
IsOwner
```

Their exact fields and API behavior should be checked against the actual files.

### DPC enrollment

The backend QR creates an EnrollmentToken, but the supplied `DeviceRegisterView` does not consume or validate the enrollment token.

This means the complete intended enrollment contract cannot be considered finalized from the supplied code alone.

---

# 53. RECOMMENDED ANDROID NETWORK LAYERS

For the Android apps, structure the API client around:

```text
AuthApi
OwnerApi
ManagerApi
DpcApi
UploadApi
```

Example logical grouping:

```text
AuthApi
 ├── login()
 └── refresh()

OwnerApi
 ├── getProfile()
 ├── listManagers()
 ├── createManager()
 ├── updateManager()
 ├── deleteManager()
 ├── listUsers()
 ├── getUser()
 ├── shareText()
 └── forceUnenroll()

ManagerApi
 ├── getProfile()
 ├── updateProfile()
 ├── listUsers()
 ├── createUser()
 ├── getUser()
 ├── updateUser()
 ├── getQr()
 ├── lock()
 ├── unlock()
 ├── unenroll()
 ├── dashboard()
 └── deviceMap()

DpcApi
 ├── register()
 ├── heartbeat()
 ├── location()
 └── ack()

UploadApi
 └── presign()
```

---

# 54. HTTP STATUS HANDLING

Android should handle at least:

```text
200 → success
201 → created
202 → command accepted / pending
400 → validation/business error
401 → access token missing/expired
403 → permission/device authentication failure
404 → resource not found
500 → backend/server configuration failure
```

For lock/unlock/unenroll:

**202 is not final success.**

The final state must come from:

- subsequent dashboard refresh,
- notification,
- or a future status endpoint.

---

# 55. CURRENT ENDPOINT CHECKLIST

## Authentication

- [x] POST `/api/auth/token/`
- [x] POST `/api/auth/token/refresh/`

## Owner

- [x] GET `/api/owner/users/`
- [x] GET `/api/owner/users/{id}/`
- [x] GET `/api/owner/users/{id}/share_text/`
- [x] POST `/api/owner/users/{id}/force_delete/`
- [x] GET `/api/owner/managers/`
- [x] POST `/api/owner/managers/`
- [x] GET `/api/owner/managers/{id}/`
- [x] PUT `/api/owner/managers/{id}/`
- [x] PATCH `/api/owner/managers/{id}/`
- [x] DELETE `/api/owner/managers/{id}/`
- [x] GET `/api/owner/profile/`
- [ ] Owner FCM registration — view exists, URL missing
- [ ] Key allocation — no dedicated API supplied

## Manager

- [x] GET `/api/manager/users/`
- [x] POST `/api/manager/users/`
- [x] GET `/api/manager/users/{id}/`
- [x] PUT `/api/manager/users/{id}/`
- [x] PATCH `/api/manager/users/{id}/`
- [x] DELETE `/api/manager/users/{id}/`
- [x] GET `/api/manager/users/{id}/qr_png/`
- [x] POST `/api/manager/users/{id}/lock/`
- [x] POST `/api/manager/users/{id}/unlock/`
- [x] POST `/api/manager/users/{id}/delete_user/`
- [x] GET `/api/manager/profile/`
- [x] PATCH `/api/manager/profile/{id}/`
- [x] GET `/api/manager/dashboard/`
- [x] GET `/api/manager/devices/map/`
- [ ] Manager FCM registration — view exists, URL missing

## System / DPC

- [x] GET `/api/system/health/`
- [x] POST `/api/system/devices/register/`
- [x] POST `/api/system/devices/heartbeat/`
- [x] POST `/api/system/devices/location/`
- [x] POST `/api/system/devices/ack/`
- [x] GET `/api/system/uploads/presign/`
- [x] POST `/api/system/uploads/presign/`

## APK

- [x] GET `/download/msafe-agent.apk`
- [x] GET `/api/manager/download/msafe-agent.apk`

---

# 56. MOST IMPORTANT WIRING CONTRACT

For the Android development, these are the core contracts to implement first:

```text
LOGIN
POST /api/auth/token/

REFRESH
POST /api/auth/token/refresh/

MANAGER USERS
GET  /api/manager/users/
POST /api/manager/users/

QR
GET /api/manager/users/{id}/qr_png/

LOCK
POST /api/manager/users/{id}/lock/

UNLOCK
POST /api/manager/users/{id}/unlock/

UNENROLL
POST /api/manager/users/{id}/delete_user/

MANAGER DASHBOARD
GET /api/manager/dashboard/

MANAGER MAP
GET /api/manager/devices/map/

DPC REGISTER
POST /api/system/devices/register/

DPC HEARTBEAT
POST /api/system/devices/heartbeat/

DPC LOCATION
POST /api/system/devices/location/

DPC ACK
POST /api/system/devices/ack/

OWNER USERS
GET /api/owner/users/

OWNER MANAGERS
GET  /api/owner/managers/
POST /api/owner/managers/

OWNER FORCE UNENROLL
POST /api/owner/users/{id}/force_delete/
```

---

# 57. FINAL IMPLEMENTATION ORDER

### Phase 1 — Authentication

1. Login
2. Save JWT
3. Refresh JWT
4. Automatic 401 handling

### Phase 2 — Manager

1. Profile
2. User list
3. Create user
4. QR
5. User detail
6. Lock
7. Unlock
8. Unenroll
9. Dashboard
10. Map

### Phase 3 — Owner

1. Profile
2. Managers
3. Create manager
4. Manager detail
5. User list
6. User detail
7. Force unenroll
8. Key allocation after backend endpoint is added

### Phase 4 — DPC

1. Receive provisioning extras
2. Store enrollment information securely
3. Register device
4. Store device token
5. Start FCM
6. Heartbeat
7. Location
8. Receive LOCK
9. Receive UNLOCK
10. Receive UNENROLL
11. Send ACK
12. Apply Device Owner policies

### Phase 5 — Production hardening

1. Secure enrollment registration
2. Secure location endpoint
3. Secure ACK endpoint
4. Wire Manager FCM registration
5. Wire Owner FCM registration
6. Add key allocation endpoint
7. Resolve device identity inconsistency
8. Migrate FCM to HTTP v1
9. Remove default production passwords
10. Make APK checksum/version management reliable

---

# 58. Bottom line

The supplied backend already has the core architecture needed for:

```text
Owner App
     ↕
Manager App
     ↕
Django API
     ↕
Celery + Redis
     ↕
Firebase FCM
     ↕
DPC / Device
```

The strongest existing paths are:

**Manager → customer → QR → DPC → FCM → lock/unlock/unenroll → ACK → backend state.**

Before treating the backend as production-ready for Android wiring, the highest-priority gaps are:

1. **Enrollment token validation during DPC registration**
2. **Manager/Owner FCM registration URLs**
3. **Owner key allocation API**
4. **Secure DPC location and ACK APIs**
5. **Consistent device identity**
6. **Current FCM implementation**
7. **Exact `users` app API/model contract**
