#!/bin/sh

echo "⚙️ Entry script starting..."

cd /app || exit 1

echo "📂 Current dir: $(pwd)"
echo "📄 Files in /app:"
ls

echo "⏳ Waiting for database..."
sleep 5

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "🧹 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting Gunicorn..."

exec gunicorn vishkey_backend.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -