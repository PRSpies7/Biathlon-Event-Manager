"""Local, review-only OCR for the application's scanned run and lane sheets."""
from functools import lru_cache
from io import BytesIO
from threading import RLock
import re

from services.results_verification import ManualReading

_LOCK = RLock()


@lru_cache(maxsize=1)
def printed_engine():
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise RuntimeError('Local recognition dependencies are missing. Install requirements-ocr.txt to read scanned PDFs.') from exc
    return RapidOCR()


def _png(image):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _remove_rules(image):
    """Remove long form rules for recognition; previews always keep the original."""
    import cv2
    import numpy as np
    from PIL import Image
    gray = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (max(35, gray.shape[1] // 2), 1)))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, int(gray.shape[0] * .8)))))
    gray[(horizontal > 0) | (vertical > 0)] = 255
    return Image.fromarray(gray).convert('RGB')


def recognize_times(images):
    import numpy as np
    output = []
    for image in images:
        cleaned = _remove_rules(image)
        if (np.asarray(cleaned.convert('L')) < 150).mean() <= .006:
            output.append('')
            continue
        with _LOCK:
            result = printed_engine()(np.asarray(cleaned), use_det=False, use_cls=False, use_rec=True)
        output.append(' '.join(result.txts or ()).strip())
    return output


def locate_rows(words, width, height, discipline):
    """Restrict detection to known athlete columns, never match using categories."""
    id_left, id_right = ((.035, .15) if discipline == 'run' else (.11, .235))
    name_left, name_right = ((.15, .425) if discipline == 'run' else (.22, .50))
    time_left, time_right = ((.775, .945) if discipline == 'run' else (.75, .955))
    rows = []
    for word in words:
        identity = word['text'].strip()
        if not re.fullmatch(r'\d{2,8}', identity):
            continue
        cx, cy = word['cx'], word['cy']
        if not (id_left * width < cx < id_right * width and .12 * height < cy < .93 * height):
            continue
        names = [w for w in words if name_left * width < w['cx'] < name_right * width
                 and abs(w['cy'] - cy) < max(word['height'], w['height']) * .7
                 and re.search(r'[A-Za-z]', w['text'])]
        if not names:
            continue
        name = ' '.join(w['text'] for w in sorted(names, key=lambda w: w['cx']))
        # Use the page's printed text angle to follow slightly tilted scan rows.
        slopes = [w['slope'] for w in names if abs(w['slope']) < .1]
        slope = sum(slopes) / len(slopes) if slopes else 0
        time_y = cy + slope * ((time_left + time_right) * width / 2 - cx)
        half_height = max(10, min(height * .012, word['height'] * .8))
        box = (int(time_left * width), max(0, int(time_y - half_height)),
               int(time_right * width), min(height, int(time_y + half_height)))
        preview = (max(0, int(id_left * width)), max(0, int(min(cy, time_y) - half_height)),
                   int(time_right * width), min(height, int(max(cy, time_y) + half_height)))
        rows.append((identity, name, box, preview))
    return sorted(rows, key=lambda row: row[2][1])


def extract_scanned_page(page, discipline, page_number):
    import numpy as np
    image = page.to_image(resolution=160).original.convert('RGB')
    with _LOCK:
        result = printed_engine()(np.asarray(image), use_det=True, use_cls=True, use_rec=True)
    words = []
    if result.boxes is not None:
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            x0, y0 = box.min(axis=0)
            x1, y1 = box.max(axis=0)
            words.append({'text': text, 'cx': float((x0+x1)/2), 'cy': float((y0+y1)/2),
                          'height': float(y1-y0), 'slope': float((box[1][1]-box[0][1])/max(1, box[1][0]-box[0][0]))})
    page_text = ' '.join(w['text'] for w in words).casefold()
    if (discipline == 'run' and 'swimming heats' in page_text) or (discipline == 'swim' and 'running heats' in page_text):
        return [], []
    if not any(marker in page_text for marker in ('athlete', 'timekeeper', 'running heats', 'swimming heats')):
        return [], [f'{discipline.title()} page {page_number}: sheet layout could not be identified. Transcribe this page manually.']
    rows = locate_rows(words, *image.size, discipline)
    if not rows:
        return [], [f'{discipline.title()} page {page_number}: no athlete rows recognized. Transcribe this page manually.']
    texts = recognize_times([image.crop(row[2]) for row in rows])
    readings = [ManualReading(identity, name, discipline, text.strip() or None, False,
                              f'Page {page_number} · local OCR, check original row', _png(image.crop(preview)))
                for (identity, name, box, preview), text in zip(rows, texts)]
    return readings, [f'{discipline.title()} page {page_number}: {len(readings)} proposed readings. Confirm athlete IDs and times against the images; blanks and crossed-out rows must not be accepted as recorded times.']
