import json
import os
import time
import requests
from playwright.sync_api import sync_playwright
import re

# Configuration
HISTORY_FILE = "history.json"
DATA_DIR = "../data"
OCR_API_URL = "http://localhost:8000/ocr"

# Ensure data directories exist
os.makedirs(os.path.join(DATA_DIR, "小说"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "拆文"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "教程"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "temp"), exist_ok=True)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history), f, ensure_ascii=False, indent=4)

def get_ocr_text(image_url):
    try:
        print(f"OCR Request for: {image_url[:50]}...")
        # Download image
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            print(f"Failed to download image: {image_url}")
            return ""
        
        # Send to OCR API
        files = {"file": ("image.jpg", response.content, "image/jpeg")}
        ocr_response = requests.post(OCR_API_URL, files=files, timeout=30)
        
        if ocr_response.status_code == 200:
            data = ocr_response.json()
            return data.get("full_text", "")
        else:
            print(f"OCR failed: {ocr_response.text}")
            return ""
    except Exception as e:
        print(f"Error during OCR: {e}")
        return ""

def classify_content(title, tags, desc):
    combined = (title + " " + " ".join(tags) + " " + desc).lower()
    
    if "拆文" in combined or "拆解" in combined:
        return "拆文"
    
    if "教程" in combined or "写作" in combined or "公式" in combined or "干货" in combined:
        return "教程"
        
    if "小说" in combined or "言情" in combined or "短篇" in combined or "推文" in combined:
        return "小说"
        
    return "temp"

def parse_likes(likes_text):
    if not likes_text:
        return 0
    likes_text = likes_text.strip()
    if "w" in likes_text:
        return float(likes_text.replace("w", "")) * 10000
    if "万" in likes_text:
        return float(likes_text.replace("万", "")) * 10000
    
    # Remove non-digit characters except .
    clean_text = re.sub(r'[^\d.]', '', likes_text)
    if clean_text:
        return float(clean_text)
    return 0

