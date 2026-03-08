import argparse
from pathlib import Path
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        default=r"e:\worksapce\short_stories\data\大佬怎么写追妻｜短篇拆文《幼薇》_2_粒子（短篇作者养成）_来自小红书网页版.jpg",
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000/ocr")
    parser.add_argument("--out", default=r"e:\worksapce\short_stories\data\ocr_result.txt")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    with image_path.open("rb") as f:
        files = {"file": (image_path.name, f, "image/jpeg")}
        response = requests.post(args.url, files=files, timeout=180)

    response.raise_for_status()
    payload = response.json()
    text = payload.get("full_text", "")
    Path(args.out).write_text(text, encoding="utf-8")
    print("OCR识别成功")
    print(f"输出文件: {args.out}")
    print("识别内容预览:")
    print(text[:1000])


if __name__ == "__main__":
    main()
