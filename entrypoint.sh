#!/bin/sh

echo "⚙️ Entry script starting..."

cd /app || exit 1

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "👤 Creating default accounts..."

python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()

# ---------------------
# ADMIN
# ---------------------
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser(
        "admin",
        "admin@msafe.com",
        "admin123"
    )
    print("✅ Admin created")

# ---------------------
# OWNER
# ---------------------
if not User.objects.filter(username="owner").exists():
    User.objects.create_user(
        "owner",
        "owner@msafe.com",
        "owner123",
        is_staff=True
    )
    print("✅ Owner created")

# ---------------------
# MANAGER
# ---------------------
if not User.objects.filter(username="manager").exists():
    User.objects.create_user(
        "manager",
        "manager@msafe.com",
        "manager123"
    )
    print("✅ Manager created")

print("🚀 Default accounts ready")
EOF

echo "🧹 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting Gunicorn..."

exec gunicorn vishkey_backend.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -