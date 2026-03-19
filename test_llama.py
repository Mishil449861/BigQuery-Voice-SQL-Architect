from llama_cpp import Llama
from rich.console import Console

console = Console()

console.print("[yellow]Loading Llama 3 into memory (This might take 5-10 seconds)...[/]")

try:
    # Point this to the exact name of the file you downloaded
    llm = Llama(
        model_path="./Meta-Llama-3-8B-Instruct.Q4_K_M.gguf", 
        n_ctx=2048,
        verbose=False # This keeps the terminal clean
    )
    
    console.print("[cyan]Model loaded! Asking Llama 3 a test question...[/]")
    
    output = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Keep your answer to exactly one sentence."},
            {"role": "user", "content": "What is the capital of Massachusetts?"}
        ]
    )
    
    response = output['choices'][0]['message']['content']
    console.print(f"[bold green]Llama 3 says:[/] {response}")
    console.print("[bold green]\nSuccess! Local AI is fully operational.[/]")
    
except Exception as e:
    console.print(f"[bold red]Uh oh, AI failed to load:[/] {e}")