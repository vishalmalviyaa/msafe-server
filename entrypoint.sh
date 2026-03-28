#!/bin/sh

echo "⚙️ Entry script starting..."

cd /app || exit 1

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "👤 Creating default accounts..."

python manage.py shell <<EOF
from django.contrib.auth import get_user_model
from manager.models import ManagerProfile

User = get_user_model()

admin, created = User.objects.get_or_create(
    username="admin",
    defaults={"email": "admin@msafe.com", "is_superuser": True, "is_staff": True}
)
if created:
    admin.set_password("admin123")
    admin.save()

owner, created = User.objects.get_or_create(
    username="owner",
    defaults={"email": "owner@msafe.com", "is_staff": True}
)
if created:
    owner.set_password("owner123")
    owner.save()

manager, created = User.objects.get_or_create(
    username="manager",
    defaults={"email": "manager@msafe.com"}
)
if created:
    manager.set_password("manager123")
    manager.save()

if not ManagerProfile.objects.filter(user=manager).exists():
    ManagerProfile.objects.create(
        user=manager,
        phone="9999999999",
        total_keys=100,
        used_keys=0
    )

print("Default accounts ready")
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