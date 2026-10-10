import os
import sys
import re
import glob
import argparse
import warnings
from datetime import datetime, timedelta
from PIL import Image, ExifTags

warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"

MONTHS = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4,
    'май': 5, 'июн': 6, 'июл': 7, 'авг': 8,
    'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
}

def log_debug(msg, enabled=False):
    if enabled:
        sys.stderr.write(f"[DEBUG-META] {msg}\n")
        sys.stderr.flush()

def log_warn(msg):
    sys.stderr.write(f"[WARN] {msg}\n")
    sys.stderr.flush()

def parse_datetime_from_string(text, plus_second=False):
    """Парсит дату/время из маркера, стандартного EXIF или текста штампа."""
    if not text:
        return None

    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
    clean = str(text).replace('\n', ' ').replace('\r', ' ').strip('\x00').strip()

    # 1. Надежный ASCII-маркер TIMEPHOTO_YYYYMMDD_HHMMSS
    marker_m = re.search(r'TIMEPHOTO_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', clean)
    if marker_m:
        y, m, d, hh, mm, ss = map(int, marker_m.groups())
        dt = datetime(y, m, d, hh, mm, ss)
        return (dt + timedelta(seconds=1) if plus_second else dt).strftime("%Y%m%d_%H%M%S")

    # 2. Стандартный цифровой EXIF (2026:10:09 15:32:46)
    exif_m = re.search(r'(\d{4})[:\-](\d{2})[:\-](\d{2})\s+(\d{2})[:.](\d{2})[:.](\d{2})', clean)
    if exif_m:
        y, m, d, hh, mm, ss = map(int, exif_m.groups())
        dt = datetime(y, m, d, hh, mm, ss)
        return (dt + timedelta(seconds=1) if plus_second else dt).strftime("%Y%m%d_%H%M%S")

    # 3. Русский текст OCR ("9 окт 2026 г 15.32.46")
    date_m = re.search(r'(\d{1,2})\s*([а-яёА-ЯЁ]{3})[^\d]*?(20\d{2})', clean)
    time_m = re.search(r'\b(\d{2})[.:,\s](\d{2})[.:,\s](\d{2})\b', clean)
    if date_m and time_m:
        day, month_raw, year = date_m.groups()
        hh, mm, ss = time_m.groups()
        m_num = MONTHS.get(month_raw.lower()[:3])
        if m_num:
            dt = datetime(int(year), m_num, int(day), int(hh), int(mm), int(ss))
            return (dt + timedelta(seconds=1) if plus_second else dt).strftime("%Y%m%d_%H%M%S")

    return None

def extract_all_exif_tags(im, debug=False):
    """Считывает корень, Exif SubIFD и Windows теги."""
    tags = {}
    if hasattr(im, "_getexif") and im._getexif():
        tags.update(im._getexif())

    try:
        exif = im.getexif()
        if exif:
            tags.update(dict(exif))
            for ifd_id in (0x8769, 0x8825, 0xA005):
                sub = exif.get_ifd(ifd_id)
                if sub:
                    tags.update(sub)
    except Exception:
        pass

    # Декодируем Windows XPComment (40092), если он в UTF-16LE
    if 40092 in tags and isinstance(tags[40092], bytes):
        try:
            tags[40092] = tags[40092].decode('utf-16le', errors='ignore').strip('\x00')
        except Exception:
            pass

    return tags

def try_extract_from_metadata(file_path, plus_second=False, debug=False):
    """Быстрая проверка метаданных без запуска OCR."""
    try:
        with Image.open(file_path) as im:
            is_jpeg = (im.format == 'JPEG')
            tags = extract_all_exif_tags(im, debug)
            if not tags:
                return is_jpeg, None

            # Приоритет тегов: 36867 (DateTimeOriginal), 40092 (XPComment), 270 (ImageDescription), 306 (DateTime)
            for tag_id in [36867, 40092, 270, 306, 36868]:
                if tag_id in tags:
                    val = tags[tag_id]
                    stamp = parse_datetime_from_string(val, plus_second)
                    if stamp:
                        log_debug(f"Найдено в теге {tag_id} -> {stamp}", debug)
                        return is_jpeg, stamp

            return is_jpeg, None
    except Exception as e:
        log_debug(f"Ошибка чтения {file_path}: {e}", debug)
        return False, None

