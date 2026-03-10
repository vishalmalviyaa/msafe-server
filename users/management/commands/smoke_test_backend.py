# users/management/commands/smoke_test_backend.py

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import BaseCommand, call_command
from rest_framework.test import APIClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Full VishKey backend smoke test (settings, helpers, and main APIs)."

    def handle(self, *args, **options):
        self.stdout.write("🚀 Starting VishKey full API smoke test...\n")

        self.check_settings()
        self.test_fcm_helper()
        self.test_dpc_security()
        self.test_retry_pending_commands()
        self.test_api_endpoints()

        self.stdout.write("\n✅ Smoke test completed (see messages above).")

    # -------------------------------------------------------------------------
    # 1) SETTINGS CHECKS
    # -------------------------------------------------------------------------
    def check_settings(self):
        self.stdout.write("==> Checking critical settings")

        fcm_key = getattr(settings, "FCM_SERVER_KEY", None)
        if fcm_key and fcm_key not in ("", "YOUR_FCM_SERVER_KEY"):
            self.stdout.write(self.style.SUCCESS("[OK] FCM_SERVER_KEY is set (not default placeholder)."))
        else:
            self.stdout.write(self.style.WARNING(
                "[WARN] FCM_SERVER_KEY is missing or default. Real FCM sends will not work."
            ))

        dpc_api_key = getattr(settings, "DPC_API_KEY", None)
        if dpc_api_key and dpc_api_key not in ("", "CHANGE_ME_DPC_API_KEY"):
            self.stdout.write(self.style.SUCCESS("[OK] DPC_API_KEY is set (not default)."))
        else:
            self.stdout.write(self.style.WARNING(
                "[WARN] DPC_API_KEY is missing or default. DPC endpoints may not be properly secured."
            ))

        secret = getattr(settings, "SECRET_KEY", "")
        if secret and secret not in ("dev-secret-key-change-me", "changeme"):
            self.stdout.write(self.style.SUCCESS("[OK] SECRET_KEY set (not default dev-secret-key-change-me)."))
        else:
            self.stdout.write(self.style.ERROR(
                "[FAIL] SECRET_KEY is default or missing. Change this for production."
            ))

        debug = getattr(settings, "DEBUG", True)
        if debug:
            self.stdout.write(self.style.WARNING("[WARN] DEBUG = True (good for dev, bad for production)."))
        else:
            self.stdout.write(self.style.SUCCESS("[OK] DEBUG = False"))

        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
        self.stdout.write(self.style.SUCCESS(f"[OK] ALLOWED_HOSTS = {allowed_hosts!r}"))

    # -------------------------------------------------------------------------
    # 2) FCM HELPER
    # -------------------------------------------------------------------------
    def test_fcm_helper(self):
        self.stdout.write("\n==> Testing FCM helper (dummy call)")

        try:
            from users.utils import send_fcm_message  # type: ignore
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"[FAIL] Failed to import users.utils.send_fcm_message: {e}"
            ))
            return

        try:
            result = send_fcm_message(
                token="dummy_fcm_token_for_smoke_test",
                data={"test": True},
                title="SmokeTest",
                body="This is a dummy FCM test.",
            )
            self.stdout.write(self.style.SUCCESS(
                f"[OK] send_fcm_message() callable, returned: {result}"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"[FAIL] send_fcm_message raised an exception: {e}"
            ))

    # -------------------------------------------------------------------------
    # 3) DPC SECURITY (OPTIONAL)
    # -------------------------------------------------------------------------
    def test_dpc_security(self):
        self.stdout.write("\n==> Testing DPC endpoint security (optional)")

        client = APIClient()
        correct_key = getattr(settings, "DPC_API_KEY", "CHANGE_ME_DPC_API_KEY")

        # TODO: change this to your real DPC registration endpoint
        dpc_url = "/api/dpc/register/"

        # 3.1 correct key
        resp_ok = client.post(
            dpc_url,
            data={"test": True},
            HTTP_X_DPC_API_KEY=correct_key,
            format="json",
        )
        self.stdout.write(self.style.SUCCESS(
            f"[OK] DPC endpoint with correct API key responded with status {resp_ok.status_code}"
        ))

        # 3.2 wrong key
        resp_bad = client.post(
            dpc_url,
            data={"test": True},
            HTTP_X_DPC_API_KEY="WRONG_KEY",
            format="json",
        )
        if resp_bad.status_code in (401, 403):
            self.stdout.write(self.style.SUCCESS(
                f"[OK] DPC endpoint with WRONG API key returned {resp_bad.status_code} (secured)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"[WARN] DPC endpoint with WRONG API key returned status {resp_bad.status_code}. "
                f"Expected 401/403 for strict security."
            ))

    # -------------------------------------------------------------------------
    # 4) RETRY PENDING COMMANDS
    # -------------------------------------------------------------------------
    def test_retry_pending_commands(self):
        self.stdout.write("\n==> Running retry_pending_commands (background retries)")
        try:
            call_command("retry_pending_commands")
            self.stdout.write(self.style.SUCCESS("[OK] retry_pending_commands executed successfully."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"[FAIL] retry_pending_commands raised an exception: {e}"
            ))

    # -------------------------------------------------------------------------
    # 5) MAIN API ENDPOINT TESTS
    # -------------------------------------------------------------------------
    def test_api_endpoints(self):
        """
        Hit important APIs with a dedicated smoke-test superuser using DRF's APIClient.

        IMPORTANT:
        - You must adjust URLs below (OWNER_API, MANAGER_API, USER_API) to match your real routes.
        - If you see 404 in output => probably wrong path, fix and re-run.
        """
        self.stdout.write("\n==> Testing API endpoints")

        User = get_user_model()

        # Create a dedicated smoke-test superuser so we don't depend on manual superuser
        admin, created = User.objects.get_or_create(
            username="smoke_admin",
            defaults={
                "email": "smoke_admin@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password("SmokeAdmin123!")
            admin.save()
            self.stdout.write(self.style.SUCCESS("[OK] Created smoke_admin superuser for API tests."))
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Using existing smoke_admin superuser."))

        client = APIClient()
        client.force_authenticate(user=admin)

        # ---------------------------------------------------------------------
        # Helper for calling endpoints
        # ---------------------------------------------------------------------
        def call(method: str, url: str, desc: str, payload=None, files=None,
                 expected_ok=(200, 201, 204), extra_headers=None):
            method = method.upper()
            headers = extra_headers or {}

            try:
                if method == "GET":
                    resp = client.get(url, **headers)
                elif method == "POST":
                    if files:
                        resp = client.post(url, data=payload or {}, files=files, format=None, **headers)
                    else:
                        resp = client.post(url, data=payload or {}, format="json", **headers)
                elif method == "PUT":
                    resp = client.put(url, data=payload or {}, format="json", **headers)
                elif method == "PATCH":
                    resp = client.patch(url, data=payload or {}, format="json", **headers)
                elif method == "DELETE":
                    resp = client.delete(url, **headers)
                else:
                    self.stdout.write(self.style.WARNING(
                        f"[SKIP] Unsupported method {method} for {url}"
                    ))
                    return

                code = resp.status_code
                base_msg = f"[{code}] {method} {url} - {desc}"

                if code in expected_ok:
                    self.stdout.write(self.style.SUCCESS(f"[OK] {base_msg}"))
                elif code == 404:
                    self.stdout.write(self.style.WARNING(
                        f"[WARN] {base_msg} -> 404 (URL might be wrong or endpoint not implemented)."
                    ))
                elif code in (401, 403):
                    self.stdout.write(self.style.WARNING(
                        f"[WARN] {base_msg} -> {code} (auth/permission issue)."
                    ))
                elif code >= 500:
                    self.stdout.write(self.style.ERROR(
                        f"[FAIL] {base_msg} -> {code} (server error)."
                    ))
                    try:
                        body = resp.json()
                    except Exception:
                        body = resp.content[:300].decode(errors="ignore")
                    self.stdout.write(self.style.ERROR(f"      Response body: {body!r}"))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"[WARN] {base_msg}"
                    ))

                return resp
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"[FAIL] Exception when calling {method} {url}: {e}"
                ))
                return None

        # ---------------------------------------------------------------------
        # 5.1 BASIC / AUTH / HEALTH
        # ---------------------------------------------------------------------
        call("GET", "/api/health/", "Health check endpoint (if exists)")
        call("GET", "/api/auth/me/", "Current user profile (auth check)")
        call("GET", "/api/users/me/", "Current user profile (alternate path)")

        # ---------------------------------------------------------------------
        # 5.2 OWNER APIs (guessed URLs, adjust to real ones)
        # ---------------------------------------------------------------------
        self.stdout.write("\n-- Owner endpoints --")

        call("GET", "/api/owner/managers/", "Owner: list managers")

        manager_payload = {
            "name": "Smoke Manager",
            "employee_id": "SMOKE-MGR-001",
            "phone": "+910000000000",
            "email": "smoke_manager@example.com",
            "password": "ManagerPass123!",
        }
        resp_mgr_create = call(
            "POST",
            "/api/owner/managers/",
            "Owner: create manager",
            payload=manager_payload,
        )

        manager_id = None
        if resp_mgr_create is not None:
            try:
                data = resp_mgr_create.json()
                manager_id = data.get("id") or data.get("pk")
            except Exception:
                manager_id = None

        call("GET", "/api/owner/users/", "Owner: list users under all managers")
        call("GET", "/api/owner/keys/", "Owner: list keys")

        if manager_id:
            call("GET", f"/api/owner/managers/{manager_id}/", "Owner: manager detail")
            call("GET", f"/api/owner/managers/{manager_id}/stats/", "Owner: manager stats")

        # ---------------------------------------------------------------------
        # 5.3 MANAGER APIs (guessed URLs)
        # ---------------------------------------------------------------------
        self.stdout.write("\n-- Manager endpoints --")

        call("GET", "/api/manager/profile/", "Manager: profile (using admin auth)")
        call("GET", "/api/manager/users/", "Manager: list own users")
        call("GET", "/api/manager/keys/", "Manager: list allocated keys")

        call("GET", "/api/manager/default-lock-settings/", "Manager: get default lock settings")

        default_lock_payload = {
            "auto_lock_seconds": 10,
            "allow_remote_unlock": True,
            "max_failed_attempts": 5,
        }
        call(
            "PATCH",
            "/api/manager/default-lock-settings/",
            "Manager: update default lock settings",
            payload=default_lock_payload,
        )

        # ---------------------------------------------------------------------
        # 5.4 USER / DEVICE / ENROLLMENT (guessed URLs)
        # ---------------------------------------------------------------------
        self.stdout.write("\n-- User / Device / Enrollment endpoints --")

        call("GET", "/api/users/devices/", "User: list devices")

        call("GET", "/api/owner/enrollment-tokens/", "Owner: list enrollment tokens")
        call(
            "POST",
            "/api/owner/enrollment-tokens/",
            "Owner: create enrollment token",
            payload={"label": "Smoke token", "max_uses": 1},
        )

        call("GET", "/api/devices/commands/", "List device commands")

        # ---------------------------------------------------------------------
        # 5.5 FILE UPLOAD ENDPOINTS (PHOTO / SIGNATURE)
        # ---------------------------------------------------------------------
        self.stdout.write("\n-- File upload endpoints (photo/signature) --")

        dummy_png = SimpleUploadedFile(
            "smoke.png",
            b"\x89PNG\r\n\x1a\n" + b"0" * 256,
            content_type="image/png",
        )

        call(
            "POST",
            "/api/users/upload-photo/",
            "User: upload profile photo",
            payload={},
            files={"photo": dummy_png},
            expected_ok=(200, 201),
        )

        dummy_sig = SimpleUploadedFile(
            "signature.png",
            b"\x89PNG\r\n\x1a\n" + b"1" * 256,
            content_type="image/png",
        )
        call(
            "POST",
            "/api/users/upload-signature/",
            "User: upload signature",
            payload={},
            files={"signature": dummy_sig},
            expected_ok=(200, 201),
        )

        # ---------------------------------------------------------------------
        # 5.6 QR / KEY / MISC (guessed URLs)
        # ---------------------------------------------------------------------
        self.stdout.write("\n-- QR / Key / Misc endpoints --")

        call("GET", "/api/owner/qr/test/", "Owner: test QR generation endpoint (if exists)")
        call("GET", "/api/owner/keys/export/", "Owner: export keys list")

        self.stdout.write(self.style.SUCCESS("\n[DONE] API endpoint tests complete."))
