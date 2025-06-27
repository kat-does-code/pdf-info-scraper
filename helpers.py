from datetime import datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
from pydoc import resolve
from classes import ExtractedArtifact, PossibleArtifactFinding, ScannedPDF, ArtifactType
import pdfplumber 
import easyocr
import re
from PIL import Image
from regexes import re_objects
import fitz

PATTERNS = { key: re.compile(pattern) for key, pattern in re_objects.items() }


def parse_pdf_date(pdf_date: str) -> datetime:
    if not pdf_date:
        return None

    # Remove the leading "D:" if present
    if pdf_date.startswith("D:"):
        pdf_date = pdf_date[2:]

    # Regex pattern to extract the components
    pattern = (
        r"(?P<year>\d{4})"
        r"(?P<month>\d{2})?"
        r"(?P<day>\d{2})?"
        r"(?P<hour>\d{2})?"
        r"(?P<minute>\d{2})?"
        r"(?P<second>\d{2})?"
        r"(?P<tz_sign>[+-Z])?"
        r"(?P<tz_hour>\d{2})?'?(?P<tz_minute>\d{2})?'?"
    )

    match = re.match(pattern, pdf_date)
    if not match:
        raise ValueError(f"Invalid PDF date format: {pdf_date}")

    parts = match.groupdict(default='00')  # Default all missing parts to '00'
    
    # Build the datetime object
    dt = datetime(
        int(parts['year']),
        int(parts['month']),
        int(parts['day']),
        int(parts['hour']),
        int(parts['minute']),
        int(parts['second']),
    )

    # Handle timezone
    if parts['tz_sign'] == 'Z' or parts['tz_sign'] is None:
        tz = timezone.utc
    else:
        offset_hours = int(parts['tz_hour'])
        offset_minutes = int(parts['tz_minute'])
        delta = timedelta(hours=offset_hours, minutes=offset_minutes)
        if parts['tz_sign'] == '-':
            delta = -delta
        tz = timezone(delta)

    return dt.replace(tzinfo=tz)

def extract_text_inside_filled_rectangles(pdf: pdfplumber.PDF, out:Path):
    last_page_number = -1
    last_y_offset = -1
    has_dark_rects = False
    try:
        for page in pdf.pages:
            last_page_number = page.page_number
            captured_text = ""
            for rect in page.objects.get("rect", []):
                # Capture rectangle boundaries
                x0, y0, x1, y1 = round(rect['x0']), round(rect['y0']), round(rect['x1']), round(rect['y1'])
                if last_y_offset != y0:
                    if captured_text:
                        logging.debug(f"Captured text inside filled rectangle on page {page.page_number} at offset{last_y_offset}: {captured_text}")
                        yield ExtractedArtifact(page.page_number, captured_text, artifact_type=ArtifactType.FILLED_RECTANGLE)
                        captured_text = ""
                    # indent
                    last_y_offset = y0


                # Check if the rectangle is filled
                if not rect.get('fill', None) == True:
                    continue
                else:
                    has_dark_rects = True

                # check if the rectangle has a dark color
                non_stroking_color = rect.get('non_stroking_color', [])
                if isinstance(non_stroking_color, float) or isinstance(non_stroking_color, int):
                    non_stroking_color = [non_stroking_color]
                if not all(0.0 <= c <= 0.2 for c in non_stroking_color):
                    continue

                for i, char in enumerate(page.objects.get("char", [])):
                    if (
                        round(char['x0']) >= x0 and round(char['x1']) <= x1 and
                        round(char['y0']) >= y0 and round(char['y1']) <= y1
                    ):
                        captured_text += char['text']
            
            # flush last bit of captured text
            if captured_text:
                logging.debug(f"Captured text inside filled rectangle on page {page.page_number} at offset{last_y_offset}: {captured_text}")
                yield ExtractedArtifact(page.page_number, captured_text, artifact_type=ArtifactType.FILLED_RECTANGLE)
    except Exception as e:
        errmsg = f"Error extracting text inside filled rectangles on page {last_page_number} from PDF: {pdf.path.as_posix()}"
        logging.error(errmsg, exc_info=True)
        raise RuntimeError(errmsg) from e

