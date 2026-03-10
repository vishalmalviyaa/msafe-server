#!/bin/sh

echo "⚙️  Entry script starting..."

# Always work from /app where your code lives
cd /app || exit 1
echo "📂 Current dir: $(pwd)"
echo "📄 Files in /app:"
ls

echo "⏳ Waiting for database..."
sleep 8

echo "📦 Running migrations (if this fails, container will still keep running)..."
python manage.py migrate --noinput || echo "❌ migrate failed (will debug from inside container)."

echo "🧹 Collecting static files..."
python manage.py collectstatic --noinput || echo "No static files to collect"

echo "🚀 Starting Gunicorn (vishkey_backend.wsgi)..."
gunicorn vishkey_backend.wsgi:application --bind 0.0.0.0:8000 --workers 3
