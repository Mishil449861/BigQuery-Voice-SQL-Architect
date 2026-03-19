import json
import re
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from llama_cpp import Llama
from google.api_core.exceptions import BadRequest
from RealtimeSTT import AudioToTextRecorder
from RealtimeTTS import TextToAudioStream, SystemEngine

import bq_client
from prompts import GITHUB_SCHEMA_PROMPT

console = Console()

console.print("[yellow]Loading local Llama 3 model...[/]")
llm = Llama(
    model_path="./Meta-Llama-3-8B-Instruct.Q4_K_M.gguf", 
    n_ctx=2048,
    verbose=False
)

tts_engine = SystemEngine() # Uses native OS voice for 0ms latency
tts_stream = TextToAudioStream(tts_engine)

def clean_json_output(raw_text):
    """Strips markdown hallucinated by the LLM."""
    clean_text = re.sub(r'```json\n|\n```|```', '', raw_text).strip()
    return json.loads(clean_text)

def generate_and_execute_sql(user_text, max_retries=3):
    """The Self-Healing Loop: Generates SQL, tests it, and fixes syntax errors."""
    messages = [
        {"role": "system", "content": GITHUB_SCHEMA_PROMPT},
        {"role": "user", "content": user_text}
    ]
    
    for attempt in range(1, max_retries + 1):
        try:
            # 1. Generate SQL
            output = llm.create_chat_completion(
                messages=messages,
                response_format={"type": "json_object"}
            )
            raw_response = output['choices'][0]['message']['content']
            parsed_data = clean_json_output(raw_response)
            
            sql_query = parsed_data['sql']
            voice_reply = parsed_data['reply']
            
            console.print(Panel(Syntax(sql_query, "sql", theme="monokai", line_numbers=True), title=f"Generated SQL (Attempt {attempt})", border_style="green"))
            
            # Speak the acknowledgement (Async)
            if not tts_stream.is_playing():
                tts_stream.feed(voice_reply)
                tts_stream.play_async()

            # 2. Execute on BigQuery
            results = bq_client.execute_bq_query(sql_query)
            return results, voice_reply
            
        except BadRequest as e:
            # 3. Catch BigQuery Error and Self-Heal
            error_msg = str(e)
            console.print(f"[bold red]BigQuery Error:[/] {error_msg}")
            console.print("[yellow]Initiating self-correction...[/]")
            
            # Feed error back to the LLM
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({
                "role": "user", 
                "content": f"BigQuery threw this error: {error_msg}. Fix the SQL syntax. Ensure you are using UNNEST() for arrays and proper RECORD access."
            })
            
        except Exception as e:
            console.print(f"[bold red]Parsing Error:[/] {e}")
            
    return None, "I failed to generate a valid database query after multiple attempts."

def generate_natural_response(user_query, bq_results):
    """Feeds raw BigQuery JSON back to the LLM for a natural conversational answer."""
    prompt = f"""
    The user asked: "{user_query}"
    The database returned this raw data: {bq_results}
    
    Write a brief, conversational response answering the user's question using this data. 
    Do not mention "the database", "JSON", or read out raw code syntax. Keep it natural and direct.
    """
    
    output = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    return output['choices'][0]['message']['content'].strip()

def process_audio(text):
    """Handles the audio interruption and triggers the agent."""
    console.print(Panel(f"[bold cyan]{text}[/]", title="Transcribed Query", border_style="cyan"))
    
    # Stop user interruption
    if tts_stream.is_playing():
        tts_stream.stop()

    results, _ = generate_and_execute_sql(text)
    
    if results is not None:
        console.print(Panel(f"{results}", title="BigQuery Results", border_style="yellow"))
        
        # 1. Check if results are empty
        if not results:
            final_answer = "I executed the query, but couldn't find any matching data in the repository."
        else:
            # 2. Call the LLM to translate raw data to natural text
            console.print("[yellow]Translating data to natural language...[/]")
            final_answer = generate_natural_response(text, results)
            
        console.print(f"[bold magenta] Agent:[/] {final_answer}")
        
        # 3. FIX: Stop any "acknowledgement" audio currently playing before speaking the final answer
        if tts_stream.is_playing():
            tts_stream.stop()
            
        tts_stream.feed(final_answer)
        tts_stream.play_async()

if __name__ == '__main__':
    console.print("[bold green]System Ready. Start speaking![/]")
    
    # Initialize Voice Activity Detection (VAD)
    recorder = AudioToTextRecorder(
        spinner=False,
        model="tiny.en",
        language="en",
        post_speech_silence_duration=0.5, # Adjust lower for faster response time
    )

    while True:
        user_text = recorder.text()
        if user_text.strip():
            process_audio(user_text)
