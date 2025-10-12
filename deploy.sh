#!/bin/bash
# Deploy script for Quiz App
# Usage: ./deploy.sh "commit message"

if [ -z "$1" ]; then
    echo "Error: Please provide a commit message"
    echo "Usage: ./deploy.sh \"commit message\""
    exit 1
fi

COMMIT_MESSAGE="$1"

echo "Starting deployment process for Quiz App..."

# Step 1: Git add all changes
echo "Adding changes to git..."
git add .

# Step 2: Git commit
echo "Committing changes..."
git commit -m "$COMMIT_MESSAGE"

# Step 3: Git push
echo "Pushing to origin..."
git push origin main

echo ""
echo "✅ Deployment complete!"
echo "📝 Commit message: $COMMIT_MESSAGE"