def extract_white_text_from_pdf(pdf: pdfplumber.PDF):
    last_page_number = -1
    captured_white_text = ""
    try:
        for page in pdf.pages:
            last_page_number = page.page_number
            for obj in page.objects.get("char", []):
                if (
                    obj['object_type'] == 'char' and
                    all(0.8 <= c <= 1.0 for c in obj.get('non_stroking_color', []))
                ):
                    captured_white_text += obj['text']
                elif captured_white_text:
                    logging.debug(f"Captured white text on page {page.page_number}: {captured_white_text}")
                    yield ExtractedArtifact(page.page_number, captured_white_text, artifact_type=ArtifactType.WHITE_TEXT)
                    captured_white_text = ""
    except Exception as e:
        errmsg = f"Error extracting white text on page {last_page_number} from PDF: {pdf.path.as_posix()}"
        logging.error(errmsg, exc_info=True)
        raise RuntimeError(errmsg) from e

def extract_text_from_pdf(pdf: pdfplumber.PDF):
    try:
        for page in pdf.pages:
            logging.debug(f"Extracting text from page {page.page_number}")
            page_text = page.extract_text(x_tolerance=1, y_tolerance=1)  + '\n'
            logging.debug(f"Extracted text with length {len(page_text)} from page {page.page_number}")
            yield ExtractedArtifact(page.page_number, page_text)
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}", exc_info=True)
        raise RuntimeError(f"Failed to extract text from PDF: {pdf}") from e

def _extract_image_data_from_pdf_image(image: dict) -> Image.Image:
    attrs = image['stream'].attrs
    data = image['stream'].get_data()

    width = attrs.get("Width")
    height = attrs.get("Height")
    color_space = attrs.get("ColorSpace")
    bits_per_component = attrs.get("BitsPerComponent")
    filter_ = attrs.get("Filter")

    # Step 2: Handle common filters
    if 'DCTDecode' in str(filter_):
        # JPEG format
        return Image.open(io.BytesIO(data))

    elif  "FlateDecode" in str(filter_):
        # Assume RGB or grayscale (add more checks if needed)
        mode = "L" if "DeviceGray" in resolve(color_space) else "RGB"
        expected_len = width * height if mode == "L" else width * height * 3
        if len(data) < expected_len:
            # Pad with zeros if data is too short
            data += b'\x00' * (expected_len - len(data))
        elif len(data) > expected_len:
            # Truncate if data is too long
            data = data[:expected_len]
        return Image.frombytes(mode, (width, height), data)

    else: 
        # JPEG2000 - supported by Pillow
        return Image.open(io.BytesIO(data), formats=None) # Try loading all formats


def _extract_images_from_page(page):
    for img in page.images:
        buffer = io.BytesIO()
        image = _extract_image_data_from_pdf_image(img)
        image.save(buffer, format="PNG")
        yield buffer

async def extract_images_from_pdf(pdf: pdfplumber.PDF):
    last_page_number = -1
    last_image = None
    n = len(pdf.pages)
    try:
        reader = easyocr.Reader(['en', 'nl'], gpu=True)
        logging.info(f"Extracting images from PDF: {pdf.path.as_posix()} with {len(pdf.pages)} pages")
        for i, page in enumerate(pdf.pages):
            last_page_number = page.page_number
            for img_buffer in _extract_images_from_page(page):
                last_image = img_buffer
                image_text = reader.readtext(img_buffer.getvalue(), detail=0)
                yield ExtractedArtifact(
                    page.page_number,
                    image_text if image_text else "",
                    object_ref=img_buffer,
                    description=f"Image on page {page.page_number}"
                )
    except Exception as e:
        if last_image:
            last_image.save(f"image_error_{pdf.path.stem}.png", format="PNG")

        errmsg = f"Error extracting images from PDF: {pdf.path.as_posix()} at page {last_page_number}"
        logging.error(errmsg, exc_info=True)
        raise RuntimeError(errmsg) from e


