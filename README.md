# BigQuery Voice-SQL Architect 

An intelligent, voice-controlled interface for querying Google BigQuery using local LLMs. This project enables users to perform complex data analysis on the GitHub Public Dataset through natural speech, featuring a self-correcting SQL generation engine.

## Key Features
* **Voice-to-SQL Pipeline:** Uses `RealtimeSTT` and `RealtimeTTS` for a seamless, low-latency conversational experience.
* **Self-Healing SQL Loop:** Automatically catches `BadRequest` exceptions from BigQuery and feeds the error back to the LLM to fix syntax on the fly.
* **Advanced Analytics:** Custom prompt engineering enables the model to handle complex BigQuery structures, including `UNNEST()` for arrays and Window Functions (e.g., `RANK() OVER`).
* **Local LLM Integration:** Powered by Llama 3 (GGUF) via `llama-cpp-python` for privacy and cost-efficiency.
* **Real-time Feedback:** Provides instant audio acknowledgments while processing queries and speaks the final data insights naturally.

## Tech Stack
* **Language:** Python 3.10+
* **Cloud:** Google Cloud Platform (BigQuery)
* **LLM:** Meta Llama 3 8B (Quantized GGUF) [Downloaded Locally]
* **Speech:** RealtimeSTT (Faster-Whisper), RealtimeTTS (System Engine)
* **Libraries:** `google-cloud-bigquery`, `rich`, `llama-cpp-python`

## Getting Started

### 1. Prerequisites
* A Google Cloud Project with the BigQuery API enabled.
* A Service Account Key (JSON) with `BigQuery Data Viewer` and `BigQuery Job User` roles.
* Python installed on your machine.

### 2. Installation
```bash
# Clone the repository
git clone [https://github.com/yourusername/voice-bigquery-assistant.git](https://github.com/yourusername/voice-bigquery-assistant.git)
cd voice-bigquery-assistant

# Install dependencies
pip install -r requirements.txt
