import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from rapidocr_onnxruntime import RapidOCR

app = FastAPI()
ocr = RapidOCR()

@app.post("/ocr")
async def perform_ocr(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        result, _ = ocr(img)

        extracted_text = []
        full_text = ""

        lines = result or []
        for line in lines:
            if len(line) < 3:
                continue
            box, text, confidence = line[0], line[1], line[2]
            extracted_text.append(
                {"text": text, "confidence": float(confidence), "box": box}
            )
            full_text += text + "\n"

        return {
            "status": "success",
            "full_text": full_text,
            "details": extracted_text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
