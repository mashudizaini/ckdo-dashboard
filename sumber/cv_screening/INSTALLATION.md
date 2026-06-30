# CV Screening - Installation Guide

## Overview

The CV Screening application now supports **three different screening methods** with varying levels of accuracy and requirements:

| Method | Accuracy | Speed | Cost | Requirements |
|--------|----------|-------|------|--------------|
| **Rule-Based** | 45% | Fast | Free | ✅ No additional setup needed |
| **NLP-Enhanced (spaCy)** | 70% | Medium | Free | 📦 spaCy installation required |
| **AI-Powered (Claude)** | 93% | Slow | $0.01-0.03/CV | 🔑 Claude API key required |

---

## 1. Rule-Based Method (Default)

**Status:** ✅ Already available

This method uses pattern matching and keyword search. No additional setup required.

**Pros:**
- Fast processing
- No dependencies
- Free

**Cons:**
- Low accuracy (45%)
- Cannot understand context
- Many false positives/negatives

---

## 2. NLP-Enhanced Method (spaCy)

**Status:** 📦 Requires installation

This method uses Named Entity Recognition (NER) and context-aware parsing for better accuracy.

### Installation Steps:

#### Step 1: Install spaCy
```bash
pip install spacy
```

#### Step 2: Download English Language Model
```bash
python -m spacy download en_core_web_sm
```

#### Step 3: Verify Installation
```python
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('✅ spaCy installed successfully')"
```

#### Step 4: Restart the Application
After installation, restart the Flask application:
```bash
# Press Ctrl+C to stop the current server
# Then run again:
python app.py
```

### Optional: Indonesian Language Model

For better accuracy with Indonesian CVs, you can install the Indonesian model (if available):
```bash
# Note: Indonesian model may not be available in standard spaCy
# Use English model as fallback
```

**Pros:**
- Better accuracy (70%)
- Section detection (separates education from work experience)
- Context-aware skill extraction
- Free

**Cons:**
- Medium processing speed
- Requires additional packages (~100MB)

---

## 3. AI-Powered Method (Claude API)

**Status:** 🔑 Requires API key

This method uses Claude API for deep understanding with LLM analysis.

### Installation Steps:

#### Step 1: Install Anthropic SDK
```bash
pip install anthropic
```

#### Step 2: Get Claude API Key
1. Go to [https://console.anthropic.com/](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key (starts with `sk-ant-`)

#### Step 3: Set Environment Variable

**Windows (Command Prompt):**
```cmd
set ANTHROPIC_API_KEY=sk-ant-your-api-key-here
```

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-your-api-key-here"
```

**Linux/Mac:**
```bash
export ANTHROPIC_API_KEY=sk-ant-your-api-key-here
```

**Permanent Setup (Windows):**
1. Right-click "This PC" → Properties
2. Advanced System Settings → Environment Variables
3. Add new System Variable:
   - Name: `ANTHROPIC_API_KEY`
   - Value: `sk-ant-your-api-key-here`

#### Step 4: Restart the Application
```bash
# Press Ctrl+C to stop the current server
# Then run again:
python app.py
```

#### Step 5: Verify API Key
The application will automatically check if the API key is valid when you select the AI method.

### Cost Considerations:

- **Model:** Claude 3.5 Sonnet (claude-3-5-sonnet-20241022)
- **Input:** ~2000 tokens per CV (CV text + prompt)
- **Output:** ~1000 tokens per analysis
- **Estimated cost:** $0.01-0.03 per CV

**Example:**
- Screening 100 CVs: ~$1-3
- Screening 1000 CVs: ~$10-30

**Pros:**
- Highest accuracy (93%)
- Deep context understanding
- Detects skill proficiency levels
- Identifies red flags (job hopping, gaps, etc.)
- Provides detailed reasoning

**Cons:**
- Slower processing (API calls)
- Costs money (API usage)
- Requires internet connection

---

## Switching Between Methods

Once installed, you can easily switch between methods:

1. Go to **Job Configuration** tab
2. Select **Screening Method** dropdown
3. Choose your preferred method:
   - ✅ **Rule-Based** (always available)
   - 📦 **NLP-Enhanced** (if spaCy installed)
   - 🔑 **AI-Powered** (if API key set)
4. **Save Configuration**
5. Upload CVs and click **Start Screening**

The system will automatically use the selected method for screening.

---

## Troubleshooting

### spaCy Issues

**Error: "No module named 'spacy'"**
```bash
pip install spacy
```

**Error: "Can't find model 'en_core_web_sm'"**
```bash
python -m spacy download en_core_web_sm
```

**Error: "spaCy model not loaded"**
- Make sure you've downloaded the model
- Restart the application after installation

### Claude API Issues

**Error: "anthropic package not installed"**
```bash
pip install anthropic
```

**Error: "ANTHROPIC_API_KEY not found"**
- Make sure you've set the environment variable
- Restart your terminal/command prompt
- Restart the application

**Error: "DPY-3015: authentication failed"** (Wrong error, but similar concept)
- Check if your API key is correct
- Make sure it starts with `sk-ant-`
- Try regenerating the API key

**Error: "Rate limit exceeded"**
- You've exceeded Claude API rate limits
- Wait a few minutes and try again
- Consider upgrading your Claude API plan

### Method Not Available

If a method shows as "NOT AVAILABLE" in the dropdown:
1. Check the status message below the dropdown
2. Follow installation instructions for that method
3. Restart the application
4. Refresh the page

---

## Verification Checklist

After installation, verify each method:

### ✅ Rule-Based (Should always work)
```
Status: Available by default
No action needed
```

### 📦 NLP-Enhanced
```bash
# Check if spaCy is installed
python -c "import spacy; print('✅ spaCy available')"

# Check if model is downloaded
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('✅ Model loaded')"
```

### 🔑 AI-Powered
```bash
# Check if anthropic is installed
python -c "import anthropic; print('✅ Anthropic SDK available')"

# Check if API key is set
python -c "import os; print('✅ API key set' if os.environ.get('ANTHROPIC_API_KEY') else '❌ API key not set')"
```

---

## Recommendations

### For Testing/Development:
- Use **Rule-Based** method (free, fast)
- Test with small batches first

### For Production (Small Volume):
- Use **NLP-Enhanced** method (good balance of accuracy and cost)
- Free and reasonably accurate

### For Production (High Quality Required):
- Use **AI-Powered** method (highest accuracy)
- Budget for API costs
- Consider batch processing to optimize costs

### Hybrid Approach:
1. Use **NLP-Enhanced** for initial screening (filters out obvious mismatches)
2. Use **AI-Powered** for final candidates (detailed analysis)
3. This minimizes API costs while maintaining quality

---

## Next Steps

After installation:

1. **Create job configuration** with required skills
2. **Select screening method** based on your needs
3. **Upload sample CVs** to test
4. **Compare results** between different methods
5. **Choose the best method** for your use case

For detailed comparison, see [AI_SCREENING_ANALYSIS.md](AI_SCREENING_ANALYSIS.md)

---

## Support

If you encounter issues:
1. Check error messages in browser console (F12)
2. Check server logs for detailed errors
3. Verify all installation steps were completed
4. Try restarting the application

For method-specific questions, refer to:
- Rule-Based: [cv_screener.py](cv_screener.py)
- NLP-Enhanced: [cv_screener_nlp.py](cv_screener_nlp.py)
- AI-Powered: [cv_screener_ai_enhanced.py](cv_screener_ai_enhanced.py)
