#!/bin/sh

echo "⚙️  Entry script starting..."

cd /app || exit 1
echo "📂 Current dir: $(pwd)"
echo "📄 Files in /app:"
ls

echo "⏳ Waiting for database..."
sleep 8

echo "📦 Running migrations..."
python manage.py migrate --noinput || echo "❌ migrate failed"

echo "🧹 Collecting static files..."
python manage.py collectstatic --noinput || echo "No static files"

echo "🚀 Starting Gunicorn..."
exec gunicorn vishkey_backend.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers 2 \
  --timeout 120 \
  --log-level debug \
  --access-logfile - \
  --error-logfile -