#!/bin/bash
set -e

echo "========================================"
echo "ABCT Backend Starting"
echo "========================================"

# Run database migrations
echo "Running database migrations..."
cd /app
python3 run_migrations.py

if [ $? -ne 0 ]; then
    echo "ERROR: Database migration failed!"
    exit 1
fi

echo "Migrations complete. Starting application..."
echo "========================================"

# Execute the main command (passed as arguments)
exec "$@"
