# Dynamic AI Quiz Application

A sophisticated AI-powered quiz/assignment system built with Streamlit, LangGraph, and Google Sheets integration. This application supports **1-25 variable questions** per assignment with intelligent grading, conversation features, and comprehensive memory management.

## Features

### 🎯 Core Features
- **Variable Question Support**: Create assignments with 1-25 questions
- **Parallel AI Grading**: Grades all questions simultaneously using up to 10 concurrent threads
- **Intelligent Feedback**: AI-powered feedback with scoring on 1-10 scale
- **Enhanced Feedback**: Get deeper insights on your performance
- **Interactive Conversations**: Ask follow-up questions about your answers
- **Retry Mechanism**: Revise and resubmit answers to improve scores
- **Session Persistence**: Resume assignments across sessions
- **Memory Management**: LangGraph-based memory system tracks all interactions

### 🤖 LLM Support
- OpenAI (GPT-4, GPT-4o-mini)
- Google Gemini (Gemini 2.5 Flash)

### 📊 Data Management
- Google Sheets integration for all data storage
- Real-time background writing for better performance
- Automatic session restoration
- Assignment tracking and status management

## Architecture

### Tech Stack
- **Frontend**: Streamlit
- **AI Orchestration**: LangGraph (not n8n)
- **LLM Providers**: OpenAI, Google Gemini
- **Data Storage**: Google Sheets (via gspread)
- **Memory**: LangGraph MemorySaver

### Key Components
- `app.py` - Main Streamlit application
- `config.py` - Configuration and secrets management
- `prompt_manager.py` - Dynamic prompt management with Google Docs integration

## Setup Instructions

### Prerequisites
- Python 3.8+
- Google Cloud Platform account
- OpenAI API key or Google Gemini API key
- Google Sheets API access

### 1. Clone and Install

```bash
cd quiz_app
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Secrets

Create `.streamlit/secrets.toml`:

```toml
[openai]
api_key = "your-openai-api-key"

[gemini]
api_key = "your-gemini-api-key"