def write_exif_data(image_path, stamp_id, text_data, debug=False):
    """
    Записывает:
    - 36867 (DateTimeOriginal): цифровой стандарт EXIF
    - 40092 (XPComment): чистый русский текст в UTF-16LE для проводника Windows
    - 270 (ImageDescription): маркер TIMEPHOTO_...
    """
    base, ext = os.path.splitext(image_path)
    tmp_path = f"{base}_temp{ext}"
    dt_str = f"{stamp_id[:4]}:{stamp_id[4:6]}:{stamp_id[6:8]} {stamp_id[9:11]}:{stamp_id[11:13]}:{stamp_id[13:15]}"

    try:
        with Image.open(image_path) as im:
            file_format = im.format or "JPEG"
            exif = im.getexif()

            exif[306] = dt_str
            exif.get_ifd(0x8769)[36867] = dt_str
            exif.get_ifd(0x8769)[36868] = dt_str
            exif[270] = f"TIMEPHOTO_{stamp_id}"
            exif[40092] = text_data.encode('utf-16le')

            try:
                im.save(tmp_path, format=file_format, exif=exif, quality="keep")
            except Exception:
                im.save(tmp_path, format=file_format, exif=exif, quality=95)

        os.replace(tmp_path, image_path)
        log_debug(f"Метаданные внедрены в {image_path}", debug)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        log_debug(f"Ошибка записи EXIF: {e}", debug)

def apply_rename(original_path, stamp_id):
    _, ext = os.path.splitext(original_path)
    new_filename = f"TimePhoto_{stamp_id}{ext}"
    dir_name = os.path.dirname(original_path)
    target_path = os.path.join(dir_name, new_filename) if dir_name else new_filename

    if os.path.abspath(original_path) != os.path.abspath(target_path):
        os.replace(original_path, target_path)

    return new_filename

def main():
    parser = argparse.ArgumentParser(description="TimePhoto OCR & Metadata Tool")
    parser.add_argument("inputs", nargs="+", help="Файлы (*.jpg)")
    parser.add_argument("-n", "--rename", action="store_true", help="Переименовать файлы на диске")
    parser.add_argument("-c", "--ceil", action="store_true", help="Округлить вверх (+1 секунда)")
    parser.add_argument("-m", "--meta", action="store_true", help="Записать OCR текст в EXIF")
    parser.add_argument("-d", "--debug", action="store_true", help="Логи в stderr")

    args = parser.parse_args()

    all_files = []
    for item in args.inputs:
        matched = glob.glob(item)
        if matched:
            all_files.extend(matched)
        elif os.path.exists(item):
            all_files.append(item)

    if not all_files:
        sys.stderr.write("Файлы не найдены.\n")
        sys.exit(1)

    needs_ocr = []

    # ФАЗА 1: Быстрая проверка метаданных
    log_debug(f"Сканирование метаданных ({len(all_files)} шт.)...", args.debug)
    for f in all_files:
        is_jpeg, stamp_id = try_extract_from_metadata(f, plus_second=args.ceil, debug=args.debug)
        if stamp_id:
            new_name = apply_rename(f, stamp_id) if args.rename else f"TimePhoto_{stamp_id}{os.path.splitext(f)[1]}"
            sys.stdout.write(f"{new_name}\n")
            sys.stdout.flush()
        else:
            if not is_jpeg:
                log_warn(f"Файл '{f}' не является JPEG и не содержит метаданных.")
            needs_ocr.append(f)

    if not needs_ocr:
        log_debug("Все файлы разрешены через EXIF. OCR не требуется.", args.debug)
        return

    # ФАЗА 2: Ленивый запуск OCR только при необходимости
    log_debug(f"Запуск OCR для {len(needs_ocr)} файлов...", args.debug)
    from stamp_detector import init_ocr, extract_text_from_stamp
    reader = init_ocr()

    for f in needs_ocr:
        patch = extract_text_from_stamp(f)
        if patch is None:
            log_warn(f"Штамп не найден на '{f}'")
            continue

        ocr_results = reader.readtext(patch, detail=0)
        full_text = "\n".join(ocr_results)

        stamp_id = parse_datetime_from_string(full_text, plus_second=args.ceil)
        if not stamp_id:
            log_warn(f"Не удалось спарсить дату из OCR на '{f}': {full_text}")
            continue

        if args.meta:
            write_exif_data(f, stamp_id, full_text, args.debug)

        new_name = apply_rename(f, stamp_id) if args.rename else f"TimePhoto_{stamp_id}{os.path.splitext(f)[1]}"
        sys.stdout.write(f"{new_name}\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()