import multiprocessing as mp
import time
from pathlib import Path
import requests
import uvicorn


IMAGE_PATH = Path(r"e:\worksapce\short_stories\data\大佬怎么写追妻｜短篇拆文《幼薇》_2_粒子（短篇作者养成）_来自小红书网页版.jpg")
OUT_PATH = Path(r"e:\worksapce\short_stories\data\ocr_result.txt")


def serve():
    import os
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.chdir(str(Path(__file__).resolve().parent))
    uvicorn.run("app:app", host="127.0.0.1", port=8000, log_level="warning")


def wait_ready(timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get("http://127.0.0.1:8000/docs", timeout=2)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError("OCR 服务启动超时")


def main():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"图片不存在: {IMAGE_PATH}")

    proc = mp.Process(target=serve, daemon=True)
    proc.start()
    try:
        wait_ready()
        with IMAGE_PATH.open("rb") as f:
            files = {"file": (IMAGE_PATH.name, f, "image/jpeg")}
            resp = requests.post("http://127.0.0.1:8000/ocr", files=files, timeout=300)
        resp.raise_for_status()
        payload = resp.json()
        text = payload.get("full_text", "")
        OUT_PATH.write_text(text, encoding="utf-8")
        print("OCR识别成功")
        print(f"输出文件: {OUT_PATH}")
        print(text[:1200])
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=10)


if __name__ == "__main__":
    main()
