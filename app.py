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
# ===========================
# Prompt Manager (from prompt_manager.py)
# ===========================

import json

class PromptManager:
    def __init__(self, credentials_dict: dict, sheets_manager=None):
        """Initialize the prompt manager with Google credentials."""
        self.credentials = Credentials.from_service_account_info(
            credentials_dict,
            scopes=['https://www.googleapis.com/auth/documents.readonly']
        )
        self.service = build('docs', 'v1', credentials=self.credentials)
        self.sheets_manager = sheets_manager
        self._prompts_cache = {}
    
    def get_prompt_from_doc(self, doc_id: str, prompt_name: str) -> Optional[str]:
        """
        Extract a specific prompt from a Google Doc.
        
        Args:
            doc_id: Google Doc ID (from URL)
            prompt_name: Name of the prompt to extract (e.g., 'grading_prompt')
        
        Returns:
            The prompt text or None if not found
        """
        try:
            # Get the document content
            document = self.service.documents().get(documentId=doc_id).execute()
            
            # Extract text content
            content = document.get('body', {}).get('content', [])
            full_text = self._extract_text_from_content(content)
            
            # Parse prompts (assuming format like "GRADING_PROMPT: ...")
            prompts = self._parse_prompts_from_text(full_text)
            
            return prompts.get(prompt_name)
            
        except Exception as e:
            st.error(f"Error loading prompt '{prompt_name}' from Google Doc: {e}")
            return None
    
    def _extract_text_from_content(self, content: list) -> str:
        """Extract text from Google Doc content structure."""
        text = ""
        for element in content:
            if 'paragraph' in element:
                for para_element in element['paragraph']['elements']:
                    if 'textRun' in para_element:
                        text += para_element['textRun']['content']
        return text
    
    def _parse_prompts_from_text(self, text: str) -> Dict[str, str]:
        """Parse prompts from text using a simple format."""
        prompts = {}
        current_prompt = None
        current_content = []
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if this line starts a new prompt (format: PROMPT_NAME:)
            if ':' in line and line.split(':')[0].isupper():
                # Save previous prompt if exists
                if current_prompt:
                    prompts[current_prompt] = '\n'.join(current_content).strip()
                
                # Start new prompt
                current_prompt = line.split(':')[0].lower()
                current_content = []
                
                # Add the rest of the line as content if it exists
                remaining = line.split(':', 1)[1].strip()
                if remaining:
                    current_content.append(remaining)
            else:
                # Add line to current prompt content
                if current_prompt:
                    current_content.append(line)
        
        # Save the last prompt
        if current_prompt:
            prompts[current_prompt] = '\n'.join(current_content).strip()
        
        return prompts
    
    def get_cached_prompt(self, doc_id: str, prompt_name: str) -> Optional[str]:
        """Get a prompt with caching to avoid repeated API calls."""
        cache_key = f"{doc_id}_{prompt_name}"
        
        if cache_key not in self._prompts_cache:
            self._prompts_cache[cache_key] = self.get_prompt_from_doc(doc_id, prompt_name)
        
        return self._prompts_cache[cache_key]
    
    def get_prompt_from_assignment(self, assignment_id: str, prompt_type: str) -> Optional[str]:
        """
        Get a prompt from the Google Sheets assignments table.
        
        Args:
            assignment_id: The assignment ID to look up
            prompt_type: Type of prompt ("grading" or "conversation")
        
        Returns:
            The prompt text or None if not found
        """
        if not self.sheets_manager:
            print(f"[DEBUG] sheets_manager is None, cannot fetch prompt for assignment {assignment_id}")
            return None
            
        try:
            # Get the assignment record using the fetch method
            print(f"[DEBUG] Fetching assignment {assignment_id} for prompt type {prompt_type}")
            assignment = self.sheets_manager.assignments.fetch(assignment_id)
            
            if not assignment:
                print(f"[DEBUG] No assignment found for ID {assignment_id}")
                return None
            
            # Map prompt type to column name
            column_map = {
                "grading": "GradingPrompt",
                "conversation": "ConversationPrompt",
                "evaluation": "EnhancedFeedbackPrompt"
            }
            
            column_name = column_map.get(prompt_type)
            if not column_name:
                print(f"[DEBUG] Invalid prompt type: {prompt_type}")
                return None
            
            prompt = assignment.get(column_name, "").strip()
            if prompt:
                print(f"[DEBUG] Successfully loaded {prompt_type} prompt (length: {len(prompt)})")
            else:
                print(f"[DEBUG] No prompt found in column {column_name} for assignment {assignment_id}")
            return prompt if prompt else None
            
        except Exception as e:
            st.error(f"Error loading prompt from assignments sheet: {e}")
            print(f"[DEBUG] Exception loading prompt: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_prompt_cached(self, assignment_id: str, prompt_type: str) -> Optional[str]:
        """Get a prompt from assignments sheet with caching.
        Only caches successful prompt fetches, not None values."""
        cache_key = f"assignment_{assignment_id}_{prompt_type}"
        
        # Check if we have a cached value
        if cache_key in self._prompts_cache:
            cached_value = self._prompts_cache[cache_key]
            print(f"[DEBUG] Using cached {prompt_type} prompt for assignment {assignment_id} (cached length: {len(cached_value) if cached_value else 'None'})")
            return cached_value
        
        # Fetch fresh prompt
        print(f"[DEBUG] Cache miss - fetching fresh {prompt_type} prompt for assignment {assignment_id}")
        prompt = self.get_prompt_from_assignment(assignment_id, prompt_type)
        
        # Only cache if we successfully got a prompt (not None or empty)
        if prompt:
            self._prompts_cache[cache_key] = prompt
            print(f"[DEBUG] Cached {prompt_type} prompt for assignment {assignment_id}")
        else:
            print(f"[DEBUG] Not caching empty/None prompt for {prompt_type} assignment {assignment_id}")
        
        return prompt

# Example usage and prompt templates
def get_default_prompts() -> Dict[str, str]:
    """Fallback prompts if Google Docs are unavailable."""
    return {
        "grading_prompt": """You are an AI teaching assistant grading student answers. Please evaluate the following answers and provide feedback and scores.

Student ID: {student_id}
Execution ID: {execution_id}

Current Student Answers:
Q1: {q1}
Q2: {q2}
Q3: {q3}

Question 1 Context History:
{q1_context}

Question 2 Context History:
{q2_context}

Question 3 Context History:
{q3_context}

Previous Conversations:
{conversation_context}

Please provide your evaluation in the following JSON format:
{{
    "execution_id": "{execution_id}",
    "student_id": "{student_id}",
    "score1": <score from 1-10>,
    "score2": <score from 1-10>,
    "score3": <score from 1-10>,
    "feedback1": "<detailed feedback for Q1>",
    "feedback2": "<detailed feedback for Q2>",
    "feedback3": "<detailed feedback for Q3>"
}}

Be thoughtful in your evaluation. Consider clarity, depth of understanding, and relevance to the questions. Use the context history to provide more personalized and relevant feedback.""",
        
        "evaluation_prompt": """You are an AI teaching assistant providing improved feedback. Review the previous grading and provide enhanced feedback.

Previous Grading Results:
{previous_grading}

Please provide improved feedback in the following JSON format:
{{
    "execution_id": "{execution_id}",
    "student_id": "{student_id}",
    "new_score1": <improved score from 1-10>,
    "new_score2": <improved score from 1-10>,
    "new_score3": <improved score from 1-10>,
    "new_feedback1": "<enhanced feedback for Q1>",
    "new_feedback2": "<enhanced feedback for Q2>",
    "new_feedback3": "<enhanced feedback for Q3>"
}}

Provide more detailed, constructive feedback that will help the student improve.""",
        
        "conversation_prompt": """You are an AI teaching assistant helping a student with their assignment feedback.

Here is the full context for this assignment session:
{context}

Student's new question: {user_question}

Please provide a helpful, encouraging response that addresses their question and provides guidance for improvement. Be supportive and constructive.
Respond in a conversational tone, as if you're having a one-on-one tutoring session."""
    }


def get_orchestration_text() -> Dict[str, str]:
    """Get orchestration instructions for different agent types."""
    return {
        "grading_evaluation": """You are an AI assistant helping with educational assessment. Follow these instructions carefully:

1. USE THE DATA: The <data> section contains all relevant information about the assignment, questions, answers, and previous interactions. Use this data to provide context-aware feedback.

2. FOLLOW THE INSTRUCTIONS: The <instructions> section contains specific guidance on how to approach this task. Follow these instructions precisely.

3. VARIABLE NUMBER OF QUESTIONS: This assignment may have anywhere from 1 to 25 questions. The <output_format> section will show the exact structure needed for this specific assignment. Pay attention to which question numbers are required.

4. OUTPUT FORMAT (CRITICAL): Regardless of what the instructions say, you MUST respond with ONLY valid JSON in the exact format specified in the <output_format> section. Include ALL fields shown in the output format - no more, no less. Do not include any explanatory text, markdown formatting, or additional content outside the JSON structure. Your entire response should be parseable as JSON.""",
        
        "conversation": """You are an AI teaching assistant helping a student understand their assignment feedback. Follow these instructions carefully:

1. USE THE DATA: The <data> section contains all relevant information about the assignment, questions, answers, grading feedback, and conversation history. Use this data to provide context-aware, personalized responses.

2. FOLLOW THE INSTRUCTIONS: The <instructions> section contains specific guidance on how to interact with students. Follow these instructions precisely.

3. BE HELPFUL AND SUPPORTIVE: Provide clear, encouraging guidance that helps the student improve their understanding. Reference specific parts of their answers and feedback when relevant."""
    }


def get_grading_output_format(question_num: int) -> str:
    """Get the required JSON output format for grading a single question."""
    return f"""{{
    "score{question_num}": <integer from 0-10>,
    "feedback{question_num}": "<detailed feedback string>"
}}"""


def get_evaluation_output_format(num_questions: int) -> str:
    """Get the required JSON output format for evaluation of multiple questions."""
    fields = []
    for i in range(1, num_questions + 1):
        fields.append(f'    "new_score{i}": <integer from 0-10>,')
        fields.append(f'    "new_feedback{i}": "<enhanced feedback string>"{"," if i < num_questions else ""}')
    
    return "{\n" + "\n".join(fields) + "\n}" 
# ===========================
# Main Application (from source_app.py)
# ===========================


# Page config must be first
st.set_page_config(page_title='Dynamic AI Assignment', layout='centered')

# --- Custom CSS for Modern Look ---
st.markdown('''
    <style>
    body {
        background-color: #f7f9fa;
    }
    .main {
        background-color: #fff;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        padding: 2rem 2rem 1rem 2rem;
        margin-top: 1.5rem;
        color: #222;
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }
    .question-card {
        background: rgba(200,210,220,0.18) !important;
        border-radius: 10px;
        padding: 0.7rem 1rem 0.7rem 1rem;
        margin-bottom: 0.7rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
        color: #fff !important;
        font-size: 1.08rem;
        font-weight: 400;
    }
    .question-card, .question-card * {
        color: #fff !important;
    }
    .question-card h3, .feedback-card h3, .main h1, .main h2, .main h3 {
        color: #fff !important;
        font-size: 1.25rem !important;
        margin-bottom: 0.3rem !important;
        margin-top: 0.3rem !important;
        font-weight: 400 !important;
    }
    .main h1 {
        font-size: 1.7rem !important;
    }
    .main h2 {
        font-size: 1.3rem !important;
    }
    .main h3 {
        font-size: 1.1rem !important;
    }
    .score-high { color: #2ecc40; font-weight: bold; }
    .score-mid { color: #f1c40f; font-weight: bold; }
    .score-low { color: #e74c3c; font-weight: bold; }
    .stButton>button {
        border-radius: 8px;
        padding: 0.5rem 1.2rem;
        font-size: 1.1rem;
        background: linear-gradient(90deg, #425066 0%, #7a8ca3 100%) !important;
        color: #fff !important;
        border: none;
        margin-top: 0.5rem;
    }
    .stTextInput>div>input, .stTextArea>div>textarea {
        border-radius: 8px;
        border: 1px solid #d0d7de;
        background: #f7f9fa;
        font-size: 1.1rem;
    }
    .stTextInput>div>input:focus, .stTextArea>div>textarea:focus {
        border: 1.5px solid #4f8cff;
        background: #fff;
    }
    .stAlert {
        border-radius: 8px;
    }
    .footer {
        margin-top: 2.5rem;
        text-align: center;
        color: #888;
        font-size: 0.95rem;
    }
    /* --- FORCE FEEDBACK CARD COLOR OVERRIDE --- */
    .feedback-card, .feedback-card * {
        background: rgba(60, 180, 90, 0.10) !important;
        color: #fff !important;
    }
    </style>
''', unsafe_allow_html=True)

# --- Header/Banner ---
st.markdown("""
<div style='display: flex; align-items: center; justify-content: center; margin-bottom: 1.2rem;'>
    <img src='https://img.icons8.com/color/96/000000/artificial-intelligence.png' style='height: 48px; margin-right: 14px;'>
    <div>
        <h1 style='margin-bottom: 0.1rem; font-size:1.6rem;'>Dynamic AI Assignment</h1>
    </div>
</div>
""", unsafe_allow_html=True)

# Add this helper at the top (after imports)
def rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# Get credentials and initialize prompt manager
OPENAI_API_KEY = get_openai_api_key()
GCP_CREDENTIALS = get_gcp_credentials()

# Get Gemini API key if using Gemini
GEMINI_API_KEY = None
if LLM_PROVIDER == "gemini":
    try:
        GEMINI_API_KEY = get_gemini_api_key()
    except:
        st.warning("Gemini API key not found. Falling back to OpenAI.")
        LLM_PROVIDER = "openai"

# Prompt manager will be initialized after sheets are set up
prompt_manager = None

# Generic Google Sheets wrapper with caching
class Sheet:
    def __init__(self, client, title: str, headers: list[str]):
        self.headers = headers
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 10  # Cache for only 10 seconds to ensure fresher data
        ss = client.open(SPREADSHEET_NAME)
        try:
            self.ws = ss.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            self.ws = ss.add_worksheet(title=title, rows="1000", cols=str(len(headers)))
            self.ws.append_row(headers)

    def get_all(self) -> list[dict]:
        """Get all records with caching."""
        current_time = time.time()
        if (current_time - self._cache_timestamp) < self._cache_ttl and self._cache:
            return self._cache
        
        # Fetch fresh data
        try:
            # First, check if there are empty headers in the sheet
            actual_headers = self.ws.row_values(1)
            # Filter out empty headers and only keep the ones we expect
            filtered_headers = [h for h in actual_headers if h.strip()]
            
            # If there are empty headers, use expected_headers parameter
            if len(filtered_headers) < len(actual_headers):
                empty_count = len(actual_headers) - len(filtered_headers)
                print(f"[DEBUG] Found {empty_count} empty header(s) in sheet, using expected_headers parameter")
                self._cache = self.ws.get_all_records(expected_headers=self.headers)
            else:
                self._cache = self.ws.get_all_records()
            self._cache_timestamp = current_time
        except Exception as e:
            print(f"[ERROR] get_all_records() failed: {e}")
            # If there's a header uniqueness issue, try with expected_headers parameter
            try:
                print(f"[DEBUG] Attempting get_all_records() with expected_headers")
                self._cache = self.ws.get_all_records(expected_headers=self.headers)
                self._cache_timestamp = current_time
                print(f"[DEBUG] Successfully fetched records with expected_headers parameter")
            except Exception as e2:
                print(f"[ERROR] get_all_records() with expected_headers also failed: {e2}")
                # Last resort: check actual headers
                try:
                    actual_headers = self.ws.row_values(1)
                    print(f"[ERROR] Actual headers from sheet: {actual_headers}")
                    from collections import Counter
                    header_counts = Counter(actual_headers)
                    duplicates = [h for h, c in header_counts.items() if c > 1 and h != '']
                    empty_count = actual_headers.count('')
                    if duplicates:
                        print(f"[ERROR] ❌ DUPLICATE HEADERS IN GOOGLE SHEET: {duplicates}")
                    if empty_count > 0:
                        print(f"[ERROR] ❌ EMPTY COLUMN HEADERS IN GOOGLE SHEET: {empty_count} empty headers")
                except Exception as e3:
                    print(f"[ERROR] Could not diagnose header issue: {e3}")
                self._cache = []
                self._cache_timestamp = current_time
        
        return self._cache

    def is_duplicate(self, data: dict[str, any]) -> bool:
        # Only check for duplicates based on unique keys (e.g., execution_id, assignment_id, student_id)
        # If all keys in headers are present and match, consider it a duplicate
        for rec in self.get_all():
            if all(str(rec.get(h, "")) == str(data.get(h, "")) for h in self.headers if h in data):
                return True
        return False

    def append_row(self, data: dict[str, Any]) -> None:
        try:
            if not self.is_duplicate(data):
                row = [data.get(h, "") for h in self.headers]
                # Debug: Show first 10 values being written in order
                print(f"[DEBUG] Writing row with {len(row)} values in order: {row[:10]}...")
                self.ws.append_row(row)
                # Invalidate cache after successful write
                self._cache = {}
                self._cache_timestamp = 0
                print(f"[DEBUG] Cache invalidated after successful write")
        except Exception as e:
            print(f"[ERROR] Failed to append row: {e}")
            # Try to diagnose the issue
            try:
                actual_headers = self.ws.row_values(1)
                print(f"[DEBUG] Expected {len(self.headers)} columns, sheet has {len(actual_headers)} columns")
                print(f"[DEBUG] Expected headers: {self.headers}")
                print(f"[DEBUG] Actual headers: {actual_headers}")
            except:
                pass
            raise  # Re-raise the exception after logging

# Specific sheet classes
class AssignmentsSheet(Sheet):
    def __init__(self, client):
        # Support up to 25 questions
        question_columns = [f"Question{i}" for i in range(1, 26)]
        headers = ["date", "assignment_id"] + question_columns + ["GradingPrompt", "ConversationPrompt", "EnhancedFeedbackPrompt"]
        super().__init__(client, "assignments", headers)

    def fetch(self, assignment_id: str) -> dict[str, Any]:
        key = str(assignment_id).strip().lower()
        for rec in self.get_all():
            if str(rec.get("assignment_id", "")).strip().lower() == key:
                return rec
        return {}
    
    def get_active_questions(self, assignment_id: str) -> dict[str, str]:
        """Get only the filled questions for a given assignment."""
        rec = self.fetch(assignment_id)
        if not rec:
            return {}
        
        active_questions = {}
        for i in range(1, 26):
            question_key = f"Question{i}"
            question_text = rec.get(question_key, "").strip()
            if question_text:  # Only include non-empty questions
                active_questions[f"q{i}"] = question_text
        
        return active_questions

class StudentAssignmentsSheet(Sheet):
    def __init__(self, client):
        super().__init__(client, "student_assignments", [
            "student_id", "student_first_name", "student_last_name",
            "assignment_id", "assignment_due", "started"
        ])

    def fetch_current(self, student_id: str) -> dict[str, Any]:
        sid = student_id.strip()
        today = datetime.date.today()
        for rec in self.get_all():
            if str(rec.get("student_id", "")).strip() == sid:
                due_str = str(rec.get("assignment_due", "")).strip()
                due = None
                for fmt in ("%Y-%m-%d", "%m/%d/%Y"):  # ISO or US
                    try:
                        due = datetime.datetime.strptime(due_str, fmt).date()
                        break
                    except ValueError:
                        due = None
                if due and due >= today:
                    return rec
        return {}

class DataSheets:
    def __init__(self, creds: dict):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_obj = Credentials.from_service_account_info(creds, scopes=scopes)
        client = gspread.authorize(creds_obj)
        self.assignments = AssignmentsSheet(client)
        self.student_assignments = StudentAssignmentsSheet(client)
        
        # Build headers dynamically for up to 25 questions
        answer_columns = [f"q{i}_answer" for i in range(1, 26)]
        self.answers = Sheet(client, "student_answers", 
            ["execution_id", "assignment_id", "student_id"] + answer_columns + ["timestamp"]
        )
        
        # Build feedback and score columns for up to 25 questions
        feedback_columns = [f"feedback{i}" for i in range(1, 26)]
        score_columns = [f"score{i}" for i in range(1, 26)]
        # Group feedback columns first, then score columns (to match Google Sheet format)
        grading_columns = feedback_columns + score_columns
        grading_headers = ["execution_id", "assignment_id", "student_id"] + grading_columns + ["timestamp"]
        print(f"[INIT] Grading sheet headers (GROUPED format): {grading_headers[:10]}...{grading_headers[-5:]}")
        
        self.grading = Sheet(client, "feedback+grading", grading_headers)
        
        # Build evaluation columns for up to 25 questions
        new_feedback_columns = [f"new_feedback{i}" for i in range(1, 26)]
        new_score_columns = [f"new_score{i}" for i in range(1, 26)]
        # Group new_feedback columns first, then new_score columns (to match Google Sheet format)
        eval_columns = new_feedback_columns + new_score_columns
        eval_headers = ["execution_id", "assignment_id", "student_id"] + eval_columns + ["timestamp"]
        print(f"[INIT] Evaluation sheet headers (GROUPED format): {eval_headers[:10]}...{eval_headers[-5:]}")
        
        self.evaluation = Sheet(client, "feedback_evaluation", eval_headers)
        
        self.conversations = Sheet(client, "conversations", [
            "execution_id", "assignment_id", "student_id",
            "user_msg", "agent_msg", "timestamp"
        ])
    
    def get_latest_answers(self, student_id: str, assignment_id: str) -> dict[str, Any]:
        """Get the most recent answers for a student and assignment."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        latest_record = {}
        latest_timestamp = None
        
        for rec in self.answers.get_all():
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                timestamp_str = rec.get("timestamp", "")
                if timestamp_str and (latest_timestamp is None or timestamp_str > latest_timestamp):
                    latest_timestamp = timestamp_str
                    latest_record = rec
        
        return latest_record
    
    def get_all_answers_for_memory(self, student_id: str, assignment_id: str) -> List[dict[str, Any]]:
        """Get all answers for a student and assignment for memory loading."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        all_answers = []
        
        for rec in self.answers.get_all():
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                all_answers.append(rec)
        
        # Sort by timestamp to maintain chronological order
        all_answers.sort(key=lambda x: x.get("timestamp", ""))
        return all_answers
    
    def get_latest_grading(self, student_id: str, assignment_id: str) -> dict[str, Any]:
        """Get the most recent grading for a student and assignment."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        latest_record = {}
        latest_timestamp = None
        
        for rec in self.grading.get_all():
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                timestamp_str = rec.get("timestamp", "")
                if timestamp_str and (latest_timestamp is None or timestamp_str > latest_timestamp):
                    latest_timestamp = timestamp_str
                    latest_record = rec
        
        return latest_record
    
    def get_all_grading_for_memory(self, student_id: str, assignment_id: str) -> List[dict[str, Any]]:
        """Get all grading records for a student and assignment for memory loading."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        all_grading = []
        
        for rec in self.grading.get_all():
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                all_grading.append(rec)
        
        # Sort by timestamp to maintain chronological order
        all_grading.sort(key=lambda x: x.get("timestamp", ""))
        return all_grading
    
    def get_latest_conversation(self, student_id: str, assignment_id: str) -> dict[str, Any]:
        """Get the most recent conversation for a student and assignment."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        latest_record = {}
        latest_timestamp = None
        
        for rec in self.conversations.get_all():
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                timestamp_str = rec.get("timestamp", "")
                if timestamp_str and (latest_timestamp is None or timestamp_str > latest_timestamp):
                    latest_timestamp = timestamp_str
                    latest_record = rec
        
        return latest_record
    
    def get_all_conversations_for_memory(self, student_id: str, assignment_id: str) -> List[dict[str, Any]]:
        """Get all conversations for a student and assignment for memory loading."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        all_conversations = []
        
        for rec in self.conversations.get_all():
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                all_conversations.append(rec)
        
        # Sort by timestamp to maintain chronological order
        all_conversations.sort(key=lambda x: x.get("timestamp", ""))
        return all_conversations
    
    def update_started_status(self, student_id: str, assignment_id: str, started: str):
        """Update the started status for a student assignment."""
        sid = student_id.strip()
        aid = assignment_id.strip()
        
        # Find the row to update
        for i, rec in enumerate(self.student_assignments.get_all()):
            if (str(rec.get("student_id", "")).strip() == sid and 
                str(rec.get("assignment_id", "")).strip() == aid):
                # Update the started field
                row_num = i + 2  # +2 because sheets are 1-indexed and we have a header row
                self.student_assignments.ws.update_cell(row_num, 6, started)  # Column 6 is "started"
                break

# Initialize sheets
@st.cache_resource(show_spinner="Loading...")
def get_sheets() -> DataSheets:
    return DataSheets(GCP_CREDENTIALS)

sheets = get_sheets()

# Initialize prompt manager with sheets reference
@st.cache_resource
def get_prompt_manager(_sheets):
    """Initialize prompt manager with sheets reference. 
    The _sheets parameter ensures it's recreated if sheets changes."""
    pm = PromptManager(GCP_CREDENTIALS, sheets_manager=_sheets)
    return pm

prompt_manager = get_prompt_manager(sheets)

# --- OLD CONTEXT CACHE SYSTEM (COMMENTED OUT) ---
# class ContextCache:
#     """Manages context caches for questions and conversations."""
#     
#     def __init__(self):
#         # Initialize question caches with empty content
#         self.question_caches = {
#             'q1': '',
#             'q2': '', 
#             'q3': ''
#         }
#         self.conversation_cache = ''
#         self.question_counters = {'q1': 0, 'q2': 0, 'q3': 0}
#         self.conversation_counter = 0
#     
#     def initialize_question_cache(self, question_num: str, question_text: str):
#         """Initialize a question cache with the question text."""
#         self.question_caches[f'q{question_num}'] = f"<question_text>{question_text}</question_text>"
#         self.question_counters[f'q{question_num}'] = 0
#     
#     def add_response_and_feedback(self, question_num: str, response: str, feedback: str, score: str = ""):
#         """Add student response and feedback to question cache."""
#         q_key = f'q{question_num}'
#         self.question_counters[q_key] += 1
#         counter = self.question_counters[q_key]
#         
#         score_text = f" (Score: {score})" if score else ""
#         new_content = f"<response_{counter}>{response}</response_{counter}><feedback_{counter}>{feedback}{score_text}</feedback_{counter}>"
#         self.question_caches[q_key] += new_content
#     
#     def add_conversation(self, question: str, response: str):
#         """Add conversation Q&A to conversation cache."""
#         self.conversation_counter += 1
#         counter = self.conversation_counter
#         new_content = f"<conversation_question_{counter}>{question}</conversation_question_{counter}><conversation_response_{counter}>{response}</conversation_response_{counter}>"
#         self.conversation_cache += new_content
#     
#     def get_question_context(self, question_num: str) -> str:
#         """Get the full context for a specific question."""
#         return self.question_caches.get(f'q{question_num}', '')
#     
#     def get_conversation_context(self) -> str:
#         """Get the full conversation context."""
#         return self.conversation_cache
#     
#     def clear_all(self):
#         """Clear all caches."""
#         self.question_caches = {'q1': '', 'q2': '', 'q3': ''}
#         self.conversation_cache = ''
#         self.question_counters = {'q1': 0, 'q2': 0, 'q3': 0}
#         self.conversation_counter = 0

# Initialize context cache
# @st.cache_resource
# def get_context_cache():
#     return ContextCache()

# context_cache = get_context_cache()

# --- NEW LANGGRAPH MEMORY MANAGEMENT SYSTEM ---
class AssignmentState(MessagesState):
    """Enhanced state using LangGraph's MessagesState for automatic memory management."""
    
    # Core assignment data
    execution_id: str
    student_id: str
    assignment_id: str
    
    # Questions and answers (now supports variable number 1-25)
    questions: Dict[str, str]  # {"q1": "What is...", "q5": "Explain...", "q10": "How does..."}
    answers: Dict[str, str]   # {"q1": "Student answer...", "q5": "...", "q10": "..."}
    
    # Grading results (variable number 1-25)
    scores: Dict[str, int]    # {"q1": 8, "q5": 7, "q10": 9}
    feedback: Dict[str, str]  # {"q1": "Good work...", "q5": "Needs improvement...", "q10": "Excellent..."}
    
    # Session metadata
    session_metadata: Dict[str, Any]
    conversation_ready: bool
    
    # Legacy compatibility fields (for smooth transition)
    question_contexts: Dict[str, str]  # Maintains question-specific context for backward compatibility

# Initialize memory system
@st.cache_resource
def get_memory_system():
    """Initialize LangGraph memory system with persistence."""
    return MemorySaver()

memory_system = get_memory_system()

# Global state manager for the assignment session
class AssignmentMemoryManager:
    """Manages assignment state using LangGraph's memory system."""
    
    def __init__(self):
        self.memory = memory_system
        self.current_state = None
    
    def initialize_assignment_session(self, exec_id: str, sid: str, aid: str, questions: Dict[str, str]) -> AssignmentState:
        """Initialize a new assignment session with variable number of questions."""
        # Initialize answers and question_contexts dynamically based on provided questions
        answers = {q_key: "" for q_key in questions.keys()}
        question_contexts = {q_key: "" for q_key in questions.keys()}
        
        state = {
            "messages": [SystemMessage(content=f"Assignment session for student {sid} with {len(questions)} questions")],
            "execution_id": exec_id,
            "student_id": sid,
            "assignment_id": aid,
            "questions": questions,
            "answers": answers,
            "scores": {},
            "feedback": {},
            "session_metadata": {
                "start_time": datetime.datetime.now().isoformat(),
                "assignment_id": aid,
                "num_questions": len(questions)
            },
            "conversation_ready": True,
            "question_contexts": question_contexts
        }
        self.current_state = state
        return state
    
    def add_student_answer(self, question_num: str, answer: str):
        """Add a student's answer to the current state."""
        if self.current_state:
            self.current_state["answers"][f"q{question_num}"] = answer
            # Add to conversation history
            self.current_state["messages"].append(HumanMessage(content=f"Student answered Q{question_num}: {answer[:100]}..."))
    
    def add_grading_result(self, question_num: str, score: int, feedback: str):
        """Add grading results for a question."""
        if self.current_state:
            self.current_state["scores"][f"q{question_num}"] = score
            self.current_state["feedback"][f"q{question_num}"] = feedback
            
            # Add to conversation history
            self.current_state["messages"].append(AIMessage(content=f"Q{question_num} graded: {score}/10 - {feedback[:100]}..."))
            
            # Update question context for backward compatibility
            q_key = f"q{question_num}"
            if q_key not in self.current_state["question_contexts"]:
                self.current_state["question_contexts"][q_key] = ""
            
            # Add response and feedback to question context (maintaining backward compatibility)
            counter = len([msg for msg in self.current_state["messages"] if f"Q{question_num}" in msg.content])
            score_text = f" (Score: {score})"
            new_content = f"<response_{counter}>{self.current_state['answers'][f'q{question_num}']}</response_{counter}><feedback_{counter}>{feedback}{score_text}</feedback_{counter}>"
            self.current_state["question_contexts"][q_key] += new_content
    
    def add_conversation(self, question: str, response: str):
        """Add a conversation exchange to the memory."""
        if self.current_state:
            # Add to conversation history
            self.current_state["messages"].append(HumanMessage(content=question))
            self.current_state["messages"].append(AIMessage(content=response))
    
    def get_question_context(self, question_num: str) -> str:
        """Get question-specific context (backward compatibility)."""
        if self.current_state:
            return self.current_state["question_contexts"].get(f"q{question_num}", "")
        return ""
    
    def get_conversation_context(self) -> str:
        """Get conversation context from messages (backward compatibility)."""
        if self.current_state:
            # Convert messages to conversation context format for backward compatibility
            conversation_parts = []
            for msg in self.current_state["messages"]:
                if isinstance(msg, HumanMessage):
                    conversation_parts.append(f"Student: {msg.content}")
                elif isinstance(msg, AIMessage):
                    conversation_parts.append(f"AI: {msg.content}")
            return "\n".join(conversation_parts)
        return ""
    
    def get_full_conversation_history(self) -> List:
        """Get the full conversation history as messages."""
        if self.current_state:
            return self.current_state["messages"]
        return []
    
    def clear_session(self):
        """Clear the current session."""
        self.current_state = None
    
    def get_current_state(self) -> AssignmentState:
        """Get the current assignment state."""
        return self.current_state

# Initialize assignment memory manager
@st.cache_resource
def get_assignment_memory_manager():
    return AssignmentMemoryManager()

assignment_memory = get_assignment_memory_manager()

def load_previous_session_data(student_id: str, assignment_id: str) -> tuple[Dict[str, str], Dict[str, Any], str]:
    """
    Load previous session data for a student and assignment.
    Returns: (previous_answers, previous_feedback, latest_conversation_response)
    
    Note: No caching to ensure fresh data on every page load/refresh
    """
    try:
        print(f"[SESSION RESTORE] Loading FRESH data for student {student_id}, assignment {assignment_id}")
        
        # Get all data in one go to minimize API calls
        all_answers = sheets.get_all_answers_for_memory(student_id, assignment_id)
        all_grading = sheets.get_all_grading_for_memory(student_id, assignment_id)
        all_conversations = sheets.get_all_conversations_for_memory(student_id, assignment_id)
        
        # Find the most recent answers record
        latest_answers = {}
        if all_answers:
            latest_answers = max(all_answers, key=lambda x: x.get("timestamp", ""))
            print(f"[DEBUG] Latest answers record: {latest_answers}")
        
        # Find the matching feedback record with the same execution_id
        matching_feedback = {}
        if latest_answers and all_grading:
            execution_id = latest_answers.get("execution_id")
            print(f"[DEBUG] Looking for feedback with execution_id: {execution_id}")
            
            for grading_record in all_grading:
                if grading_record.get("execution_id") == execution_id:
                    matching_feedback = grading_record
                    print(f"[DEBUG] Found matching feedback record: {matching_feedback}")
                    break
        
        # Find the most recent conversation record
        latest_conversation = {}
        if all_conversations:
            latest_conversation = max(all_conversations, key=lambda x: x.get("timestamp", ""))
        
        # Prepare previous answers for UI (supports up to 25 questions)
        previous_answers = {}
        for i in range(1, 26):
            answer_key = f"q{i}_answer"  # Use correct column name from Google Sheet
            ui_key = f"q{i}"  # Use q1, q2, q3, ... for UI
            if answer_key in latest_answers:
                answer_value = latest_answers[answer_key]
                if answer_value:  # Only add non-empty answers
                    previous_answers[ui_key] = answer_value
                    print(f"[DEBUG] Found {answer_key}: {answer_value[:50]}...")
            else:
                print(f"[DEBUG] Missing {answer_key} in latest_answers")
        
        # Get latest conversation response for UI
        latest_conversation_response = latest_conversation.get("agent_msg", "") if latest_conversation else ""
        
        print(f"[SESSION RESTORE] Found {len(all_answers)} answer records, {len(all_grading)} grading records, {len(all_conversations)} conversation records")
        print(f"[SESSION RESTORE] Previous answers: {previous_answers}")
        print(f"[SESSION RESTORE] Matching feedback: {matching_feedback}")
        print(f"[SESSION RESTORE] Latest conversation response: {latest_conversation_response[:100]}..." if latest_conversation_response else "[SESSION RESTORE] No conversation response")
        
        return previous_answers, matching_feedback, latest_conversation_response
        
    except Exception as e:
        print(f"[ERROR] Failed to load previous session data: {e}")
        return {}, {}, ""

def load_session_data_into_memory(student_id: str, assignment_id: str):
    """
    Load all session data into memory system (separate from UI data loading).
    This is called only once per session.
    """
    try:
        print(f"[MEMORY LOAD] Loading data into memory for student {student_id}, assignment {assignment_id}")
        
        # Get all data for memory loading
        all_answers = sheets.get_all_answers_for_memory(student_id, assignment_id)
        all_grading = sheets.get_all_grading_for_memory(student_id, assignment_id)
        all_conversations = sheets.get_all_conversations_for_memory(student_id, assignment_id)
        
        # Load all answers and feedback into memory (supports up to 25 questions)
        for answer_record in all_answers:
            for i in range(1, 26):
                answer_key = f"q{i}_answer"  # Use correct column name from Google Sheet
                if answer_key in answer_record and answer_record[answer_key]:
                    assignment_memory.add_student_answer(str(i), answer_record[answer_key])
        
        for grading_record in all_grading:
            for i in range(1, 26):
                score_key = f"score{i}"
                feedback_key = f"feedback{i}"
                if score_key in grading_record and feedback_key in grading_record:
                    score = grading_record[score_key]
                    feedback = grading_record[feedback_key]
                    if score and feedback:
                        assignment_memory.add_grading_result(str(i), int(score) if str(score).isdigit() else 0, feedback)
        
        # Load all conversations into memory
        for conv_record in all_conversations:
            user_msg = conv_record.get("user_msg", "")
            agent_msg = conv_record.get("agent_msg", "")
            if user_msg and agent_msg:
                assignment_memory.add_conversation(user_msg, agent_msg)
        
        print(f"[MEMORY LOAD] Loaded {len(all_answers)} answer records, {len(all_grading)} grading records, {len(all_conversations)} conversation records into memory")
        
    except Exception as e:
        print(f"[ERROR] Failed to load session data into memory: {e}")

# Backward compatibility wrapper for existing code
class ContextCache:
    """Backward compatibility wrapper that uses the new memory system."""
    
    def __init__(self):
        self.memory_manager = assignment_memory
    
    def initialize_question_cache(self, question_num: str, question_text: str):
        """Initialize question cache (maintains backward compatibility)."""
        if self.memory_manager.current_state:
            self.memory_manager.current_state["question_contexts"][f"q{question_num}"] = f"<question_text>{question_text}</question_text>"
    
    def add_response_and_feedback(self, question_num: str, response: str, feedback: str, score: str = ""):
        """Add response and feedback (maintains backward compatibility)."""
        self.memory_manager.add_grading_result(question_num, int(score) if score else 0, feedback)
    
    def add_conversation(self, question: str, response: str):
        """Add conversation (maintains backward compatibility)."""
        self.memory_manager.add_conversation(question, response)
    
    def get_question_context(self, question_num: str) -> str:
        """Get question context (maintains backward compatibility)."""
        return self.memory_manager.get_question_context(question_num)
    
    def get_conversation_context(self) -> str:
        """Get conversation context (maintains backward compatibility)."""
        return self.memory_manager.get_conversation_context()
    
    def clear_all(self):
        """Clear all caches (maintains backward compatibility)."""
        self.memory_manager.clear_session()

# Initialize context cache for backward compatibility
@st.cache_resource
def get_context_cache():
    return ContextCache()

context_cache = get_context_cache()

# --- Simple Background Writer System ---
class SimpleBackgroundWriter:
    """Simple background writer for Google Sheets operations."""
    
    def __init__(self, sheets_instance):
        self.sheets = sheets_instance
        self.active_threads = []
    
    def write_async(self, operation_type: str, data: dict):
        """Start a background thread to write data to sheets."""
        def write_worker():
            sheet_obj = None
            try:
                print(f"[WRITE] Starting write for {operation_type} with {len(data)} fields")
                print(f"[WRITE] Data keys: {list(data.keys())[:15]}...")
                
                if operation_type == 'answers':
                    sheet_obj = self.sheets.answers
                    print(f"[WRITE] Answers sheet expects {len(sheet_obj.headers)} columns")
                    sheet_obj.append_row(data)
                elif operation_type == 'grading':
                    sheet_obj = self.sheets.grading
                    print(f"[WRITE] Grading sheet expects {len(sheet_obj.headers)} columns")
                    print(f"[WRITE] Grading sheet header order: {sheet_obj.headers[:10]}...{sheet_obj.headers[-5:]}")
                    sheet_obj.append_row(data)
                elif operation_type == 'evaluation':
                    sheet_obj = self.sheets.evaluation
                    print(f"[WRITE] Evaluation sheet expects {len(sheet_obj.headers)} columns")
                    sheet_obj.append_row(data)
                elif operation_type == 'conversations':
                    sheet_obj = self.sheets.conversations
                    sheet_obj.append_row(data)
                print(f"[DEBUG] Successfully wrote {operation_type} data to sheets")
                # Note: Cache is already invalidated in append_row() method
            except Exception as e:
                print(f"[ERROR] Failed to write {operation_type} data: {e}")
                # Try to get the actual headers from the sheet for debugging
                if sheet_obj:
                    try:
                        actual_headers = sheet_obj.ws.row_values(1)
                        expected_headers = sheet_obj.headers
                        print(f"[ERROR] Expected headers ({len(expected_headers)}): {expected_headers}")
                        print(f"[ERROR] Actual headers ({len(actual_headers)}): {actual_headers}")
                        # Find duplicates
                        from collections import Counter
                        header_counts = Counter(actual_headers)
                        duplicates = [header for header, count in header_counts.items() if count > 1]
                        if duplicates:
                            print(f"[ERROR] Duplicate headers found: {duplicates}")
                    except Exception as debug_error:
                        print(f"[ERROR] Could not retrieve headers for debugging: {debug_error}")
        
        # Start background thread
        thread = threading.Thread(target=write_worker, daemon=True)
        thread.start()
        self.active_threads.append(thread)
        
        # Clean up completed threads (keep only last 10)
        self.active_threads = [t for t in self.active_threads if t.is_alive()][-10:]
    
    def shutdown(self):
        """Wait for all active threads to complete."""
        for thread in self.active_threads:
            if thread.is_alive():
                thread.join(timeout=5)

# Initialize simple background writer
@st.cache_resource
def get_background_writer():
    return SimpleBackgroundWriter(sheets)

background_writer = get_background_writer()

# Initialize agent with streaming support
@st.cache_resource
def get_agent():
    """Get the appropriate LLM based on configuration."""
    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        llm = ChatGoogleGenerativeAI(
            model=DEFAULT_MODEL["gemini"],
            temperature=0,
            google_api_key=GEMINI_API_KEY,
            streaming=True,
            max_output_tokens=4000,
            request_timeout=60
        )
    else:
        llm = ChatOpenAI(
                model_name=DEFAULT_MODEL["openai"], 
            temperature=0,
            openai_api_key=OPENAI_API_KEY,
            streaming=True,  # Enable streaming
            max_tokens=4000,  # Increased limit to prevent truncation
            request_timeout=60  # Increased timeout for longer responses
        )
    return llm

agent = get_agent()

# Workflow functions

def prompt_student_id() -> Optional[str]:
    sid = st.text_input('Student ID:', key='sid')
    if not sid:
        st.info('Enter your Student ID to proceed.')
        return None
    return sid.strip()


def load_assignment(sid: str) -> Optional[dict[str, Any]]:
    rec = sheets.student_assignments.fetch_current(sid)
    if not rec:
        st.error('Invalid Student ID or no assignment due.')
        return None
    return rec


def load_questions(aid: str) -> Optional[dict[str, Any]]:
    """Load assignment record and return only active (filled) questions."""
    q = sheets.assignments.fetch(aid)
    if not q:
        st.error('Assignment questions not found.')
        return None
    
    # Get active questions (only those with content)
    active_questions = sheets.assignments.get_active_questions(aid)
    if not active_questions:
        st.error('No questions found for this assignment.')
        return None
    
    # Add active questions to the record
    q['active_questions'] = active_questions
    q['num_questions'] = len(active_questions)
    
    print(f"[DEBUG] Loaded {len(active_questions)} active questions for assignment {aid}")
    print(f"[DEBUG] Question keys: {list(active_questions.keys())}")
    
    return q


def record_answers(exec_id: str, sid: str, aid: str, answers: dict[str, str]) -> None:
    """Record answers using background writer for better performance. Supports variable number of questions."""
    data = {
        'execution_id': exec_id,
        'assignment_id': aid,
        'student_id': sid,
        'timestamp': datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
    }
    
    # Add all answers dynamically (supports up to 25 questions)
    for i in range(1, 26):
        q_key = f'q{i}'
        answer_key = f'q{i}_answer'
        data[answer_key] = answers.get(q_key, '')
    
    # Queue for background writing instead of blocking
    background_writer.write_async('answers', data)


# Removed grade_single_question function - now using _make_single_api_call for true parallelism

# --- Metadata Builder Functions ---

def build_grading_metadata(question_num: int, question_text: str, answer: str, all_questions: Dict[str, str], 
                          all_answers: Dict[str, str], previous_feedbacks: Dict[str, str] = None, 
                          previous_scores: Dict[str, int] = None) -> str:
    """Build metadata block for grading agent (per-question)."""
    metadata_parts = []
    
    # All questions
    metadata_parts.append("<all_questions>")
    for q_key, q_text in sorted(all_questions.items()):
        q_num = q_key.replace('q', '')
        metadata_parts.append(f"  <question_{q_num}>{q_text}</question_{q_num}>")
    metadata_parts.append("</all_questions>")
    
    # Current question being graded
    metadata_parts.append(f"<current_question_number>{question_num}</current_question_number>")
    metadata_parts.append(f"<current_question_text>{question_text}</current_question_text>")
    metadata_parts.append(f"<current_answer>{answer}</current_answer>")
    
    # All current answers
    metadata_parts.append("<all_current_answers>")
    for q_key, ans in sorted(all_answers.items()):
        if ans.strip():
            q_num = q_key.replace('q', '')
            metadata_parts.append(f"  <answer_{q_num}>{ans}</answer_{q_num}>")
    metadata_parts.append("</all_current_answers>")
    
    # Previous feedbacks and scores (if any)
    if previous_feedbacks or previous_scores:
        metadata_parts.append("<previous_grading>")
        for q_key in sorted(all_questions.keys()):
            q_num = q_key.replace('q', '')
            feedback = previous_feedbacks.get(f"feedback{q_num}", "") if previous_feedbacks else ""
            score = previous_scores.get(f"score{q_num}", "") if previous_scores else ""
            if feedback or score:
                metadata_parts.append(f"  <previous_q{q_num}>")
                if score:
                    metadata_parts.append(f"    <score>{score}</score>")
                if feedback:
                    metadata_parts.append(f"    <feedback>{feedback}</feedback>")
                metadata_parts.append(f"  </previous_q{q_num}>")
        metadata_parts.append("</previous_grading>")
    
    return "\n".join(metadata_parts)


def build_evaluation_metadata(all_questions: Dict[str, str], all_answers: Dict[str, str], 
                              current_feedbacks: Dict[str, str], current_scores: Dict[str, int]) -> str:
    """Build metadata block for evaluation agent (all questions)."""
    metadata_parts = []
    
    # All questions
    metadata_parts.append("<all_questions>")
    for q_key, q_text in sorted(all_questions.items()):
        q_num = q_key.replace('q', '')
        metadata_parts.append(f"  <question_{q_num}>{q_text}</question_{q_num}>")
    metadata_parts.append("</all_questions>")
    
    # All current answers
    metadata_parts.append("<all_current_answers>")
    for q_key, ans in sorted(all_answers.items()):
        if ans.strip():
            q_num = q_key.replace('q', '')
            metadata_parts.append(f"  <answer_{q_num}>{ans}</answer_{q_num}>")
    metadata_parts.append("</all_current_answers>")
    
    # Current feedbacks and scores
    metadata_parts.append("<current_grading>")
    for q_key in sorted(all_questions.keys()):
        q_num = q_key.replace('q', '')
        feedback = current_feedbacks.get(f"feedback{q_num}", "")
        score = current_scores.get(f"score{q_num}", "")
        if feedback or score:
            metadata_parts.append(f"  <grading_q{q_num}>")
            if score:
                metadata_parts.append(f"    <score>{score}</score>")
            if feedback:
                metadata_parts.append(f"    <feedback>{feedback}</feedback>")
            metadata_parts.append(f"  </grading_q{q_num}>")
    metadata_parts.append("</current_grading>")
    
    return "\n".join(metadata_parts)


def build_conversation_metadata(all_questions: Dict[str, str], all_answers: Dict[str, str], 
                                current_feedbacks: Dict[str, str] = None, current_scores: Dict[str, int] = None,
                                conversation_history: List = None) -> str:
    """Build metadata block for conversation agent (with conversation history)."""
    metadata_parts = []
    
    # All questions
    metadata_parts.append("<all_questions>")
    for q_key, q_text in sorted(all_questions.items()):
        q_num = q_key.replace('q', '')
        metadata_parts.append(f"  <question_{q_num}>{q_text}</question_{q_num}>")
    metadata_parts.append("</all_questions>")
    
    # All current answers
    metadata_parts.append("<all_current_answers>")
    for q_key, ans in sorted(all_answers.items()):
        if ans.strip():
            q_num = q_key.replace('q', '')
            metadata_parts.append(f"  <answer_{q_num}>{ans}</answer_{q_num}>")
    metadata_parts.append("</all_current_answers>")
    
    # Current feedbacks and scores (if any)
    if current_feedbacks or current_scores:
        metadata_parts.append("<current_grading>")
        for q_key in sorted(all_questions.keys()):
            q_num = q_key.replace('q', '')
            feedback = current_feedbacks.get(f"feedback{q_num}", "") if current_feedbacks else ""
            score = current_scores.get(f"score{q_num}", "") if current_scores else ""
            if feedback or score:
                metadata_parts.append(f"  <grading_q{q_num}>")
                if score:
                    metadata_parts.append(f"    <score>{score}</score>")
                if feedback:
                    metadata_parts.append(f"    <feedback>{feedback}</feedback>")
                metadata_parts.append(f"  </grading_q{q_num}>")
        metadata_parts.append("</current_grading>")
    
    # Conversation history
    if conversation_history:
        metadata_parts.append("<conversation_history>")
        conv_num = 1
        for msg in conversation_history:
            if isinstance(msg, HumanMessage):
                metadata_parts.append(f"  <student_message_{conv_num}>{msg.content}</student_message_{conv_num}>")
            elif isinstance(msg, AIMessage):
                metadata_parts.append(f"  <ai_message_{conv_num}>{msg.content}</ai_message_{conv_num}>")
                conv_num += 1
        metadata_parts.append("</conversation_history>")
    
    return "\n".join(metadata_parts)


# Orchestration text is now imported from prompt_manager


def run_grading_streaming(exec_id: str, sid: str, aid: str, answers: Dict[str, str]) -> Dict[str, Any]:
    """True parallel grading - all API calls made simultaneously. Supports variable number of questions (1-25)."""
    try:
        # Get active questions from session state
        all_questions = st.session_state.get('active_questions', {})
        
        # Get previous feedback from session state (if any)
        previous_feedback = st.session_state.get('feedback', {})
        
        # Determine which questions to grade based on provided answers
        questions_to_grade = []
        for q_key, answer in answers.items():
            if answer.strip():  # Only grade questions with answers
                # Extract question number from key (e.g., "q3" -> 3)
                q_num = int(q_key.replace('q', ''))
                questions_to_grade.append((q_num, q_key, answer))
        
        num_questions = len(questions_to_grade)
        print(f"[DEBUG] Grading {num_questions} questions: {[q[0] for q in questions_to_grade]}")
        
        # Try to get prompt from assignments sheet based on assignment_id
        prompt_template = prompt_manager.get_prompt_cached(aid, "grading")
        
        # Fall back to default if not found in sheet
        if not prompt_template:
            print(f"[DEBUG] No prompt found in sheet for assignment {aid}, using default grading prompt")
            prompt_template = get_default_prompts()["grading_prompt"]
        else:
            print(f"[DEBUG] Using custom grading prompt from sheet for assignment {aid}")
        
        # Print the actual prompt template being used
        print(f"[DEBUG] ===== GRADING PROMPT TEMPLATE =====")
        print(f"[DEBUG] {prompt_template[:500]}..." if len(prompt_template) > 500 else f"[DEBUG] {prompt_template}")
        print(f"[DEBUG] =====================================")
        
        # Prepare question-specific prompts for each LLM
        prompts = []
        for q_num, q_key, answer in questions_to_grade:
            # Get question text
            question_text = all_questions.get(q_key, f"Question {q_num}")
            
            # Build metadata block for this question
            metadata = build_grading_metadata(
                question_num=q_num,
                question_text=question_text,
                answer=answer,
                all_questions=all_questions,
                all_answers=answers,
                previous_feedbacks=previous_feedback if previous_feedback else None,
                previous_scores=previous_feedback if previous_feedback else None
            )
            
            # Build the structured prompt with admin orchestration
            orchestration_texts = get_orchestration_text()
            admin_section = orchestration_texts["grading_evaluation"]
            output_format = get_grading_output_format(q_num)
            
            question_prompt = f"""<data>
{metadata}
</data>

<admin>
{admin_section}
</admin>

<output_format>
{output_format}
</output_format>

<instructions>
{prompt_template}
</instructions>"""
            
            prompts.append((q_num, question_prompt))
        
        # Execute all API calls simultaneously (dynamic number of workers based on question count)
        with st.spinner(f"Grading your {num_questions} answer{'s' if num_questions != 1 else ''}..."):
            start_time = time.time()
            # Use min to ensure we don't create more threads than questions
            max_workers = min(num_questions, 10)  # Cap at 10 concurrent threads
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="grading") as executor:
                # Submit all API calls at once
                futures = []
                for question_num, prompt in prompts:
                    future = executor.submit(_make_single_api_call, question_num, prompt)
                    futures.append(future)
                
                print(f"[BENCHMARK] All {num_questions} API calls submitted at {time.time() - start_time:.3f}s")
                
                # Wait for ALL responses to complete
                results = []
                for i, future in enumerate(futures):
                    try:
                        result = future.result(timeout=60)  # 60 second timeout per question
                        results.append(result)
                        print(f"[BENCHMARK] Q{prompts[i][0]} API call completed at {time.time() - start_time:.3f}s")
                    except Exception as e:
                        q_num = prompts[i][0]
                        print(f"[ERROR] Q{q_num} API call failed: {e}")
                        results.append({
                            "execution_id": exec_id,
                            "student_id": sid,
                            f"score{q_num}": 5,
                            f"feedback{q_num}": f"API call failed: {str(e)}"
                        })
            
            total_time = time.time() - start_time
            print(f"[BENCHMARK] Total parallel grading time: {total_time:.3f}s")
            print(f"[BENCHMARK] Average time per question: {total_time/num_questions:.3f}s")
            print(f"[BENCHMARK] Questions completed: {len(results)}/{num_questions}")
        
        # Merge results from all questions
        merged_result = {
            "execution_id": exec_id,
            "assignment_id": aid,
            "student_id": sid,
            "timestamp": datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        }
        
        # Initialize all possible scores and feedback to empty/0
        for i in range(1, 26):
            merged_result[f"score{i}"] = 0
            merged_result[f"feedback{i}"] = ""
        
        # Fill in actual results
        for result in results:
            for i in range(1, 26):
                score_key = f"score{i}"
                feedback_key = f"feedback{i}"
                if score_key in result:
                    merged_result[score_key] = result[score_key]
                if feedback_key in result:
                    merged_result[feedback_key] = result[feedback_key]
        
        print("[DEBUG] Parallel API grading result:", {k: v for k, v in merged_result.items() if v})
        return merged_result
        
    except Exception as e:
        print(f"[ERROR] Parallel grading failed: {e}")
        st.error(f"Grading failed: {e}")
        # Return error result for all questions that were attempted
        error_result = {
            "execution_id": exec_id,
            "assignment_id": aid,
            "student_id": sid,
            "timestamp": datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        }
        for i in range(1, 26):
            error_result[f"score{i}"] = 5
            error_result[f"feedback{i}"] = "Grading error"
        return error_result


