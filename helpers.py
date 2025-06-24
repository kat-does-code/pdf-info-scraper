import io
import json
import logging
from pydoc import resolve
from classes import ExtractedArtifact, PossibleArtifactFinding, ScannedPDF, ArtifactType
import pdfplumber 
import easyocr
import re
from PIL import Image
from regexes import re_objects

PATTERNS = { key: re.compile(pattern) for key, pattern in re_objects.items() }

def extract_text_inside_filled_rectangles(pdf: pdfplumber.PDF):
    last_page_number = -1
    try:
        for page in pdf.pages:
            last_page_number = page.page_number
            for rect in page.objects["rect"]:
                captured_text = ""
                # Check if the rectangle is filled
                if not rect.get('fill', None) == True:
                    continue

                # check if the rectangle has a dark color
                non_stroking_color = rect.get('non_stroking_color', [])
                if isinstance(non_stroking_color, float):
                    non_stroking_color = [non_stroking_color]
                if not all(0.0 <= c <= 0.2 for c in non_stroking_color):
                    continue

                # Capture text inside the rectangle
                x0, y0, x1, y1 = rect['x0'], rect['y0'], rect['x1'], rect['y1']
                for char in page.objects["char"]:
                    if (
                        char['x0'] >= x0 and char['x1'] <= x1 and
                        char['y0'] >= y0 and char['y1'] <= y1
                    ):
                        captured_text += char['text']
                    elif captured_text:
                        logging.debug(f"Captured text inside filled rectangle on page {page.page_number}: {captured_text}")
                        yield ExtractedArtifact(page.page_number, captured_text, artifact_type=ArtifactType.FILLED_RECTANGLE)
                        captured_text = ""
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
            for obj in page.objects["char"]:
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

    elif "JPXDecode" in str(filter_):
        # JPEG2000 - supported by Pillow
        return Image.open(io.BytesIO(data))

    else:
        raise NotImplementedError(f"Unsupported filter: {filter_}")

async def extract_images_from_pdf(pdf: pdfplumber.PDF):
    last_page_number = -1
    last_image = None
    try:
        reader = easyocr.Reader(['en', 'nl'], gpu=True)
        logging.info(f"Extracting images from PDF: {pdf.path.as_posix()} with {len(pdf.pages)} pages")
        for page in pdf.pages:
            last_page_number = page.page_number
            for img in page.images:
                buffer = io.BytesIO()
                image = _extract_image_data_from_pdf_image(img)
                last_image = image
                image.save(buffer, format="PNG")
                image_text = reader.readtext(buffer.getvalue(), detail=0)
                yield ExtractedArtifact(
                    page.page_number,
                    image_text if image_text else "",
                    object_ref=image,
                    description=f"Image on page {page.page_number} with size {img['width']}x{img['height']}"
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

async def process_pdf(pdf_path: str) -> ScannedPDF:
    """ Processes a PDF file to extract text and images, yielding PII data found in the text.
    
    Args:
        pdf_path (str): The path to the PDF file.
    Yields:
        PossibleArtifactFinding: An object containing the page number, extracted text, and artifact type.
    """
    scanned_pdf = ScannedPDF(pdf_path)
    findings = []
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            logging.error(f"No pages found in PDF: {pdf_path}")
            raise StopAsyncIteration(f"No pages found in PDF: {pdf_path}")
        
        scanned_pdf.author = pdf.metadata.get('Author', '')
        scanned_pdf.title = pdf.metadata.get('Title', '')
        scanned_pdf.subject = pdf.metadata.get('Subject', '')
        scanned_pdf.keywords = pdf.metadata.get('Keywords', '')

        logging.info(f"Processing PDF: {pdf_path} with {len(pdf.pages)} pages")
        text = extract_text_from_pdf(pdf)
        images = extract_images_from_pdf(pdf)
        white_text = extract_white_text_from_pdf(pdf)
        masked_text = extract_text_inside_filled_rectangles(pdf)

        for artifact in text:
            if artifact.text:
                for data_type, data in extract_pii(artifact.text):
                    logging.debug(f"Extracted {data_type}: {data} from page {artifact.page_number} in text of PDF {pdf_path}")
                    findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, data, data_type))

        for artifact in white_text:
            if artifact.text:
                logging.debug(f"Extracted white text from page {artifact.page_number} in PDF {pdf_path}: {artifact.text}")
                findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, artifact.text, "white_text"))

        for artifact in masked_text:
            if artifact.text:
                logging.debug(f"Extracted text inside filled rectangle from page {artifact.page_number} in PDF {pdf_path}: {artifact.text}")
                findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, artifact.text, "filled_rectangle"))

        async for artifact in images:
            if artifact.text:
                for data_type, data in extract_pii(" ".join(artifact.text)):
                    logging.debug(f"Extracted {data_type}: {data} from page {artifact.page_number} in image of PDF {pdf_path}")
                    findings.append(PossibleArtifactFinding.from_extracted_artifact(artifact, data, data_type))
    
    scanned_pdf.add_findings(findings)
    return scanned_pdf

