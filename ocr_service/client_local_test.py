from pathlib import Path
from fastapi.testclient import TestClient
from app import app


IMAGE_PATH = Path(r"e:\worksapce\short_stories\data\大佬怎么写追妻｜短篇拆文《幼薇》_2_粒子（短篇作者养成）_来自小红书网页版.jpg")
OUT_PATH = Path(r"e:\worksapce\short_stories\data\ocr_result.txt")


def main():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"图片不存在: {IMAGE_PATH}")

    client = TestClient(app)
    with IMAGE_PATH.open("rb") as f:
        resp = client.post("/ocr", files={"file": (IMAGE_PATH.name, f, "image/jpeg")})
    if resp.status_code >= 400:
        print(resp.text)
    resp.raise_for_status()
    payload = resp.json()
    text = payload.get("full_text", "")
    OUT_PATH.write_text(text, encoding="utf-8")
    print("OCR识别成功")
    print(f"输出文件: {OUT_PATH}")
    print(text[:1200])


if __name__ == "__main__":
    main()
