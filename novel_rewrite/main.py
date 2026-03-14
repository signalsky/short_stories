import argparse
import requests
import json
import os
import shutil
import sys
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Set

# Add current directory to path so we can import modules
sys.path.append(str(Path(__file__).parent))

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

import rename
import plan
import rewrite
import oss_store

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

def get_processed_titles(csv_path: Path) -> Set[str]:
    processed = set()
    if not csv_path.exists():
        return processed
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "Old Title" in row:
                    processed.add(row["Old Title"].strip())
    except Exception as e:
        print(f"Warning: Failed to read history file: {e}")
    return processed

def process_one_novel(input_path: Path, config: dict, bound_chat: Callable, logger: Callable, base_dir: Path):
    if not input_path.exists():
        logger(f"Input file not found: {input_path}")
        return

    # Prepare output directory
    output_dir = Path(r"e:\worksapce\short_stories\data\改进小说")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    renamed_path = base_dir / f"{input_path.stem}_renamed.txt"
    
    try:
        # Step 1: Rename
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

        # Step 4: Upload to OSS
        logger("\n=== STEP 4: UPLOAD TO OSS ===")
        old_title = input_path.stem
        oss_config = config.get("oss")
        if oss_config:
            oss_urls = oss_store.process_upload(str(final_path), str(input_path), old_title, new_title, oss_config, logger)
            if oss_urls and oss_urls[0]:
                logger(f"OSS Upload Complete.\nModified URL: {oss_urls[0]}\nOriginal URL: {oss_urls[1]}")
            else:
                logger("OSS Upload Failed.")
        else:
            logger("OSS config missing in config.json. Skipping upload.")

        logger(f"\nSuccessfully processed: {input_path.name} -> {final_path.name}")

    finally:
        # Cleanup
        logger("\n=== CLEANUP ===")
        
        # List of files to cleanup
        files_to_cleanup = [renamed_path, base_dir / "plan.json"]
        
        for file_path in files_to_cleanup:
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger(f"Deleted intermediate file: {file_path}")
                except Exception as e:
                    logger(f"Failed to delete {file_path}: {e}")

def main():
    base_dir = Path(__file__).parent
    config_path = base_dir / "config.json"
    
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Use config values
    input_folder = config.get("input_folder", "")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name = config.get("model", "qwen3.5-plus")

    if not input_folder or not api_key:
        print("Error: 'input_folder' and 'api_key' are required in config.json")
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

    # Load processed history
    history_csv = Path(r"e:\worksapce\short_stories\data\改进小说\rewrite_history.csv")
    processed_titles = get_processed_titles(history_csv)
    logger(f"Loaded {len(processed_titles)} processed titles from history.")

    input_folder_path = Path(input_folder)
    if not input_folder_path.exists():
        logger(f"Input folder not found: {input_folder_path}")
        return
    
    # Find all txt files
    txt_files = list(input_folder_path.glob("*.txt"))
    logger(f"Found {len(txt_files)} txt files in {input_folder_path}")

    for txt_file in txt_files:
        old_title = txt_file.stem
        
        # Check if processed
        if old_title in processed_titles:
            logger(f"Skipping '{old_title}' (already in history).")
            continue
            
        logger(f"\n\n{'#'*50}")
        logger(f"STARTING PROCESSING: {txt_file.name}")
        logger(f"{'#'*50}\n")
        
        try:
            process_one_novel(txt_file, config, bound_chat, logger, base_dir)
        except Exception as e:
            logger(f"\nCRITICAL ERROR processing {txt_file.name}: {e}")
            import traceback
            logger(traceback.format_exc())
            # Continue to next file despite error

    logger("\nAll files processed.")

if __name__ == "__main__":
    main()
