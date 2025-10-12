#!/bin/bash
# Deploy script for Quiz App
# Compiles source_app.py, config.py, and prompt_manager.py into app.py
# Usage: ./deploy.sh "commit message"
#        ./deploy.sh -c   (compile only, no git operations)

COMPILE_ONLY=false
COMMIT_MESSAGE=""

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        -c)
            COMPILE_ONLY=true
            shift
            ;;
        *)
            COMMIT_MESSAGE="$1"
            shift
            ;;
    esac
done

# Validate that we have a commit message if not in compile-only mode
if [ "$COMPILE_ONLY" = false ] && [ -z "$COMMIT_MESSAGE" ]; then
    echo "Error: Please provide a commit message or use -c flag for compile-only mode"
    echo "Usage: ./deploy.sh \"commit message\""
    echo "       ./deploy.sh -c   (compile only)"
    exit 1
fi

echo "Starting deployment process for Quiz App..."
if [ "$COMPILE_ONLY" = true ]; then
    echo "Compile-only mode: Skipping git operations"
fi

# Step 1: Delete current app.py if it exists
if [ -f "app.py" ]; then
    echo "Deleting existing app.py..."
    rm app.py
fi

# Step 2: Combine files into app.py
echo "Combining files into app.py..."

# Start with shebang and imports
cat > app.py << 'EOF'
#!/usr/bin/env python3

import time
import datetime
import json
from typing import Dict, Any, Optional, List
import uuid
import threading
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import logging

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import Tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState

# Import scroll component
try:
    from streamlit_scroll_to_top import scroll_to_here
    SCROLL_AVAILABLE = True
except ImportError:
    SCROLL_AVAILABLE = False
    st.warning("streamlit-scroll-to-top not installed. Run: pip install streamlit-scroll-to-top")

# ===========================
# Configuration (from config.py)
# ===========================

EOF

# Add config.py content (skip first line shebang and imports)
echo "  Adding config.py..."
tail -n +3 config.py >> app.py

# Add prompt_manager content (excluding shebang and already-included imports)
echo "  Adding prompt_manager.py..."
echo "" >> app.py
echo "# ===========================" >> app.py
echo "# Prompt Manager (from prompt_manager.py)" >> app.py
echo "# ===========================" >> app.py
echo "" >> app.py

# Skip the first 6 lines (shebang and imports already in output)
tail -n +7 prompt_manager.py >> app.py

# Add source_app content (excluding imports and config imports)
echo "  Adding source_app.py..."
echo "" >> app.py
echo "# ===========================" >> app.py
echo "# Main Application (from source_app.py)" >> app.py
echo "# ===========================" >> app.py
echo "" >> app.py

# Skip the first 38 lines (shebang, imports, and config imports)
tail -n +39 source_app.py >> app.py

echo "✅ Successfully created app.py"

if [ "$COMPILE_ONLY" = false ]; then
    # Step 3: Git add
    echo "Adding app.py and requirements.txt to git..."
    git add app.py requirements.txt

    # Step 4: Git commit
    echo "Committing changes..."
    git commit -m "$COMMIT_MESSAGE"

    # Step 5: Git push
    echo "Pushing to origin..."
    git push origin main

    echo ""
    echo "✅ Deployment complete!"
    echo "📝 Commit message: $COMMIT_MESSAGE"
else
    echo ""
    echo "✅ Compilation complete! (Git operations skipped)"
fi
