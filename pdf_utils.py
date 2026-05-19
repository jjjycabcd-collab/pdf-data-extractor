import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
import difflib

# Windows 환경 등에서 Tesseract 경로를 못 찾을 경우 아래 주석을 풀고 설치 경로를 지정해주세요.
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def get_html_diff(text1, text2):
    if not text1 and not text2: return ""
    matcher = difflib.SequenceMatcher(None, text1, text2)
    result = []
    del_style = "background-color: #ffcccc; color: #cc0000; text-decoration: line-through; cursor: pointer; border-radius: 3px; padding: 0 3px;"
    ins_style = "background-color: #ccffcc; color: #006600; font-weight: bold; cursor: pointer; border-radius: 3px; padding: 0 3px;"
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal': result.append(text1[i1:i2])
        elif tag == 'delete': result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{del_style}'>{text1[i1:i2]}</span>")
        elif tag == 'insert': result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{ins_style}'>{text2[j1:j2]}</span>")
        elif tag == 'replace':
            result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{del_style} margin-right: 2px;'>{text1[i1:i2]}</span>")
            result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{ins_style}'>{text2[j1:j2]}</span>")
    return "".join(result).replace('\n', '<br>')

def extract_text_with_spaces(page, clip_rect):
    words = page.get_text("words", clip=clip_rect)
    if not words: return ""
    words.sort(key=lambda w: (w[5], w[6], w[7]))
    lines = []
    current_line_words = []
    if words:
        prev_block_line = (words[0][5], words[0][6])
        for w in words:
            curr_block_line = (w[5], w[6])
            word_text = w[4]
            if curr_block_line != prev_block_line:
                lines.append(" ".join(current_line_words))
                current_line_words = [word_text]
                prev_block_line = curr_block_line
            else:
                current_line_words.append(word_text)
        if current_line_words: lines.append(" ".join(current_line_words))
    return "\n".join(lines)

def clean_text(text, exclude_keywords_str):
    if not text: return ""
    lines = text.split('\n')
    cleaned_lines = []
    excludes = [k.strip() for k in exclude_keywords_str.split(',') if k.strip()]
    
    for line in lines:
        line = line.strip()
        if line and not any(ex in line for ex in excludes):
            line = re.sub(r'\s+', ' ', line)
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def extract_text_via_ocr(img_path, lang, exclude_keywords_str):
    try:
        img = Image.open(img_path).convert('L')
        img = img.point(lambda x: 0 if x < 150 else 255, '1')
        ocr_text = pytesseract.image_to_string(img, lang=lang, config='--psm 4')
        return clean_text(ocr_text, exclude_keywords_str)
    except Exception as e:
        return f"[OCR 에러: Tesseract가 설치되어 있는지 확인하세요]\n{str(e)}"

def get_page_image(file_bytes, page_idx):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return img, page.rect.width, page.rect.height
    except:
        return None, 0, 0

def parse_page_ranges(range_str, max_pages):
    pages = set()
    parts = range_str.split(',')
    for part in parts:
        part = part.strip()
        if not part: continue
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                pages.update(range(max(1, start), min(max_pages + 1, end + 1)))
            except: pass
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages: pages.add(p)
            except: pass
    return sorted(list(pages))
