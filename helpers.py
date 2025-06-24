import io
import logging
from pydoc import resolve
from classes import ExtractedArtifact, PossibleArtifactFinding, ScannedPDF
import pdfplumber 
import easyocr
import re
from PIL import Image
from regexes import re_objects

PATTERNS = { key: re.compile(pattern) for key, pattern in re_objects.items() }

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
        return Image.frombytes(mode, (width, height), data)

    elif "JPXDecode" in str(filter_):
        # JPEG2000 - supported by Pillow
        return Image.open(io.BytesIO(data))

    else:
        raise NotImplementedError(f"Unsupported filter: {filter_}")

async def extract_images_from_pdf(pdf: pdfplumber.PDF):
    try:
        reader = easyocr.Reader(['en', 'nl'], gpu=True)
        logging.info(f"Extracting images from PDF: {pdf.path.as_posix()} with {len(pdf.pages)} pages")
        for page in pdf.pages:
            for img in page.images:
                buffer = io.BytesIO()
                image = _extract_image_data_from_pdf_image(img)
                image.save(buffer, format="PNG")
                image_text = reader.readtext(buffer.getvalue(), detail=0)
                yield ExtractedArtifact(
                    page.page_number,
                    image_text if image_text else "",
                    object_ref=image,
                    description=f"Image on page {page.page_number} with size {img['width']}x{img['height']}"
                )
    except Exception as e:
        logging.error(f"Error extracting images from PDF: {e}", exc_info=True)
        raise RuntimeError(f"Failed to extract images from PDF: {pdf.path.as_posix()}") from e
    

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
    
    scanned_pdf.add_findings(findings)
    return scanned_pdf

