#!/bin/sh

echo "⚙️ Entry script starting..."

cd /app || exit 1

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "👤 Creating admin user..."

python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()

if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser("admin", "admin@example.com", "admin123")
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