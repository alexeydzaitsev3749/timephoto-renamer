import cv2
import numpy as np

def init_ocr():
    """Инициализация EasyOCR (вызывается лениво только при необходимости)."""
    import easyocr
    return easyocr.Reader(['ru', 'en'], gpu=False, verbose=False)

def extract_text_from_stamp(file_path):
    """
    Находит штамп через адаптивную гистограмму и морфологию,
    распознает текст и возвращает его в виде строки с переносами строк.
    """
    img = cv2.imread(file_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    # Правый нижний сектор (25% высоты, 65% ширины)
    roi = img[int(h * 0.75):h, int(w * 0.35):w]

    # Анализ яркости белого текста
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    v_channel = hsv_roi[:, :, 2]
    hist = cv2.calcHist([v_channel], [0], None, [256], [0, 256]).ravel()
    thresh_val = max(170, 190 + int(np.argmax(hist[190:])) - 25)
    _, mask = cv2.threshold(v_channel, thresh_val, 255, cv2.THRESH_BINARY)

    # Горизонтальное морфологическое замыкание
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    morphed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_x, min_y = roi.shape[1], roi.shape[0]
    max_x, max_y = 0, 0
    found = False

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw > 35 and 10 < bh < 120:
            found = True
            min_x, min_y = min(min_x, x), min(min_y, y)
            max_x, max_y = max(max_x, x + bw), max(max_y, y + bh)

    if not found:
        return None

    pad = 10
    text_patch = roi[max(0, min_y - pad):min(roi.shape[0], max_y + pad),
                     max(0, min_x - pad):min(roi.shape[1], max_x + pad)]

    return text_patch