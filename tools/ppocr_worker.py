"""A PP-OCRv6 reader that stays up: loads the models once, then reads one PNG per input line.

Runs in its own Python environment, the one with paddleocr and onnxruntime (no Paddle framework needed),
started by tools/ocr_crops.py --engine=ppocrv6. One thread, so a run gives the same lines every time.

  stdin:  one JSON object per line, {"png": "<path>"}
  stdout: one JSON object per line, {"lines": [[x0, y0, x1, y1, "text", score], ...]}, boxes in the PNG's
          pixels, score from 0 to 1; or {"error": "..."}

usage: <ppocr python> tools/ppocr_worker.py <tier> <detector long side>
"""
import json
import os
import sys

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
# one CPU thread in every library: left to themselves, OpenMP, OpenCV and ONNX Runtime each start a pool,
# and four readers in parallel then ran 3.3 times slower than with one thread each
os.environ["OMP_NUM_THREADS"] = "1"
THREADS = {"intra_op_num_threads": 1, "inter_op_num_threads": 1}


def main():
    tier, side = sys.argv[1], int(sys.argv[2])
    import cv2
    cv2.setNumThreads(1)
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(text_detection_model_name=f"PP-OCRv6_{tier}_det", text_recognition_model_name=f"PP-OCRv6_{tier}_rec",
                    engine="onnxruntime", engine_config=THREADS, use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False, text_det_limit_side_len=side,
                    text_det_limit_type="max")
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            r = ocr.predict(json.loads(line)["png"])[0]
            out = []
            for poly, text, score in zip(r["rec_polys"], r["rec_texts"], r["rec_scores"]):
                xs, ys = [float(p[0]) for p in poly], [float(p[1]) for p in poly]
                out.append([min(xs), min(ys), max(xs), max(ys), text, float(score)])
            print(json.dumps({"lines": out}, ensure_ascii=False), flush=True)
        except Exception as e:  # one bad crop is reported, not fatal to the worker
            print(json.dumps({"error": f"{type(e).__name__}: {e}"[:300]}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