def _make_single_api_call(question_num: int, prompt: str) -> Dict[str, Any]:
    """Make a single API call to the configured LLM for grading with dedicated agent instance."""
    try:
        # Create a dedicated agent instance for this thread to avoid conflicts
        if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
            thread_agent = ChatGoogleGenerativeAI(
                model=DEFAULT_MODEL["gemini"],
                temperature=1,
                google_api_key=GEMINI_API_KEY,
                streaming=True,
                max_output_tokens=4000,
                request_timeout=60
            )
        else:
            thread_agent = ChatOpenAI(
                model_name=DEFAULT_MODEL["openai"], 
                temperature=1,
                openai_api_key=OPENAI_API_KEY,
                streaming=True,
                max_tokens=4000,
                request_timeout=60
            )
        
        # Use streaming for faster response
        response_text = ""
        for chunk in thread_agent.stream(prompt):
            if hasattr(chunk, 'content'):
                response_text += chunk.content
        
        response_preview = response_text[:50] + "..." if len(response_text) > 50 else response_text
        print(f"[DEBUG] Q{question_num} API response received: {response_preview}")
        
        # Parse JSON response
        result = {}
        try:
            import re
            json_match = re.search(r'\{.*?\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Fallback response - clean up any JSON artifacts
            clean_feedback = response_text
            # Remove common JSON artifacts
            clean_feedback = re.sub(r'```json\s*', '', clean_feedback)
            clean_feedback = re.sub(r'```\s*', '', clean_feedback)
            clean_feedback = re.sub(r'\{[^}]*\}', '', clean_feedback)  # Remove JSON objects
            clean_feedback = re.sub(r'"[^"]*":\s*"[^"]*"', '', clean_feedback)  # Remove key-value pairs
            clean_feedback = clean_feedback.strip()
            
            result = {
                f"score{question_num}": 5,
                f"feedback{question_num}": clean_feedback[:300] + "..." if len(clean_feedback) > 300 else clean_feedback if clean_feedback else "No feedback available"
            }
        
        return result
        
    except Exception as e:
        print(f"[ERROR] Q{question_num} API call failed: {e}")
        return {
            f"score{question_num}": 5,
            f"feedback{question_num}": f"Error grading question {question_num}: {str(e)}"
        }


def run_grading(exec_id: str, sid: str, aid: str, answers: Dict[str, str]) -> Dict[str, Any]:
    """Legacy function - now calls the optimized version."""
    return run_grading_streaming(exec_id, sid, aid, answers)


def run_evaluation_streaming(grade_res: Dict[str, Any]) -> Dict[str, Any]:
    """Optimized evaluation with streaming."""
    try:
        # Get assignment_id from grade_res
        aid = grade_res.get('assignment_id', '')
        
        # Get active questions from session state
        all_questions = st.session_state.get('active_questions', {})
        
        # Get current answers from assignment memory
        all_answers = {}
        if assignment_memory.current_state:
            all_answers = assignment_memory.current_state.get('answers', {})
        
        # Extract current feedbacks and scores from grade_res
        current_feedbacks = {}
        current_scores = {}
        for i in range(1, 26):
            feedback_key = f"feedback{i}"
            score_key = f"score{i}"
            if feedback_key in grade_res and grade_res[feedback_key]:
                current_feedbacks[feedback_key] = grade_res[feedback_key]
            if score_key in grade_res:
                score_val = grade_res[score_key]
                # Ensure score is numeric, handle empty strings from sheets
                try:
                    if score_val and str(score_val).strip():
                        current_scores[score_key] = int(float(score_val))
                    else:
                        current_scores[score_key] = 0
                except (ValueError, TypeError):
                    current_scores[score_key] = 0
        
        # Try to get prompt from assignments sheet based on assignment_id
        prompt_template = prompt_manager.get_prompt_cached(aid, "evaluation")
        
        # Fall back to default if not found in sheet
        if not prompt_template:
            print(f"[DEBUG] No prompt found in sheet for assignment {aid}, using default evaluation prompt")
            prompt_template = get_default_prompts()["evaluation_prompt"]
        else:
            print(f"[DEBUG] Using custom evaluation prompt from sheet for assignment {aid}")
        
        # Print the actual prompt template being used
        print(f"[DEBUG] ===== EVALUATION PROMPT TEMPLATE =====")
        print(f"[DEBUG] {prompt_template[:500]}..." if len(prompt_template) > 500 else f"[DEBUG] {prompt_template}")
        print(f"[DEBUG] ========================================")
        
        # Build metadata block for evaluation
        metadata = build_evaluation_metadata(
            all_questions=all_questions,
            all_answers=all_answers,
            current_feedbacks=current_feedbacks,
            current_scores=current_scores
        )
        
        # Determine number of questions for output format
        num_questions = len(all_questions)
        
        # Build the structured prompt with admin orchestration
        orchestration_texts = get_orchestration_text()
        admin_section = orchestration_texts["grading_evaluation"]
        output_format = get_evaluation_output_format(num_questions)
        
        prompt = f"""<data>
{metadata}
</data>

<admin>
{admin_section}
</admin>

<output_format>
{output_format}
</output_format>

<instructions>
{prompt_template}
</instructions>"""

        # Use streaming for faster response
        response_text = ""
        start_time = time.time()
        with st.spinner("Evaluating feedback..."):
            for chunk in agent.stream(prompt):
                if hasattr(chunk, 'content'):
                    response_text += chunk.content
        
        eval_time = time.time() - start_time
        response_preview = response_text[:50] + "..." if len(response_text) > 50 else response_text
        print(f"[BENCHMARK] Evaluation completed in {eval_time:.3f}s")
        print(f"[DEBUG] run_evaluation_streaming LLM response: {response_preview}")
        
        # Improved JSON parsing with multiple fallback strategies
        result = {}
        try:
            import re
            # Strategy 1: Look for JSON object with simpler pattern
            json_match = re.search(r'\{.*?\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # Strategy 2: Look for JSON array
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    # Strategy 3: Try to parse the entire response as JSON
                    result = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Strategy 4: If all JSON parsing fails, try to extract fields manually
            print("[WARNING] Could not parse JSON from evaluation response, attempting manual extraction")
            result = {
                "execution_id": grade_res.get('execution_id', ''),
                "student_id": grade_res.get('student_id', ''),
            }
            
            # Dynamically populate fallback for all questions in the assignment
            for i in range(1, num_questions + 1):
                result[f"new_score{i}"] = grade_res.get(f'score{i}', 0)
                result[f"new_feedback{i}"] = grade_res.get(f'feedback{i}', '')
            
            # Try to extract individual feedback fields from the response text
            try:
                import re
                # Look for new_feedback patterns for all questions dynamically
                for i in range(1, num_questions + 1):
                    feedback_pattern = rf'"new_feedback{i}":\s*"([^"]*)"'
                    score_pattern = rf'"new_score{i}":\s*(\d+)'
                    
                    feedback_match = re.search(feedback_pattern, response_text)
                    score_match = re.search(score_pattern, response_text)
                    
                    if feedback_match:
                        result[f"new_feedback{i}"] = feedback_match.group(1)
                    if score_match:
                        result[f"new_score{i}"] = int(score_match.group(1))
                        
            except Exception as e:
                print(f"[WARNING] Manual extraction failed: {e}")
                # Keep the original feedback as fallback
        
        # Ensure all required fields are present for sheet writing
        complete_result = {
            "execution_id": grade_res.get('execution_id', ''),
            "assignment_id": grade_res.get('assignment_id', ''),
            "student_id": grade_res.get('student_id', ''),
            "timestamp": datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        }
        
        # Initialize all possible new_score and new_feedback fields to empty/0
        for i in range(1, 26):
            complete_result[f"new_score{i}"] = 0
            complete_result[f"new_feedback{i}"] = ""
        
        # Fill in actual results from LLM response
        for key, value in result.items():
            if key.startswith(('new_score', 'new_feedback')):
                complete_result[key] = value
        
        print("[DEBUG] run_evaluation_streaming complete result:", {k: v for k, v in complete_result.items() if v and k.startswith('new_')})
        return complete_result
        
    except Exception as e:
        print(f"[ERROR] run_evaluation_streaming failed: {e}")
        st.error(f"Evaluation failed: {e}")
        # Return error result with all required fields
        error_result = {
            "execution_id": grade_res.get('execution_id', ''),
            "assignment_id": grade_res.get('assignment_id', ''),
            "student_id": grade_res.get('student_id', ''),
            "timestamp": datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        }
        for i in range(1, 26):
            error_result[f"new_score{i}"] = 0
            error_result[f"new_feedback{i}"] = "Evaluation error"
        return error_result


def run_evaluation(grade_res: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy function - now calls the optimized version."""
    return run_evaluation_streaming(grade_res)


def run_conversation_streaming(exec_id: str, sid: str, user_msg: str) -> Dict[str, Any]:
    """Optimized conversation with streaming and context cache integration."""
    try:
        # Get assignment_id from session state
        aid = st.session_state.get('assignment_id', '')
        
        # Get active questions from session state
        all_questions = st.session_state.get('active_questions', {})
        
        # Get current answers from assignment memory
        all_answers = {}
        if assignment_memory.current_state:
            all_answers = assignment_memory.current_state.get('answers', {})
        
        # Get current feedbacks and scores from session state
        current_feedback = st.session_state.get('feedback', {})
        current_feedbacks = {}
        current_scores = {}
        if current_feedback:
            for i in range(1, 26):
                feedback_key = f"feedback{i}"
                score_key = f"score{i}"
                # Check for both new_ and regular versions
                if f"new_{feedback_key}" in current_feedback and current_feedback[f"new_{feedback_key}"]:
                    current_feedbacks[feedback_key] = current_feedback[f"new_{feedback_key}"]
                elif feedback_key in current_feedback and current_feedback[feedback_key]:
                    current_feedbacks[feedback_key] = current_feedback[feedback_key]
                    
                # Extract and convert scores safely
                score_val = None
                if f"new_{score_key}" in current_feedback and current_feedback[f"new_{score_key}"]:
                    score_val = current_feedback[f"new_{score_key}"]
                elif score_key in current_feedback and current_feedback[score_key]:
                    score_val = current_feedback[score_key]
                
                if score_val is not None:
                    try:
                        if str(score_val).strip():
                            current_scores[score_key] = int(float(score_val))
                        else:
                            current_scores[score_key] = 0
                    except (ValueError, TypeError):
                        current_scores[score_key] = 0
        
        # Get conversation history from assignment memory
        conversation_history = []
        if assignment_memory.current_state:
            conversation_history = assignment_memory.current_state.get('messages', [])
        
        # Try to get prompt from assignments sheet based on assignment_id
        prompt_template = prompt_manager.get_prompt_cached(aid, "conversation")
        
        # Fall back to default if not found in sheet
        if not prompt_template:
            print(f"[DEBUG] No prompt found in sheet for assignment {aid}, using default conversation prompt")
            prompt_template = get_default_prompts()["conversation_prompt"]
        else:
            print(f"[DEBUG] Using custom conversation prompt from sheet for assignment {aid}")
        
        # Print the actual prompt template being used
        print(f"[DEBUG] ===== CONVERSATION PROMPT TEMPLATE =====")
        print(f"[DEBUG] {prompt_template[:500]}..." if len(prompt_template) > 500 else f"[DEBUG] {prompt_template}")
        print(f"[DEBUG] ==========================================")
        
        # Build metadata block for conversation
        metadata = build_conversation_metadata(
            all_questions=all_questions,
            all_answers=all_answers,
            current_feedbacks=current_feedbacks if current_feedbacks else None,
            current_scores=current_scores if current_scores else None,
            conversation_history=conversation_history if conversation_history else None
        )
        
        # Build the structured prompt with conversation orchestration
        orchestration_texts = get_orchestration_text()
        admin_section = orchestration_texts["conversation"]
        
        prompt = f"""<data>
{metadata}
<current_student_question>{user_msg}</current_student_question>
</data>

<admin>
{admin_section}
</admin>

<instructions>
{prompt_template}
</instructions>"""

        # Use streaming for faster response
        response_text = ""
        start_time = time.time()
        with st.spinner("Processing your question..."):
            for chunk in agent.stream(prompt):
                if hasattr(chunk, 'content'):
                    response_text += chunk.content
        
        conv_time = time.time() - start_time
        response_preview = response_text[:50] + "..." if len(response_text) > 50 else response_text
        print(f"[BENCHMARK] Conversation completed in {conv_time:.3f}s")
        print(f"[DEBUG] run_conversation_streaming LLM response: {response_preview}")
        
        result = {
            "execution_id": exec_id,
            "student_id": sid,
            "user_msg": user_msg,
            "agent_msg": response_text,
            "timestamp": datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        }
        
        print("[DEBUG] run_conversation_streaming extracted:", result)
        return result
        
    except Exception as e:
        print(f"[ERROR] run_conversation_streaming failed: {e}")
        st.error(f"Conversation failed: {e}")
        return {
            "execution_id": exec_id,
            "student_id": sid,
            "user_msg": user_msg,
            "agent_msg": "I'm sorry, I'm having trouble processing your question right now. Please try again.",
            "timestamp": datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        }


def run_conversation(exec_id: str, sid: str, user_msg: str) -> Dict[str, Any]:
    """Legacy function - now calls the optimized streaming version."""
    return run_conversation_streaming(exec_id, sid, user_msg)

# --- Legacy Context Gathering Functions Removed ---
# These functions are no longer needed since we use the ContextCache system
# which provides better performance and more structured context management

# Main UI loop

def main() -> None:
    # Handle scroll to top
    if SCROLL_AVAILABLE and st.session_state.get('scroll_to_top', False):
        scroll_to_here(0, key='scroll_to_top')
        st.session_state['scroll_to_top'] = False
    
    
    # --- Main container for app ---
    with st.container():
        sid = prompt_student_id()
        if not sid:
            return

        sa = load_assignment(sid)
        if not sa:
            return
        aid = str(sa['assignment_id'])
        
        # Store assignment_id in session state for use by conversation agent
        st.session_state['assignment_id'] = aid

        qrec = load_questions(aid)
        if not qrec:
            return

        # Ensure exec_id is generated once per assignment session
        if 'exec_id' not in st.session_state:
            st.session_state['exec_id'] = str(uuid.uuid4())
        exec_id = st.session_state['exec_id']
        
        # Get active questions from assignment record
        active_questions = qrec.get('active_questions', {})
        num_questions = qrec.get('num_questions', 0)
        
        # Store active_questions in session state for use by agents
        st.session_state['active_questions'] = active_questions
        
        print(f"[DEBUG] Active questions in main loop: {list(active_questions.keys())}")
        print(f"[DEBUG] Number of questions: {num_questions}")
        
        # Initialize assignment session with new memory system FIRST (before loading data)
        if not assignment_memory.current_state:
            assignment_memory.initialize_assignment_session(exec_id, sid, aid, active_questions)
            print(f"[MEMORY] Initialized new assignment session for student {sid} with {num_questions} questions")
        else:
            print(f"[MEMORY] Using existing assignment session for student {sid}")
        
        # Check if assignment has been started and load previous session data if needed
        started_status = sa.get('started', 'FALSE').upper()
        has_previous_data = False
        previous_answers = {}
        previous_feedback = {}
        latest_conversation_response = ""
        
        # Only load previous data if the assignment has been started (started == 'TRUE')
        if started_status == 'TRUE':
            # Check if there's previous data (answers or conversations) - use cached function
            previous_answers, previous_feedback, latest_conversation_response = load_previous_session_data(sid, aid)
            
            if previous_answers or previous_feedback or latest_conversation_response:
                has_previous_data = True
                print(f"[SESSION RESTORE] Found previous data for student {sid}, assignment {aid}")
                print(f"[SESSION RESTORE] previous_answers keys: {list(previous_answers.keys())}")
                print(f"[SESSION RESTORE] previous_feedback keys: {list(previous_feedback.keys())}")
                
                # Load all previous session data into memory (only once per session)
                # This now works because assignment_memory.current_state is initialized above
                if not st.session_state.get('memory_loaded', False):
                    load_session_data_into_memory(sid, aid)
                    st.session_state['memory_loaded'] = True
                
                # Always update session state with latest data from Google Sheets
                # This ensures refreshing the page loads the most recent submissions
                print(f"[SESSION RESTORE] Updating session state with latest data from Google Sheets")
                
                # Populate answer values
                for q_key, answer_value in previous_answers.items():
                    val_key = f'{q_key}_val'
                    st.session_state[val_key] = answer_value
                    print(f"[SESSION RESTORE] Updated {val_key} = {answer_value[:50]}...")
                
                # Populate feedback
                if previous_feedback:
                    st.session_state['feedback'] = previous_feedback
                    st.session_state['submitted'] = True
                    print(f"[SESSION RESTORE] Updated feedback with keys: {list(previous_feedback.keys())}")
                
                # Populate conversation
                if latest_conversation_response:
                    st.session_state['last_conversation_response'] = latest_conversation_response
                    print(f"[SESSION RESTORE] Updated conversation response")
        else:
            print(f"[SESSION] Assignment not started yet (started={started_status}) - loading fresh form")
        
        # Initialize question caches with question text (backward compatibility) - dynamic based on active questions
        for q_key, q_text in active_questions.items():
            # Extract question number from key (e.g., "q3" -> "3")
            q_num = q_key.replace('q', '')
            context_cache.initialize_question_cache(q_num, q_text)
        
        round_no = st.session_state.get('round', 1)
        st.markdown(f"<h3 style='margin-top:0.2rem; margin-bottom:0.7rem; font-size:1.08rem;'>📝 Round {round_no} ({num_questions} Question{'s' if num_questions != 1 else ''})</h3>", unsafe_allow_html=True)

        answers: dict[str, str] = {}
        # If we have previous feedback AND no current session state feedback, populate session state with it
        if previous_feedback and not st.session_state.get('feedback'):
            st.session_state['feedback'] = previous_feedback
            st.session_state['submitted'] = True
            print(f"[DEBUG] Feedback populated from previous session: {previous_feedback}")
        elif st.session_state.get('feedback'):
            print(f"[DEBUG] Using existing session state feedback: {st.session_state.get('feedback')}")
        
        # If we have a previous conversation response, populate session state with it
        if latest_conversation_response:
            st.session_state['last_conversation_response'] = latest_conversation_response
            print(f"[DEBUG] Conversation response populated from previous session: {latest_conversation_response[:100]}...")
        
        # Use session state feedback (which now contains previous feedback if available)
        fb = st.session_state.get('feedback')
        submitted = st.session_state.get('submitted', False)
        reset_counter = st.session_state.get('reset_counter', 0)
        
        # Clear retry completion flag if it exists
        if st.session_state.get('retry_completed', False):
            st.session_state['retry_completed'] = False
            print("[RETRY] Cleared retry_completed flag")
        
        print(f"[DEBUG] Main function - fb exists: {bool(fb)}, submitted: {submitted}")
        print(f"[DEBUG] Previous answers: {previous_answers}")
        print(f"[DEBUG] Previous feedback: {previous_feedback}")
        print(f"[DEBUG] Latest conversation response: {latest_conversation_response[:100]}..." if latest_conversation_response else "[DEBUG] No conversation response")
        
        # Debug: Show memory system status
        if assignment_memory.current_state:
            memory_state = assignment_memory.current_state
            print(f"[MEMORY DEBUG] Session active for student {memory_state['student_id']}")
            print(f"[MEMORY DEBUG] Messages count: {len(memory_state.get('messages', []))}")
            print(f"[MEMORY DEBUG] Scores: {memory_state.get('scores', {})}")
            print(f"[MEMORY DEBUG] Answers: {len([k for k, v in memory_state.get('answers', {}).items() if v])}/3")
        else:
            print("[MEMORY DEBUG] No active assignment session")

        # --- Questions and Answers (dynamically rendered based on active questions) ---
        for q_key, q_text in active_questions.items():
            # Extract question number from key (e.g., "q3" -> 3)
            q_num = int(q_key.replace('q', ''))
            
            st.markdown(f"<div class='question-card' style='margin-bottom:0.3rem; font-size:1.08rem;'><b>Q{q_num}:</b> {q_text}</div>", unsafe_allow_html=True)
            key = f'a{q_num}_r{round_no}_reset{reset_counter}'
            val_key = f'{q_key}_val'
            
            # If we have previous answers AND no current session state value, populate session state with them
            if previous_answers and q_key in previous_answers and not st.session_state.get(val_key):
                st.session_state[val_key] = previous_answers[q_key]
                print(f"[DEBUG] Q{q_num} populated from previous session: {previous_answers[q_key][:50]}...")
            elif st.session_state.get(val_key):
                print(f"[DEBUG] Q{q_num} using existing session state value: {st.session_state.get(val_key)[:50]}...")
            
            # Use session state value (which now contains previous answer if available, or retry answer if updated)
            current_value = st.session_state.get(val_key, '')
            print(f"[DEBUG] Q{q_num} current_value: {current_value[:50]}..." if current_value else f"[DEBUG] Q{q_num} current_value: (empty)")
            answers[q_key] = st.text_area("Your Answer", value=current_value, key=key, on_change=None)
            st.session_state[val_key] = answers[q_key]
            
            # After submission, show feedback/score under each answer
            if fb and submitted:
                score = fb.get(f'new_score{q_num}', fb.get(f'score{q_num}', 0))
                text = fb.get(f'new_feedback{q_num}', fb.get(f'feedback{q_num}', ''))
                try:
                    score = float(score) if score else 0
                except (ValueError, TypeError):
                    score = 0
                if score >= THRESHOLD_SCORE:
                    score_class = 'score-high'
                    emoji = '✅'
                elif score >= THRESHOLD_SCORE - 2:
                    score_class = 'score-mid'
                    emoji = '⚠️'
                else:
                    score_class = 'score-low'
                    emoji = '❌'
                st.markdown(f"""
                    <div class='feedback-score-card' style='background:rgba(180,255,80,0.18); color:#fff; border-radius:8px 8px 0 0; padding:1rem; margin-bottom:0; font-size:1.08rem;'>
                        <span class='{score_class}'>{emoji} Score: {score}/10</span>
                    </div>
                """, unsafe_allow_html=True)
                if text:
                    st.markdown(
                        f"""
                        <div style='background:rgba(180,255,80,0.18); color:#fff; border-radius:0 0 8px 8px; padding:1rem; margin-bottom:0.7rem; font-size:1.08rem; margin-top:0;'>
                            <b>Feedback:</b><br>{text}
                        </div>
                        """, unsafe_allow_html=True
                    )
                else:
                    st.info(f"No feedback available for Q{q_num}")

        # --- Submission logic ---
        st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)
        fb = st.session_state.get('feedback')
        awaiting_resubmit = st.session_state.get('awaiting_resubmit', False)
        
        if not fb and not awaiting_resubmit:
            # Define callback function for submission
            def handle_submit():
                # Prevent submission if any answer is empty (check all active questions)
                empty_answers = [q_key for q_key in active_questions.keys() if not answers.get(q_key, '').strip()]
                if empty_answers:
                    st.session_state['submit_error'] = 'Please fill in all answers before submitting.'
                    return
                
                # Process submission
                with st.spinner('Submitting your answers...'):
                    record_answers(exec_id, sid, aid, answers)
                    grade_res = run_grading(exec_id, sid, aid, answers)
                    if grade_res:
                        # Queue grading data for background writing
                        background_writer.write_async('grading', grade_res)
                        
                        # Populate context cache with responses and feedback for all active questions
                        for q_key in active_questions.keys():
                            q_num = q_key.replace('q', '')
                            response = answers.get(q_key, '')
                            feedback = grade_res.get(f'feedback{q_num}', '')
                            score = grade_res.get(f'score{q_num}', '')
                            
                            # Add to new memory system
                            assignment_memory.add_student_answer(q_num, response)
                            assignment_memory.add_grading_result(q_num, int(score) if score else 0, feedback)
                            
                            # Also add to backward compatibility cache
                            context_cache.add_response_and_feedback(q_num, response, feedback, score)
                        
                        # Update started status to TRUE if it was FALSE
                        if started_status == 'FALSE':
                            try:
                                sheets.update_started_status(sid, aid, 'TRUE')
                                print(f"[SESSION] Updated started status to TRUE for student {sid}, assignment {aid}")
                            except Exception as e:
                                print(f"[ERROR] Failed to update started status: {e}")
                        
                        # Store in session state for the rest of the app
                        st.session_state['feedback'] = grade_res
                        st.session_state['submitted'] = True
                        st.session_state['awaiting_resubmit'] = False
                        st.session_state['submit_error'] = None
                    else:
                        st.session_state['submit_error'] = 'Failed to grade your answers. Please try again.'
            
            # Show Submit Answers button with callback
            submit = st.button('Submit Answers', use_container_width=True, on_click=handle_submit)
            
            # Show any submission errors
            if st.session_state.get('submit_error'):
                st.error(st.session_state['submit_error'])
        # --- Completion/Follow-up logic ---
        if fb:
            st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)
            # Check scores for all active questions
            scores = []
            for q_key in active_questions.keys():
                q_num = int(q_key.replace('q', ''))
                score_value = fb.get(f'new_score{q_num}', fb.get(f'score{q_num}', 0))
                try:
                    score = float(score_value) if score_value else 0
                except (ValueError, TypeError):
                    score = 0
                scores.append(score)
            
            if all(score >= THRESHOLD_SCORE for score in scores):
                st.success(f'🎉 You have successfully completed this assignment! All {num_questions} questions passed!')
            else:
                passed = sum(1 for score in scores if score >= THRESHOLD_SCORE)
                st.warning(f'You need scores of {THRESHOLD_SCORE} or higher on all questions to complete this assignment. ({passed}/{num_questions} passed)')
                # If awaiting_resubmit, show resubmit button above conversation
                if awaiting_resubmit:
                    resubmit = st.button('Resubmit', key='resubmit_btn', use_container_width=True)
                    if resubmit:
                        # Submit new answers - check all active questions
                        empty_answers = [q_key for q_key in active_questions.keys() if not answers.get(q_key, '').strip()]
                        if empty_answers:
                            st.toast('Please fill in all answers before resubmitting.', icon='⚠️')
                        else:
                            with st.spinner('Submitting your answers...'):
                                record_answers(exec_id, sid, aid, answers)
                                grade_res = run_grading(exec_id, sid, aid, answers)
                                if grade_res:
                                    sheets.grading.append_row(grade_res)
                                    # Skip evaluation for faster response - use grading directly
                                    st.session_state['feedback'] = grade_res
                                    st.session_state['submitted'] = True
                                    st.session_state['awaiting_resubmit'] = False
                                else:
                                    st.error("Failed to grade your answers. Please try again.")
                            rerun()
                # Add enhanced feedback button
                col1, col2 = st.columns(2)
                with col1:
                    enhanced_feedback = st.button('Get Enhanced Feedback', key='enhanced_feedback_btn')
                    if enhanced_feedback:
                        with st.spinner('Getting enhanced feedback...'):
                            eval_res = run_evaluation(fb)
                            if eval_res:
                                # Queue evaluation data for background writing
                                background_writer.write_async('evaluation', eval_res)
                                st.session_state['feedback'] = eval_res
                                st.success('Enhanced feedback generated!')
                                rerun()
                            else:
                                st.error("Failed to get enhanced feedback.")
                
                with col2:
                    # Use a counter-based key to force clearing
                    conv_counter = st.session_state.get('conv_counter', 0)
                    user_q = st.text_input('Ask a follow-up question:', key=f'conv_{conv_counter}')
                
                # Only process if there's a new question and it hasn't been processed yet
                if user_q and user_q != st.session_state.get('last_processed_question', ''):
                    try:
                        conv_res = run_conversation(exec_id, sid, user_q)
                        if conv_res:
                            # Queue conversation data for background writing
                            background_writer.write_async('conversations', conv_res)
                            agent_msg = conv_res.get('agent_msg', conv_res.get('content', 'No response available'))
                            
                            # Add to conversation cache (both new and old systems)
                            assignment_memory.add_conversation(user_q, agent_msg)
                            context_cache.add_conversation(user_q, agent_msg)
                            
                            # Store the response in session state to persist it
                            st.session_state['last_conversation_response'] = agent_msg
                            
                            # Mark this question as processed and increment counter to clear input
                            st.session_state['last_processed_question'] = user_q
                            st.session_state['conv_counter'] = conv_counter + 1
                            
                            # Show success message and trigger rerun to clear input
                            st.success("Response generated!")
                            rerun()
                        else:
                            st.error("Failed to get a response. Please try again.")
                    except Exception as e:
                        st.error(f"Error during conversation: {e}")
                
                # Display the stored conversation response (from session state or previous data)
                conversation_response = st.session_state.get('last_conversation_response') or latest_conversation_response
                if conversation_response:
                    st.write("**AI Response:**")
                    st.write(conversation_response)
                # Show Retry button at the bottom if not awaiting_resubmit
                if not awaiting_resubmit:
                    retry = st.button('Retry', key='retry_btn', use_container_width=True)
                    if retry:
                        # Set retry mode to show new question blocks below
                        st.session_state['retry_mode'] = True
                        st.session_state['retry_counter'] = st.session_state.get('retry_counter', 0) + 1
                        
                        # Auto-scroll to retry section
                        if SCROLL_AVAILABLE:
                            st.session_state['scroll_to_retry'] = True
                        
                        rerun()

        # --- Retry Mode: Show new question blocks below everything ---
        if st.session_state.get('retry_mode', False):
            # Place scroll anchor at the beginning of retry section
            if SCROLL_AVAILABLE and st.session_state.get('scroll_to_retry', False):
                scroll_to_here(0, key='retry_section_anchor')
                st.session_state['scroll_to_retry'] = False
            
            st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
            st.markdown("---")
            st.markdown(f"<h2 style='text-align: center; margin-bottom: 1.5rem;'>🔄 Retry Assignment</h2>", unsafe_allow_html=True)
            st.markdown(f"<p style='text-align: center; color: #666; margin-bottom: 2rem;'>Fill in your new answers below and click Resubmit when ready.</p>", unsafe_allow_html=True)
            
            retry_answers: dict[str, str] = {}
            
            # Show retry question blocks - dynamically render based on active questions
            for q_key, q_text in active_questions.items():
                q_num = int(q_key.replace('q', ''))
                st.markdown(f"<div class='question-card' style='margin-bottom:0.3rem; font-size:1.08rem;'><b>Q{q_num}:</b> {q_text}</div>", unsafe_allow_html=True)
                retry_key = f'retry_a{q_num}_counter{st.session_state.get("retry_counter", 0)}'
                retry_val_key = f'retry_{q_key}_val'
                retry_answers[q_key] = st.text_area("Your New Answer", value=st.session_state.get(retry_val_key, ''), key=retry_key, on_change=None)
                st.session_state[retry_val_key] = retry_answers[q_key]
            
            # Retry submission buttons
            col1, col2 = st.columns(2)
            with col1:
                retry_submit = st.button('Resubmit New Answers', key='retry_submit_btn', use_container_width=True)
            with col2:
                cancel_retry = st.button('Cancel Retry', key='cancel_retry_btn', use_container_width=True)
            
            if retry_submit:
                # Prevent submission if any answer is empty - check all active questions
                empty_answers = [q_key for q_key in active_questions.keys() if not retry_answers.get(q_key, '').strip()]
                if empty_answers:
                    st.toast('Please fill in all answers before resubmitting.', icon='⚠️')
                else:
                    with st.spinner('Submitting your new answers...'):
                        # Record new answers
                        record_answers(exec_id, sid, aid, retry_answers)
                        # Grade new answers
                        grade_res = run_grading(exec_id, sid, aid, retry_answers)
                        if grade_res:
                            # Queue grading data for background writing
                            background_writer.write_async('grading', grade_res)
                            
                            # Populate context cache with retry responses and feedback for all active questions
                            for q_key in active_questions.keys():
                                q_num = q_key.replace('q', '')
                                response = retry_answers.get(q_key, '')
                                feedback = grade_res.get(f'feedback{q_num}', '')
                                score = grade_res.get(f'score{q_num}', '')
                                
                                # Add to new memory system
                                assignment_memory.add_student_answer(q_num, response)
                                assignment_memory.add_grading_result(q_num, int(score) if score else 0, feedback)
                                
                                # Also add to backward compatibility cache
                                context_cache.add_response_and_feedback(q_num, response, feedback, score)
                            
                            # FIX 1: Replace text in answer boxes at the top with new answers
                            for q_key in active_questions.keys():
                                st.session_state[f'{q_key}_val'] = retry_answers[q_key]
                                print(f"[RETRY] Updated session state {q_key}_val with: {retry_answers[q_key][:50]}...")
                            
                            # FIX 2: Erase any conversation text and reset conversation state
                            st.session_state['conversation_text'] = ''
                            st.session_state['last_processed_question'] = ''
                            st.session_state['conv_counter'] = 0
                            st.session_state['last_conversation_response'] = ''
                            
                            # Clear retry mode and reset to show new feedback
                            st.session_state['retry_mode'] = False
                            st.session_state['feedback'] = grade_res
                            st.session_state['submitted'] = True
                            st.session_state['awaiting_resubmit'] = False
                            
                            # Clear retry answer values for all active questions
                            for q_key in active_questions.keys():
                                st.session_state[f'retry_{q_key}_val'] = ''
                            
                            # FIX 3: Force a complete rerun to ensure updates are visible
                            st.session_state['retry_completed'] = True
                            st.session_state['reset_counter'] = st.session_state.get('reset_counter', 0) + 1
                            
                            # FIX 4: Trigger scroll to top
                            if SCROLL_AVAILABLE:
                                st.session_state['scroll_to_top'] = True
                            
                            st.success('New answers submitted successfully!')
                            st.rerun()
                        else:
                            st.error("Failed to grade your new answers. Please try again.")
            
            if cancel_retry:
                # Clear retry mode
                st.session_state['retry_mode'] = False
                # Clear retry answer values for all active questions
                for q_key in active_questions.keys():
                    st.session_state[f'retry_{q_key}_val'] = ''
                rerun()

    # --- Footer ---
    st.markdown("""
    <div class='footer'>
        <span>&middot; <a href='https://github.com/mudcario350/streamlitapp' target='_blank'>GitHub</a></span>
    </div>
    """, unsafe_allow_html=True)

# Launch with guaranteed write completion
def run_app():
    """Run the app with proper cleanup."""
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 App interrupted by user")
    except Exception as e:
        print(f"❌ App error: {e}")
    finally:
        print("🔄 Ensuring all writes complete before shutdown...")
        try:
            background_writer.shutdown()
            print("✅ All writes completed successfully")
        except Exception as e:
            print(f"⚠️ Error during shutdown: {e}")

# Run the app
run_app()

