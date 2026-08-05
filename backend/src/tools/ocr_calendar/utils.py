"""Utility functions for OCR calendar tool."""
import base64
import re
import requests
from typing import List, Tuple
from urllib.parse import urljoin


# ==================== Configuration Constants ====================
API_URL = "https://weqfrfz5w7ocvapf.aistudio-app.com/layout-parsing"
TOKEN = "65cb8ec21d1e1b20fbb8241ed4dc599aaf8c89ed"

SUSTECH_CALENDAR_URL = "https://www.sustech.edu.cn/zh/academic-calendar.html"


# ==================== 1. Image Download Function ====================
def download_calendar_image() -> Tuple[bytes, str]:
    """Download the latest academic calendar image from SUSTech official website.

    Returns:
        Tuple[bytes, str]: A tuple containing (image content in bytes, image filename).

    Raises:
        Exception: If the calendar image URL is not found or download fails.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
    }

    # 1. Fetch calendar page
    resp = requests.get(SUSTECH_CALENDAR_URL, headers=headers, timeout=30)
    resp.encoding = 'utf-8'
    html = resp.text

    # 2. Extract image URL (prioritize calendar area images)
    pattern = r'<div[^>]*class="[^"]*(?:tzgg_ct|xl_wrap)[^"]*"[^>]*>.*?<img[^>]+src="(/uploads/images/[^"]+)"'
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        pattern = r'<img[^>]+src="(/uploads/images/\d{4}/\d{2}/[^"]+\.jpg)"'
        match = re.search(pattern, html)

    if not match:
        raise Exception("Calendar image URL not found")

    img_path = match.group(1)
    img_url = urljoin("https://www.sustech.edu.cn", img_path)

    # 3. Download image
    img_resp = requests.get(img_url, headers=headers, timeout=30)
    img_resp.raise_for_status()

    image_content = img_resp.content
    filename = img_path.split('/')[-1]

    return image_content, filename


# ==================== 2. OCR Recognition Function ====================
def ocr_image(
    file_bytes: bytes,
    file_type: int = 1,
    use_doc_orientation_classify: bool = False,
    use_doc_unwarping: bool = False,
    use_chart_recognition: bool = False,
) -> dict:
    """Perform OCR layout parsing on an image or PDF.

    Args:
        file_bytes: File content in bytes.
        file_type: File type, 0 for PDF, 1 for image. Defaults to 1.
        use_doc_orientation_classify: Whether to use document orientation classification.
        use_doc_unwarping: Whether to use document unwarping.
        use_chart_recognition: Whether to use chart recognition.

    Returns:
        dict: The parsing result returned by the API.

    Raises:
        Exception: If the API request fails.
    """
    file_data = base64.b64encode(file_bytes).decode("ascii")

    headers = {
        "Authorization": f"token {TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "file": file_data,
        "fileType": file_type,
        "useDocOrientationClassify": use_doc_orientation_classify,
        "useDocUnwarping": use_doc_unwarping,
        "useChartRecognition": use_chart_recognition,
    }

    response = requests.post(API_URL, json=payload, headers=headers, timeout=120)

    if response.status_code != 200:
        raise Exception(f"API request failed with status code: {response.status_code}")

    return response.json()["result"]


def extract_markdown_text(result: dict, doc_index: int = 0) -> str:
    """Extract Markdown text from OCR result.

    Args:
        result: The OCR result dictionary.
        doc_index: Document index to extract from. Defaults to 0.

    Returns:
        str: The extracted Markdown text.
    """
    return result["layoutParsingResults"][doc_index]["markdown"]["text"]


# ==================== 3. Table Extraction Function ====================
def extract_holiday_tables(markdown_content: str) -> List[str]:
    """Extract tables containing specific headers from markdown content.

    Matches tables where the header row contains any of the following:
    "国家节假日" (National Holidays), "重大活动" (Major Events),
    "教学安排(本科)" (Undergraduate Teaching Schedule),
    "教学安排(研究生)" (Graduate Teaching Schedule).

    Args:
        markdown_content: The markdown content to search in.

    Returns:
        List[str]: A list of HTML table strings matching the criteria.
    """
    pattern = r'(<table[^>]*>\s*<tr>(?:(?!</tr>).)*(?:国家节假日|重大活动|教学安排\(本科\)|教学安排\(研究生\)).*?</tr>.*?</table>)'
    tables = re.findall(pattern, markdown_content, re.DOTALL)
    return tables



