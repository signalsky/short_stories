# -*- coding: utf-8 -*-
import os
import oss2
import csv
import random
import string
from datetime import datetime
from pathlib import Path

# Configuration
# Loaded from config.json passed via arguments
CSV_FILE = r"e:\worksapce\short_stories\data\改进小说\rewrite_history.csv"

def get_next_id():
    """
    Reads the CSV file to determine the next available ID.
    If the file doesn't exist or is empty, returns 1.
    """
    if not Path(CSV_FILE).exists():
        return 1
    
    try:
        with Path(CSV_FILE).open(mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            # Skip header
            try:
                next(reader)
            except StopIteration:
                return 1
            
            # Find the max ID
            max_id = 0
            for row in reader:
                if row and row[0].isdigit():
                    max_id = max(max_id, int(row[0]))
            return max_id + 1
    except Exception as e:
        print(f"Error reading CSV to determine ID: {e}")
        return 1

def generate_random_suffix(length=6):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def upload_to_oss(file_path, object_name, oss_config, logger=None):
    """
    Uploads a file to Aliyun OSS and returns the public URL.
    
    Args:
        file_path (str): The absolute path to the file to upload.
        object_name (str): The object key in OSS (e.g., "1a", "1b").
        oss_config (dict): Dictionary containing oss configuration.
        logger (callable): Optional logger function.
        
    Returns:
        str: The public URL of the uploaded file.
    """
    log = logger if logger else print
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Initialize OSS Auth and Bucket
    auth = oss2.Auth(oss_config['access_key_id'], oss_config['access_key_secret'])
    bucket = oss2.Bucket(auth, oss_config['endpoint'], oss_config['bucket_name'])

    # Use the provided object_name directly (no directory prefix)
    log(f"Uploading {file_path} to oss://{oss_config['bucket_name']}/{object_name}...")

    # Upload the file
    try:
        # Set Content-Type to text/plain and UTF-8 charset
        headers = {'Content-Type': 'text/plain; charset=utf-8'}
        bucket.put_object_from_file(object_name, file_path, headers=headers)
    except oss2.exceptions.OssError as e:
        log(f"Failed to upload to OSS: {e}")
        raise

    # Construct public URL
    bucket_name = oss_config['bucket_name']
    endpoint = oss_config['endpoint']
    
    # Strip protocol from endpoint if present to ensure clean domain
    if endpoint.startswith('http://'):
        endpoint = endpoint[7:]
    elif endpoint.startswith('https://'):
        endpoint = endpoint[8:]
        
    url = f"https://{bucket_name}.{endpoint}/{object_name}"

    log(f"Upload successful. Public URL: {url}")
    return url

def save_to_csv(file_id, old_title, new_title, url_a, url_b, logger=None):
    """
    Appends the record to a local CSV file.
    
    Args:
        file_id (int): The ID of the record.
        old_title (str): The original title.
        new_title (str): The new title.
        url_a (str): The OSS signed URL for the modified file (1a).
        url_b (str): The OSS signed URL for the original file (1b).
        logger (callable): Optional logger function.
    """
    log = logger if logger else print
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    
    file_exists = os.path.exists(CSV_FILE)
    
    try:
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            # Write header if file is new
            if not file_exists:
                writer.writerow(['ID', 'Old Title', 'New Title', 'Modified Link', 'Original Link', 'Generation Time'])
            
            writer.writerow([
                file_id, 
                old_title, 
                new_title, 
                url_a, 
                url_b,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        log(f"Record saved to {CSV_FILE}")
    except Exception as e:
        log(f"Failed to save to CSV: {e}")

def process_upload(modified_file_path, original_file_path, old_title, new_title, oss_config, logger=None):
    """
    Main entry point to upload files and save record.
    """
    try:
        file_id = get_next_id()
        
        # Generate random suffix for each file
        suffix_a = generate_random_suffix()
        suffix_b = generate_random_suffix()
        
        # Upload modified file as {id}a{suffix}.txt
        url_a = upload_to_oss(modified_file_path, f"{file_id}a{suffix_a}.txt", oss_config, logger)
        
        # Upload original file as {id}b{suffix}.txt
        url_b = upload_to_oss(original_file_path, f"{file_id}b{suffix_b}.txt", oss_config, logger)
        
        save_to_csv(file_id, old_title, new_title, url_a, url_b, logger)
        return url_a, url_b
    except Exception as e:
        if logger:
            logger(f"Error in process_upload: {e}")
        else:
            print(f"Error in process_upload: {e}")
        return None, None
