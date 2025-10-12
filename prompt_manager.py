#!/usr/bin/env python3

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from typing import Dict, Optional
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
                "conversation": "ConversationPrompt"
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