import argparse
import requests
import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

# Add current directory to path so we can import modules
sys.path.append(str(Path(__file__).parent))

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

import rename
import plan
import rewrite

def chat_qwen(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    json_mode: bool = False,
    call_tag: str = "",
    trace_logger: Optional[Callable[[str], None]] = None,
) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.7, # Higher creativity for rewriting
        "messages": [
            {"role": "system", "content": "你是资深女频短篇小说创作者。"},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        payload["temperature"] = 0.3 # Lower for structure

    if trace_logger:
        trace_logger(f"--- [CALL: {call_tag}] INPUT ---\n{prompt}\n---------------------------")

    try:
        print(f"DEBUG: Sending request for {call_tag}... Payload size: {len(json.dumps(payload))}")
        sys.stdout.flush()
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=600)
        print(f"DEBUG: Response received for {call_tag}, status: {resp.status_code}")
        sys.stdout.flush()
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        
        if trace_logger:
            trace_logger(f"--- [CALL: {call_tag}] OUTPUT ---\n{content}\n---------------------------")
        return content
    except BaseException as e:
        print(f"DEBUG: Exception caught: {type(e).__name__}: {e}")
        sys.stdout.flush()
        if trace_logger:
            trace_logger(f"--- [CALL: {call_tag}] ERROR ---\n{str(e)}\n---------------------------")
        raise

def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    base_dir = Path(__file__).parent
    config_path = base_dir / "config.json"
    
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Use config values
    input_file = config.get("input_file", "")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name = config.get("model", "qwen3.5-plus")

    if not input_file or not api_key:
        print("Error: 'input_file' and 'api_key' are required in config.json")
        return

    # Setup Paths
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    log_file = logs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Setup Logger
    def logger(msg: str):
        print(msg)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    logger(f"Starting Process... Log file: {log_file}")
    logger(f"Config loaded from {config_path}")

    # Bind Chat Function
    def bound_chat(prompt, json_mode=False, call_tag="", trace_logger=None, model=None):
        target_model = model or model_name
        return chat_qwen(base_url, api_key, target_model, prompt, json_mode, call_tag, trace_logger)

    try:
        input_path = Path(input_file)
        if not input_path.exists():
            logger(f"Input file not found: {input_path}")
            return

        # Prepare output directory
        output_dir = Path(r"e:\worksapce\short_stories\data\改进小说")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Step 1: Rename
        renamed_path = base_dir / f"{input_path.stem}_renamed.txt"
        logger("\n=== STEP 1: RENAMING ===")
        renamed_text, new_title = rename.run_rename(input_path, renamed_path, bound_chat, logger)
        logger(f"New Title: {new_title}")

        # Step 2: Plan
        logger("\n=== STEP 2: PLANNING & CHUNKING ===")
        final_plan = plan.run_plan(renamed_text, bound_chat, logger)
        
        # Save plan for debugging
        plan_path = base_dir / "plan.json"
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(final_plan, f, ensure_ascii=False, indent=2)
        logger(f"Plan saved to {plan_path}")

        # Step 3: Rewrite
        safe_title = "".join(c for c in new_title if c not in r'\/:*?"<>|').strip()
        final_path = output_dir / f"《{safe_title}》.txt"
        logger(f"\n=== STEP 3: REWRITING to {final_path} ===")
        rewrite.run_rewrite(final_plan, final_path, bound_chat, logger)

        # Cleanup
        logger("\n=== CLEANUP ===")
        if renamed_path.exists():
            try:
                renamed_path.unlink()
                logger(f"Deleted intermediate file: {renamed_path}")
            except Exception as e:
                logger(f"Failed to delete {renamed_path}: {e}")
            
        logger(f"\nAll Done! Final file at: {final_path}")

    except Exception as e:
        logger(f"\nCRITICAL ERROR: {e}")
        import traceback
        logger(traceback.format_exc())

if __name__ == "__main__":
    main()
