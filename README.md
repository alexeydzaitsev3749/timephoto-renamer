# TimePhoto Stamp Renamer & EXIF Synchronizer

A high-performance CLI utility for extracting on-screen timestamps and survey metadata from camera overlays (e.g., GPS Map Camera, TimePhoto) and synchronizing them directly into file names and JPEG EXIF headers.

Designed to bridge multimodal LLM workflows (e.g., Google Gemini image manifests) and local file systems by creating immutable, synchronized filename IDs.

---

## Key Features

- **Two-Phase Architecture (Lazy Loading):**
  - **Phase 1 (Instant):** Fast EXIF inspection via Pillow. If the image already contains standard timestamps (`DateTimeOriginal` tag `36867`) or previous stamp markers, the tool resolves the filename in **< 1 ms** without loading PyTorch or OpenCV.
  - **Phase 2 (Lazy OCR):** Fallback to neural OCR only when metadata is missing.
- **Morphological Text Localization:**
  - Employs adaptive luminance peak detection (HSV color space) and horizontal morphological closing (`MORPH_CLOSE`) to tightly frame on-screen text overlays, bypassing the need to scan multi-megapixel backgrounds.
- **Cyrillic-Safe EXIF Injection (`-m`):**
  - Writes standard digital timestamps to `DateTimeOriginal` (tag `36867`) and `DateTime` (tag `306`).
  - Encodes Russian survey text (addresses, coordinates) into Windows-native UTF-16LE `XPComment` (tag `40092`), preventing encoding corruption (`???`) in Windows File Explorer.
- **Batch Processing:**
  - Evaluates glob patterns (`*.jpg`, `*.jpeg`) in a single pass. EasyOCR weights load into memory exactly once.
- **Unix Pipeline Friendly:**
  - Output filenames are sent exclusively to `stdout`.
  - Debugging traces and warnings are routed to `stderr`.

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/timephoto-renamer.git
   cd timephoto-renamer
