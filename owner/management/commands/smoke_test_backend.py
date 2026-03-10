# users/management/commands/smoke_test_backend.py

import json
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from django.test import Client


class Command(BaseCommand):
    help = "Smoke test for VishKey backend (FCM + DPC security + retry command)."

    def _print_step(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n==> {title}"))

    def _print_ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f"[OK] {msg}"))

    def _print_warn(self, msg):
        self.stdout.write(self.style.WARNING(f"[WARN] {msg}"))

    def _print_fail(self, msg):
        self.stdout.write(self.style.ERROR(f"[FAIL] {msg}"))

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🚀 Starting VishKey smoke test..."))

        # 1) Basic settings check
        self._print_step("Checking critical settings")

        fcm_key = getattr(settings, "FCM_SERVER_KEY", None)
        dpc_key = getattr(settings, "DPC_API_KEY", None)
        secret_key = getattr(settings, "SECRET_KEY", None)
        debug = getattr(settings, "DEBUG", None)
        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", None)

        if fcm_key and fcm_key not in ("YOUR_FCM_SERVER_KEY", "change-me", "dummy"):
            self._print_ok("FCM_SERVER_KEY is set (not default placeholder).")
        else:
            self._print_warn(
                "FCM_SERVER_KEY looks missing or placeholder. "
                "Real devices will not receive push notifications."
            )

        if dpc_key and dpc_key not in ("super-secret-dpc-key", "change-me", "dummy"):
            self._print_ok("DPC_API_KEY is set (not obvious default).")
        else:
            self._print_warn(
                "DPC_API_KEY is missing or default. "
                "DPC endpoints may not be properly secured."
            )

        if secret_key and secret_key != "dev-secret-key-change-me":
            self._print_ok("SECRET_KEY set (not default dev-secret-key-change-me).")
        else:
            self._print_warn("SECRET_KEY is still default – OK for local, NOT OK for production.")

        self._print_ok(f"DEBUG = {debug}")
        self._print_ok(f"ALLOWED_HOSTS = {allowed_hosts}")

        # 2) Test FCM helper
        self._print_step("Testing FCM helper (dummy call)")

        try:
            # Adjust import path if your helper is elsewhere
            from users.utils import send_fcm_message
        except Exception as e:
            self._print_fail(f"Failed to import users.utils.send_fcm_message: {e}")
        else:
            try:
                # Dummy call with fake token and payload
                result = send_fcm_message(
                    token="fake-test-token",
                    data={
                        "test": True,
                        "action": "LOCK",
                        "message": "Smoke test",
                    },
                )
                self._print_ok(f"send_fcm_message() executed without crashing, returned: {result}")
            except Exception as e:
                self._print_fail(f"send_fcm_message() raised an exception: {e}")

        # 3) Test DPC endpoint security (optional, depends on your URLs)
        self._print_step("Testing DPC endpoint security (optional)")

        client = Client()

        # 👉 IMPORTANT:
        # Set this to one of your real DPC endpoints, e.g. ACK or location update
        # Example: "/api/dpc/ack/" or "/api/dpc/location/"
        DPC_TEST_URL = "/api/dpc/ack/"  # CHANGE THIS IF NEEDED

        try:
            # 3a) Request with correct API key (if configured)
            if dpc_key:
                resp_ok = client.post(
                    DPC_TEST_URL,
                    data=json.dumps({"ping": True}),
                    content_type="application/json",
                    HTTP_X_DPC_API_KEY=dpc_key,
                )
                self._print_ok(
                    f"DPC endpoint with correct API key responded with status {resp_ok.status_code}"
                )
            else:
                self._print_warn(
                    "Skipping 'correct key' DPC test because DPC_API_KEY is not set."
                )

            # 3b) Request with WRONG API key – should be 401/403 ideally
            resp_bad = client.post(
                DPC_TEST_URL,
                data=json.dumps({"ping": True}),
                content_type="application/json",
                HTTP_X_DPC_API_KEY="WRONG-KEY-123",
            )

            if resp_bad.status_code in (401, 403):
                self._print_ok(
                    f"DPC endpoint with WRONG API key correctly rejected request "
                    f"(status {resp_bad.status_code})."
                )
            else:
                self._print_warn(
                    f"DPC endpoint with WRONG API key returned status "
                    f"{resp_bad.status_code}. "
                    f"Permissions may not be strict (expected 401/403)."
                )

        except Exception as e:
            self._print_warn(
                f"Could not hit DPC test URL '{DPC_TEST_URL}'. "
                f"Adjust DPC_TEST_URL in smoke_test_backend.py if needed. Error: {e}"
            )

        # 4) Test retry_pending_commands management command
        self._print_step("Running retry_pending_commands (background retries)")

        try:
            call_command("retry_pending_commands", verbosity=1)
            self._print_ok("retry_pending_commands executed successfully.")
        except Exception as e:
            self._print_fail(f"retry_pending_commands raised an exception: {e}")

        self._print_step("Smoke test finished")
        self.stdout.write(self.style.SUCCESS("✅ Smoke test completed (see messages above)."))
