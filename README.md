# GitHub Voice-to-SQL Agent

An AI-powered, voice-activated database assistant that translates natural language questions into highly optimized Google Standard SQL, executes them against the `bigquery-public-data.github_repos` dataset, and returns conversational answers. 

This project features a **Self-Healing SQL Loop** that automatically detects BigQuery syntax errors or high-cost queries (via dry-runs) and instructs the LLM to fix its own code before returning the final result.

## Features

* **Dual Interfaces**: Includes a polished web UI (Streamlit) and a fast, low-latency Terminal UI with local Text-to-Speech (TTS) and Speech-to-Text (STT).
* **Self-Healing SQL**: Automatically corrects `UNNEST` array errors, invalid table joins, and type mismatches.
* **Cost Guardrails**: Uses BigQuery's `dry_run` feature to estimate query costs. Queries scanning over 150 GB are automatically blocked and sent back to the LLM for optimization (e.g., adding strict `WHERE` clauses).
* **Local LLM**: Powered by `ollama` (Llama 3) for privacy and zero API costs on the LLM side.

## Tech Stack

* **Frontend**: Streamlit (`app.py`), Rich Console (`main.py`)
* **AI / LLM**: Ollama (Llama 3 8B)
* **Database**: Google Cloud BigQuery
* **Audio**: `streamlit-mic-recorder` (Web), `RealtimeSTT` & `RealtimeTTS` (Terminal)

---

## Setup & Installation

### 1. Prerequisites
* **Python 3.9+** installed.
* **Ollama** installed and running locally. Run `ollama run llama3` in your terminal to pull the required model.
* A **Google Cloud Project** with the BigQuery API enabled.
* A **Service Account JSON Key** with `BigQuery User` and `BigQuery Data Viewer` roles.

### 2. Clone and Install
```bash
# Clone the repository
git clone [https://github.com/yourusername/voice-to-bq-project.git](https://github.com/yourusername/voice-to-bq-project.git)
cd voice-to-bq-project

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies (ensure you have these in your requirements.txt)
pip install streamlit ollama google-cloud-bigquery streamlit-mic-recorder rich RealtimeSTT RealtimeTTS
