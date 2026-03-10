# users/management/commands/test_apis.py

import logging
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import BaseCommand
from rest_framework.test import APIClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Hit important VishKey APIs with a dummy superuser to make sure they respond."

    def handle(self, *args, **options):
        self.stdout.write("🚀 Starting VishKey API test...\n")

        # ------------------------------------------------------------------ #
        # 0) Make sure host checks don't block our internal test client
        # ------------------------------------------------------------------ #
        # This only affects THIS management command process, not gunicorn.
        try:
            # allow anything, just for this process
            settings.ALLOWED_HOSTS = ["*"]
        except Exception:
            pass

        User = get_user_model()

        # ------------------------------------------------------------------ #
        # 1) Create / reuse SMOKE TEST SUPERUSER
        # ------------------------------------------------------------------ #
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
            self.stdout.write(self.style.SUCCESS("[OK] Created smoke_admin superuser for API tests.\n"))
        else:
            self.stdout.write(self.style.SUCCESS("[OK] Using existing smoke_admin superuser.\n"))

        # ------------------------------------------------------------------ #
        # 2) Prepare DRF client
        # ------------------------------------------------------------------ #
        client = APIClient()
        # If you want, you can force a host, but ALLOWED_HOSTS="*"
        # means it's not strictly required:
        client.defaults["HTTP_HOST"] = "localhost"
        client.force_authenticate(user=admin)

        stats = {"ok": 0, "warn": 0, "fail": 0}

        def _print_body(prefix: str, resp):
            try:
                data = resp.json()
                body_str = repr(data)
            except Exception:
                try:
                    body_str = resp.content[:400].decode(errors="ignore")
                except Exception:
                    body_str = "<unreadable body>"

            body_str = body_str.replace("\n", " ")[:400]
            self.stdout.write(f"{prefix} Body: {body_str}\n")

        # ------------------------------------------------------------------ #
        # Helper: call one endpoint
        # ------------------------------------------------------------------ #
        def call(
            method: str,
            url: str,
            desc: str,
            *,
            payload=None,
            files=None,
            expected_ok: Iterable[int] = (200, 201, 204),
            extra_headers=None,
        ):
            nonlocal stats

            method = method.upper()
            headers = extra_headers or {}

            try:
                if method == "GET":
                    resp = client.get(url, **headers)
                elif method == "POST":
                    if files:
                        data = payload or {}
                        data.update(files)
                        resp = client.post(url, data=data, **headers)
                    else:
                        resp = client.post(url, data=payload or {}, format="json", **headers)
                elif method == "PUT":
                    resp = client.put(url, data=payload or {}, format="json", **headers)
                elif method == "PATCH":
                    resp = client.patch(url, data=payload or {}, format="json", **headers)
                elif method == "DELETE":
                    resp = client.delete(url, **headers)
                else:
                    self.stdout.write(self.style.WARNING(f"[SKIP] Unsupported method {method} for {url}\n"))
                    return None

                code = resp.status_code
                base_msg = f"[{code}] {method} {url} - {desc}"

                if code in expected_ok:
                    stats["ok"] += 1
                    self.stdout.write(self.style.SUCCESS(f"[OK] {base_msg}\n"))
                elif code == 404:
                    stats["warn"] += 1
                    self.stdout.write(self.style.WARNING(
                        f"[WARN] {base_msg} -> 404 (URL might be wrong or endpoint not implemented).\n"
                    ))
                    _print_body("       ", resp)
                elif code in (401, 403):
                    stats["warn"] += 1
                    self.stdout.write(self.style.WARNING(
                        f"[WARN] {base_msg} -> {code} (auth/permission issue).\n"
                    ))
                    _print_body("       ", resp)
                elif code >= 500:
                    stats["fail"] += 1
                    self.stdout.write(self.style.ERROR(
                        f"[FAIL] {base_msg} -> {code} (server error).\n"
                    ))
                    _print_body("       ", resp)
                else:
                    # e.g. 400, 405, 409, etc.
                    stats["warn"] += 1
                    self.stdout.write(self.style.WARNING(f"[WARN] {base_msg}\n"))
                    _print_body("       ", resp)

                return resp

            except Exception as e:
                stats["fail"] += 1
                self.stdout.write(self.style.ERROR(
                    f"[FAIL] Exception calling {method} {url}: {e}\n"
                ))
                return None

        # ------------------------------------------------------------------ #
        # 3) BASIC / AUTH / HEALTH
        # ------------------------------------------------------------------ #
        self.stdout.write("==> Basic / Auth / Health endpoints\n")

        call("GET", "/api/health/", "Health check endpoint (if exists)")
        call("GET", "/api/auth/me/", "Current user profile (auth check)")
        call("GET", "/api/users/me/", "Current user profile (alternate path)")

        # ------------------------------------------------------------------ #
        # 4) OWNER APIs
        # ------------------------------------------------------------------ #
        self.stdout.write("\n==> Owner endpoints\n")

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

        call("GET", "/api/owner/users/", "Owner: list all users")
        call("GET", "/api/owner/keys/", "Owner: list all keys")

        if manager_id:
            call("GET", f"/api/owner/managers/{manager_id}/", "Owner: manager detail")
            call("GET", f"/api/owner/managers/{manager_id}/stats/", "Owner: manager stats")

        # ------------------------------------------------------------------ #
        # 5) MANAGER APIs
        # ------------------------------------------------------------------ #
        self.stdout.write("\n==> Manager endpoints\n")

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

        # ------------------------------------------------------------------ #
        # 6) USER / DEVICE / ENROLL / COMMANDS
        # ------------------------------------------------------------------ #
        self.stdout.write("\n==> User / Device / Enrollment / Commands\n")

        call("GET", "/api/users/devices/", "User: list devices")

        call("GET", "/api/owner/enrollment-tokens/", "Owner: list enrollment tokens")
        call(
            "POST",
            "/api/owner/enrollment-tokens/",
            "Owner: create enrollment token",
            payload={"label": "Smoke token", "max_uses": 1},
        )

        call("GET", "/api/devices/commands/", "List device commands (if exists)")

        # ------------------------------------------------------------------ #
        # 7) FILE UPLOAD: PHOTO + SIGNATURE
        # ------------------------------------------------------------------ #
        self.stdout.write("\n==> File upload endpoints (photo / signature)\n")

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

        # ------------------------------------------------------------------ #
        # 8) QR / KEY / MISC
        # ------------------------------------------------------------------ #
        self.stdout.write("\n==> QR / Key / Misc endpoints\n")

        call("GET", "/api/owner/qr/test/", "Owner: test QR generation (if exists)")
        call("GET", "/api/owner/keys/export/", "Owner: export keys list (if exists)")

        # ------------------------------------------------------------------ #
        # 9) SUMMARY
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ API tests finished. OK={stats['ok']} | WARN={stats['warn']} | FAIL={stats['fail']}\n"
        ))
        self.stdout.write("   • OK   = Status in expected_ok\n")
        self.stdout.write("   • WARN = Non-fatal issues (400/401/403/404/other)\n")
        self.stdout.write("   • FAIL = Exceptions or 5xx server errors\n")
