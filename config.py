#!/usr/bin/env python3

import streamlit as st

# App Configuration
SPREADSHEET_NAME = "n8nTest"
THRESHOLD_SCORE = 8.0  # completion threshold (1-10 scale)

# Google Doc IDs for prompts
# Replace these with your actual Google Doc IDs
PROMPT_DOC_IDS = {
    "grading": "YOUR_GRADING_PROMPT_DOC_ID",  # e.g., "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    "evaluation": "YOUR_EVALUATION_PROMPT_DOC_ID",
    "conversation": "YOUR_CONVERSATION_PROMPT_DOC_ID"
}

# Prompt names within each document
PROMPT_NAMES = {
    "grading": "grading_prompt",
    "evaluation": "evaluation_prompt", 
    "conversation": "conversation_prompt"
}

def get_openai_api_key():
    """Get OpenAI API key from Streamlit secrets."""
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
        st.error("OpenAI API key missing. Add under [openai] in secrets.")
        st.stop()
    return st.secrets["openai"]["api_key"]

def get_gcp_credentials():
    """Get GCP credentials from Streamlit secrets."""
    if "gcp" not in st.secrets:
        st.error("GCP credentials missing. Add under [gcp] in secrets.")
        st.stop()
    return st.secrets["gcp"]

def get_gemini_api_key():
    """Get Gemini API key from Streamlit secrets."""
    if "gemini" not in st.secrets or "api_key" not in st.secrets["gemini"]:
        st.error("Gemini API key missing. Add under [gemini] in secrets.")
        st.stop()
    return st.secrets["gemini"]["api_key"]

# LLM Configuration
LLM_PROVIDER = "gemini"  # Options: "openai" or "gemini"
DEFAULT_MODEL = {
    "openai": "gpt-4o-mini-2024-07-18",
    "gemini": "gemini-2.5-flash"
}