def run_scraper():
    history = load_history()
    print(f"Loaded {len(history)} items from history.")
    
    with sync_playwright() as p:
        # Use a persistent context if possible to save login, but for now just wait for manual login
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Login
        print("Please log in to Xiaohongshu manually in the browser window.")
        page.goto("https://www.xiaohongshu.com/")
        
        # Check if logged in by looking for user avatar or specific element, or just wait for user
        input(">>> Press ENTER here after you have successfully logged in <<<")
        
        search_urls = [
            "https://www.xiaohongshu.com/search_result?keyword=%E5%A5%B3%E9%A2%91%E7%9F%AD%E7%AF%87%E5%B0%8F%E8%AF%B4&type=51",
            "https://www.xiaohongshu.com/search_result?keyword=%E8%A8%80%E6%83%85%E7%9F%AD%E7%AF%87%E5%B0%8F%E8%AF%B4%E6%8E%A8%E8%8D%90&type=51"
        ]
        
        success_count = 0
        TARGET_COUNT = 10

        for url in search_urls:
            if success_count >= TARGET_COUNT:
                break
            print(f"Navigating to search: {url}")
            page.goto(url)
            page.wait_for_load_state("networkidle")
            
            # Scroll to collect links
            collected_urls = []
            for i in range(5):  # Scroll a few times
                print(f"Scrolling {i+1}/5...")
                page.mouse.wheel(0, 1000)
                time.sleep(2)
                
                # Extract links incrementally
                cards = page.locator(".note-item").all() # Or whatever the card selector is, often .note-item or a.cover
                # Note: XHS structure changes, checking current structure
                # It seems to be .feeds-container .note-item or similar.
                # Let's try to find 'a' tags with href containing /explore/
                links = page.locator("a[href^='/explore/']").all()
                
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        full_url = "https://www.xiaohongshu.com" + href
                        if full_url not in history and full_url not in collected_urls:
                            collected_urls.append(full_url)
            
            print(f"Collected {len(collected_urls)} new links.")
            
            # Process each link
            for i, link_url in enumerate(collected_urls):
                try:
                    print(f"Processing [{i+1}/{len(collected_urls)}]: {link_url}")
                    page.goto(link_url)
                    try:
                        page.wait_for_selector(".note-content", timeout=5000)
                    except:
                        print("Timeout waiting for content, skipping...")
                        continue

                    # Extract Data
                    title_el = page.locator("#detail-title")
                    title = title_el.inner_text() if title_el.count() > 0 else "No Title"
                    
                    desc_el = page.locator("#detail-desc")
                    desc = desc_el.inner_text() if desc_el.count() > 0 else ""
                    
                    tags = page.locator("#detail-desc a").all_inner_texts()
                    
                    # Likes
                    # Class might be .interact-container .like-wrapper .count
                    # Or check for aria-label="点赞"
                    likes_el = page.locator(".interact-container .like-wrapper .count")
                    likes_text = likes_el.inner_text() if likes_el.count() > 0 else "0"
                    likes = parse_likes(likes_text)
                    
                    print(f"Title: {title}, Likes: {likes}")

                    # Determine Type
                    is_video = page.locator("video").count() > 0
                    # For images, XHS uses a swiper or list of images
                    image_elements = page.locator(".swiper-slide .note-slider-img").all() # Specific to XHS slider
                    if not image_elements:
                        # Sometimes it's a single image not in swiper?
                        image_elements = page.locator(".note-content img").all() 
                    
                    is_image = len(image_elements) > 0 and not is_video

                    # Filter
                    if is_video:
                        if likes < 1000:
                            print(f"Skipped Video (Likes {likes} < 1000)")
                            history.add(link_url)
                            continue
                    elif is_image:
                         if likes < 200:
                            print(f"Skipped Image (Likes {likes} < 200)")
                            history.add(link_url)
                            continue
                    else:
                        # Text only? Rare, but treat as text
                        if likes < 50:
                            print(f"Skipped Text (Likes {likes} < 50)")
                            history.add(link_url)
                            continue

                    # Classify
                    category = classify_content(title, tags, desc)
                    target_dir = os.path.join(DATA_DIR, category)
                    
                    # Prepare Content
                    file_content = f"Title: {title}\nURL: {link_url}\nLikes: {likes}\nTags: {tags}\n\nDescription:\n{desc}\n\n"
                    
                    # OCR for images
                    if is_image:
                        print(f"Found {len(image_elements)} images, performing OCR...")
                        ocr_results = []
                        for idx, img in enumerate(image_elements):
                            # Try to get high res image
                            # Usually src or style background
                            src = img.get_attribute("src")
                            if src:
                                # Sometimes src is empty or placeholder, check dataset
                                if "http" in src:
                                    text = get_ocr_text(src)
                                    ocr_results.append(f"--- Image {idx+1} ---\n{text}")
                        
                        file_content += "\nOCR Content:\n" + "\n".join(ocr_results)
                    
                    elif is_video:
                        file_content += "\n[Video Content - Audio transcription skipped]\n"

                    # Save
                    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
                    if not safe_title:
                        safe_title = f"post_{int(time.time())}"
                    
                    # Truncate filename if too long
                    if len(safe_title) > 50:
                        safe_title = safe_title[:50]
                        
                    filename = f"{safe_title}.txt"
                    filepath = os.path.join(target_dir, filename)
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(file_content)
                    
                    print(f"Saved to {filepath}")
                    
                    history.add(link_url)
                    save_history(history)
                    
                    success_count += 1
                    print(f"Progress: {success_count}/{TARGET_COUNT}")
                    
                    if success_count >= TARGET_COUNT:
                        print("Target of 10 items reached!")
                        break

                    time.sleep(2) # Politeness
                    
                except Exception as e:
                    print(f"Error processing link {link_url}: {e}")
                    continue

        browser.close()

if __name__ == "__main__":
    run_scraper()