def extract_pii(text: str):
    for key, value in PATTERNS.items():
        pii_match = re.findall(value, text)
        for match in pii_match:
            if match:
                yield (key, match)

def check_for_signatures(pdf: pdfplumber.PDF) -> bool:
    last_page = pdf.pages[-1]
    return any(last_page.images)

async def process_pdf(pdf_path:Path, do_regex:bool, output_path: Path) -> ScannedPDF:
    """ Processes a PDF file to extract text and images, yielding PII data found in the text.
    
    Args:
        pdf_path (str): The path to the PDF file.
    Yields:
        PossibleArtifactFinding: An object containing the page number, extracted text, and artifact type.
    """
    scanned_pdf = ScannedPDF(pdf_path.as_posix())
    findings: list[PossibleArtifactFinding] = []
    with pdfplumber.open(scanned_pdf.path) as pdf:
        if not pdf.pages:
            logging.error(f"No pages found in PDF: {pdf_path}")
            raise StopAsyncIteration(f"No pages found in PDF: {pdf_path}")
        
        scanned_pdf.author = pdf.metadata.get('Author', '')
        scanned_pdf.title = pdf.metadata.get('Title', '')
        scanned_pdf.subject = pdf.metadata.get('Subject', '')
        scanned_pdf.keywords = pdf.metadata.get('Keywords', '')
        scanned_pdf.producer = pdf.metadata.get('Producer', '')
        scanned_pdf.creator = pdf.metadata.get('Creator', '')

        creation_date_pdfstr = pdf.metadata.get('CreationDate', '')
        modification_date_pdfstr = pdf.metadata.get('ModDate', '')
        try:
            scanned_pdf.creation_date = parse_pdf_date(creation_date_pdfstr)
            scanned_pdf.modification_date = parse_pdf_date(modification_date_pdfstr)
        except Exception as e:
            pass

        logging.info(f"Processing PDF: {pdf_path} with {len(pdf.pages)} pages")
        # white_text = extract_white_text_from_pdf(pdf)
        masked_text = extract_text_inside_filled_rectangles(pdf, output_path)
        scanned_pdf.potential_signatures = check_for_signatures(pdf)

        # for artifact in white_text:
        #     if artifact.text:
        #         logging.debug(f"Extracted white text from page {artifact.page_number} in PDF {pdf_path}: {artifact.text}")
        #         findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, artifact.text, "white_text"))

        for artifact in masked_text:
            if artifact.text:
                logging.debug(f"Extracted text inside filled rectangle from page {artifact.page_number} in PDF {pdf_path}: {artifact.text}")
                findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, artifact.text, "filled_rectangle"))

                                
        if do_regex:
            text = extract_text_from_pdf(pdf)
            images = extract_images_from_pdf(pdf)

            for artifact in text:
                if artifact.text:
                    for data_type, data in extract_pii(artifact.text):
                        logging.debug(f"Extracted {data_type}: {data} from page {artifact.page_number} in text of PDF {pdf_path}")
                        findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, data, data_type))

            async for artifact in images:
                if artifact.text:
                    for data_type, data in extract_pii(" ".join(artifact.text)):
                        logging.debug(f"Extracted {data_type}: {data} from page {artifact.page_number} in image of PDF {pdf_path}")
                        findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, data, data_type))
        # endof do_regex

    scanned_pdf.add_findings(findings)
    output_file = output_path / (pdf_path.stem + ".json")
    with open(output_file, 'w') as f:
        json.dump(scanned_pdf.to_dict(), f)

    return scanned_pdf

