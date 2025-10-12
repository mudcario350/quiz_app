# Google Docs Prompt Setup Guide

This guide explains how to set up Google Docs to store your LangGraph prompts for the Dynamic AI Assignment app.

## Step 1: Create Google Docs

Create three separate Google Docs for your prompts:

1. **Grading Prompt Doc** - for the initial grading logic
2. **Evaluation Prompt Doc** - for the enhanced feedback logic  
3. **Conversation Prompt Doc** - for the follow-up conversation logic

## Step 2: Format Your Prompts

In each Google Doc, format your prompts using this structure:

```
GRADING_PROMPT:
You are an AI teaching assistant grading student answers. Please evaluate the following answers and provide feedback and scores.

Student ID: {student_id}
Execution ID: {execution_id}

Student Answers:
Q1: {q1}
Q2: {q2}
Q3: {q3}

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

Be thoughtful in your evaluation. Consider clarity, depth of understanding, and relevance to the questions.
```

## Step 3: Get Document IDs

1. Open each Google Doc
2. Copy the document ID from the URL:
   - URL format: `https://docs.google.com/document/d/DOCUMENT_ID/edit`
   - The DOCUMENT_ID is the long string between `/d/` and `/edit`

## Step 4: Update Configuration

Edit `config.py` and replace the placeholder document IDs:

```python
PROMPT_DOC_IDS = {
    "grading": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",  # Your actual doc ID
    "evaluation": "YOUR_EVALUATION_PROMPT_DOC_ID",
    "conversation": "YOUR_CONVERSATION_PROMPT_DOC_ID"
}
```

## Step 5: Set Up Permissions

Make sure your Google service account has access to the documents:

1. In each Google Doc, click "Share"
2. Add your service account email (found in your GCP credentials)
3. Give it "Viewer" permissions

## Step 6: Test the Setup

1. Run your Streamlit app
2. The app will automatically load prompts from Google Docs
3. If Google Docs fails, it will fall back to the default prompts

## Prompt Variables

Your prompts can use these variables that will be automatically filled:

### Grading Prompt Variables:
- `{student_id}` - The student's ID
- `{execution_id}` - The unique execution ID
- `{q1}`, `{q2}`, `{q3}` - Student answers

### Evaluation Prompt Variables:
- `{execution_id}` - The unique execution ID
- `{student_id}` - The student's ID
- `{previous_grading}` - JSON string of previous grading results

### Conversation Prompt Variables:
- `{context}` - Full context of the assignment session
- `{user_question}` - The student's follow-up question

## Troubleshooting

- **"Error loading prompt"**: Check document permissions and ID
- **"No prompt found"**: Verify the prompt name format (e.g., "GRADING_PROMPT:")
- **Fallback to defaults**: The app will use built-in prompts if Google Docs fails

## Benefits

- **Easy Editing**: Update prompts without code changes
- **Version Control**: Google Docs maintains version history
- **Collaboration**: Multiple people can edit prompts
- **No Deployment**: Changes take effect immediately
- **Fallback Safety**: App continues working even if Google Docs is down 