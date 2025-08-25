#!/bin/bash

# Backup Encryption Setup Script
# Generates secure encryption key for the backup system

set -e

echo "🔐 Chrono Scraper Backup Encryption Setup"
echo "=========================================="
echo

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is required but not found"
    exit 1
fi

# Generate encryption key
echo "🔑 Generating secure encryption key..."
ENCRYPTION_KEY=$(python3 -c "
from cryptography.fernet import Fernet
import base64
key = Fernet.generate_key()
print(key.decode())
")

if [ -z "$ENCRYPTION_KEY" ]; then
    echo "❌ Error: Failed to generate encryption key"
    exit 1
fi

echo "✅ Encryption key generated successfully!"
echo

# Check if .env file exists
if [ -f ".env" ]; then
    echo "📝 Updating .env file..."
    
    # Check if BACKUP_ENCRYPTION_KEY already exists
    if grep -q "BACKUP_ENCRYPTION_KEY=" .env; then
        # Replace existing key
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS sed syntax
            sed -i '' "s/BACKUP_ENCRYPTION_KEY=.*/BACKUP_ENCRYPTION_KEY=$ENCRYPTION_KEY/" .env
        else
            # Linux sed syntax
            sed -i "s/BACKUP_ENCRYPTION_KEY=.*/BACKUP_ENCRYPTION_KEY=$ENCRYPTION_KEY/" .env
        fi
        echo "✅ Updated existing BACKUP_ENCRYPTION_KEY in .env"
    else
        # Add new key
        echo "BACKUP_ENCRYPTION_KEY=$ENCRYPTION_KEY" >> .env
        echo "✅ Added BACKUP_ENCRYPTION_KEY to .env"
    fi
else
    echo "⚠️  Warning: .env file not found"
    echo "📝 Creating backup-encryption.env file..."
    echo "BACKUP_ENCRYPTION_KEY=$ENCRYPTION_KEY" > backup-encryption.env
    echo "✅ Created backup-encryption.env with encryption key"
    echo "   Please copy this to your .env file or source it"
fi

echo
echo "🔒 IMPORTANT SECURITY NOTES:"
echo "  • Store this encryption key securely"
echo "  • Back up the encryption key separately from your backups"
echo "  • Never commit the encryption key to version control"
echo "  • Consider using a key management service in production"
echo
echo "🔐 Your encryption key:"
echo "BACKUP_ENCRYPTION_KEY=$ENCRYPTION_KEY"
echo
echo "✅ Backup encryption setup completed!"
echo
echo "Next steps:"
echo "1. Verify the key is in your .env file"
echo "2. Test the backup system: docker compose exec backend python app/scripts/validate_backup_environment.py"
echo "3. Create your first backup: curl -X POST http://localhost:8000/api/v1/backup/test"