# Gemini API Setup Guide

This guide explains how to set up Google's Gemini API for your LangGraph agents.

## Step 1: Get a Gemini API Key

1. **Visit Google AI Studio:**
   - Go to [Google AI Studio](https://aistudio.google.com/)
   - Sign in with your Google account

2. **Generate API Key:**
   - Click "Get API Key" in the left sidebar
   - Click "Create API Key"
   - Select an existing project or create a new one
   - Copy the generated API key (you'll only see it once!)

## Step 2: Configure Your Environment

### Option A: Streamlit Secrets (Recommended for Streamlit Cloud)

If you're deploying to Streamlit Cloud, add the Gemini API key to your secrets:

1. Go to your Streamlit app dashboard
2. Click "Settings" → "Secrets"
3. Add the following to your secrets:

```toml
[gemini]
api_key = "your_gemini_api_key_here"
```

### Option B: Environment Variables (Local Development)

For local development, set the environment variable:

**Linux/macOS:**
```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="your_gemini_api_key_here"
```

**Windows (Command Prompt):**
```cmd
set GEMINI_API_KEY=your_gemini_api_key_here
```

## Step 3: Switch to Gemini

Edit `config.py` and change the LLM provider:

```python
# Change this line:
LLM_PROVIDER = "gemini"  # Options: "openai" or "gemini"
```

## Step 4: Install Dependencies

Run the following command to install the required packages:

```bash
pip install -r requirements.txt
```

## Step 5: Test the Integration

1. Start your Streamlit app: `streamlit run app.py`
2. You should see "Powered by 🤖 Gemini" in the header
3. Test the grading functionality to ensure Gemini is working

## Troubleshooting

### Common Issues:

1. **"Gemini API key missing" error:**
   - Make sure you've added the API key to Streamlit secrets or environment variables
   - Check that the key is correctly formatted

2. **"API key not valid" error:**
   - Verify your API key is correct
   - Make sure you have access to the Gemini API

3. **Fallback to OpenAI:**
   - If Gemini setup fails, the app will automatically fall back to OpenAI
   - Check the console for warning messages

### Model Options:

You can change the Gemini model in `config.py`:

```python
DEFAULT_MODEL = {
    "openai": "gpt-4o-mini-2024-07-18",
    "gemini": "gemini-1.5-flash"  # or "gemini-1.5-pro"
}
```

Available Gemini models:
- `gemini-1.5-flash`: Faster, more cost-effective
- `gemini-1.5-pro`: More capable, higher quality responses

## Benefits of Using Gemini

- **Cost-effective:** Often cheaper than OpenAI models
- **Fast responses:** Optimized for speed
- **Google integration:** Works well with other Google services
- **Multimodal:** Supports text, images, and other formats

## Switching Back to OpenAI

To switch back to OpenAI, simply change the provider in `config.py`:

```python
LLM_PROVIDER = "openai"
```

The app will automatically use OpenAI without requiring any other changes.