[gcp]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "your-cert-url"
```

See `GEMINI_SETUP.md` and `GOOGLE_DOCS_SETUP.md` for detailed setup instructions.

### 3. Configure Google Sheets

Create a Google Sheet named "n8nTest" (or update `SPREADSHEET_NAME` in `config.py`) with these tabs:

#### assignments
Columns: `date`, `assignment_id`, `Question1` through `Question25`, `GradingPrompt`, `ConversationPrompt`

#### student_assignments
Columns: `student_id`, `student_first_name`, `student_last_name`, `assignment_id`, `assignment_due`, `started`

#### student_answers
Columns: `execution_id`, `assignment_id`, `student_id`, `q1_answer` through `q25_answer`, `timestamp`

#### feedback+grading
Columns: `execution_id`, `assignment_id`, `student_id`, `feedback1`, `score1` through `feedback25`, `score25`, `timestamp`

#### feedback_evaluation
Columns: `execution_id`, `assignment_id`, `student_id`, `new_feedback1`, `new_score1` through `new_feedback25`, `new_score25`, `timestamp`

#### conversations
Columns: `execution_id`, `assignment_id`, `student_id`, `user_msg`, `agent_msg`, `timestamp`

### 4. Run the Application

```bash
streamlit run app.py
```

## Usage

### Creating Assignments

1. Add a row to the `assignments` sheet
2. Fill in `assignment_id`, `date`, and as many questions as you want (1-25)
3. Leave unused question columns empty
4. Optionally add custom `GradingPrompt` and `ConversationPrompt`

**Example - 5 Question Assignment:**
```
assignment_id: ASSIGN001
date: 2025-10-12
Question1: What is artificial intelligence?
Question2: Explain machine learning.
Question3: Define neural networks.
Question4: What is deep learning?
Question5: Describe natural language processing.
Question6-25: (leave empty)
```

### Assigning to Students

Add rows to `student_assignments` sheet:
```
student_id: STUDENT001
student_first_name: John
student_last_name: Doe
assignment_id: ASSIGN001
assignment_due: 2025-10-20
started: FALSE
```

### Student Workflow

1. **Enter Student ID**: Students log in with their ID
2. **View Questions**: System loads and displays active questions
3. **Submit Answers**: Fill in all answers and submit
4. **Receive Feedback**: AI grades and provides feedback for each question
5. **Pass/Retry**: 
   - If all scores ≥ 8: Assignment complete! 🎉
   - If any scores < 8: Use conversation feature or retry
6. **Conversation**: Ask follow-up questions about feedback
7. **Retry**: Submit revised answers to improve scores

## Variable Questions System

### How It Works

The system automatically detects how many questions are filled in the `assignments` sheet and adapts:

- **1 question**: Displays 1 question, grades in ~3-5 seconds
- **3 questions**: Displays 3 questions, grades in ~5-8 seconds  
- **10 questions**: Displays 10 questions, grades in ~8-12 seconds
- **25 questions**: Displays 25 questions, grades in ~12-20 seconds

### Parallel Grading

- Creates N parallel grading threads for N questions
- Maximum 10 concurrent API calls (configurable)
- Each question graded independently
- Significantly faster than sequential grading

### Performance

- Small assignments (1-3 questions): ~5 seconds
- Medium assignments (5-10 questions): ~10 seconds
- Large assignments (15-25 questions): ~15-20 seconds

See `VARIABLE_QUESTIONS_GUIDE.md` for technical details.

## Configuration

### config.py Options

```python
SPREADSHEET_NAME = "n8nTest"  # Your Google Sheet name
THRESHOLD_SCORE = 8.0  # Passing score (1-10 scale)
LLM_PROVIDER = "gemini"  # "openai" or "gemini"
DEFAULT_MODEL = {
    "openai": "gpt-4o-mini-2024-07-18",
    "gemini": "gemini-2.5-flash"
}
```

### Customizing Prompts

You can customize grading and conversation prompts:

1. **Sheet-based**: Add prompts to `GradingPrompt` and `ConversationPrompt` columns
2. **Google Docs**: Use Google Docs integration (see `GOOGLE_DOCS_SETUP.md`)
3. **Code-based**: Modify defaults in `prompt_manager.py`

## Testing

See `TESTING_CHECKLIST.md` for comprehensive testing instructions.

Quick test:
1. Create test assignments with 1, 3, 5, and 10 questions
2. Assign to test student
3. Complete full workflow for each
4. Verify grading, feedback, and conversation features

## Deployment

### Deploy to Streamlit Cloud

```bash
./deploy.sh
```

Or manually:
1. Push to GitHub
2. Connect repository to Streamlit Cloud
3. Add secrets in Streamlit Cloud dashboard
4. Deploy!

### Environment Variables

Required secrets (add to Streamlit Cloud or `.streamlit/secrets.toml`):
- `openai.api_key` - OpenAI API key
- `gemini.api_key` - Google Gemini API key  
- `gcp.*` - Google Cloud Platform service account credentials

## Documentation

- `VARIABLE_QUESTIONS_GUIDE.md` - Technical guide for variable questions
- `TESTING_CHECKLIST.md` - Comprehensive testing checklist
- `GEMINI_SETUP.md` - Google Gemini setup instructions
- `GOOGLE_DOCS_SETUP.md` - Google Docs prompt integration
- `MEMORY_IMPLEMENTATION_SUMMARY.md` - LangGraph memory system
- `PARALLEL_INTEGRATION_GUIDE.md` - Parallel grading architecture

## Troubleshooting

### "No questions found for this assignment"
- Ensure at least one Question column (Question1-Question25) is filled
- Check assignment_id matches between sheets

### Grading takes too long
- Check your API rate limits
- Adjust `max_workers` in `run_grading_streaming()` function
- Consider using faster models (e.g., gpt-4o-mini, gemini-flash)

### Session state issues
- Clear browser cache
- Try incognito/private browsing mode
- Check that student_id and assignment_id are consistent

### API errors
- Verify API keys are correct
- Check API usage/billing limits
- Ensure service account has Sheets API access

## Features in Detail

### Memory Management
- LangGraph-based persistent memory
- Tracks all questions, answers, and feedback
- Maintains conversation history
- Enables context-aware AI responses

### Parallel Grading
- ThreadPoolExecutor for concurrent API calls
- Configurable worker count (default: 10)
- Automatic timeout handling (60s per question)
- Robust error recovery

### Background Writing
- Non-blocking writes to Google Sheets
- Queue-based architecture
- Automatic retry on failure
- Ensures data persistence

## Contributing

This is a private project. For questions or issues, contact the development team.

## License

Proprietary - All rights reserved

## Support

For setup assistance:
1. Check documentation files
2. Review error messages in console
3. Verify all secrets are configured
4. Test with simple 1-question assignment first

## Changelog

### v2.0 (October 2025)
- ✨ Variable questions support (1-25 questions)
- ⚡ Parallel grading for all questions
- 🎨 Dynamic UI rendering
- 💾 Enhanced memory management
- 📊 Improved data persistence

### v1.0 (Initial Release)
- ✅ Fixed 3-question assignments
- 🤖 AI-powered grading
- 💬 Conversation feature
- 🔄 Retry mechanism
- 📈 Google Sheets integration

