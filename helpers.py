import enum
import io
import logging
from pydoc import resolve
import queue
from typing import AsyncGenerator, Generator, Optional
import pdfplumber 
import easyocr
import re
from PIL import Image
from regexes import re_objects
import asyncio

PATTERNS = { key: re.compile(pattern) for key, pattern in re_objects.items() }

class ArtifactType(enum.Enum):
    TEXT = "text"
    IMAGE = "image"

class ExtractedArtifact:
    def __init__(self, page_number, text, object_ref=None, description=""):
        self.page_number : int = page_number
        self.text : str = text
        self.object_ref : Optional[any] = object_ref
        self.description : Optional[str] = description

        match self.object_ref:
            case None:
                self.artifact_type = ArtifactType.TEXT
            case _:
                self.artifact_type = ArtifactType.IMAGE

    def __repr__(self):
        return f"ExtractedArtifact(page_number={self.page_number}, text_length={len(self.text)}, object_ref={self.object_ref}, description={self.description})"

class PossibleArtifactFinding():
    def __init__(self, page_number, text, artifact_type: ArtifactType, matched_data: str, matched_data_type: str):
        self.page_number : int = page_number
        self.text : str = text
        self.artifact_type = artifact_type
        self.matched_data = matched_data
        self.matched_data_type = matched_data_type

    @staticmethod
    def from_extracted_artifact(extracted_artifact: ExtractedArtifact, matched_data: str, matched_data_type: str) -> 'PossibleArtifactFinding':
        return PossibleArtifactFinding(
            page_number=extracted_artifact.page_number,
            text=extracted_artifact.text,
            artifact_type=extracted_artifact.artifact_type,
            matched_data=matched_data,
            matched_data_type=matched_data_type
        )
    
    def to_dict(self):
        return {
            "page_number": self.page_number,
            "text": self.text,
            "artifact_type": self.artifact_type.value,
            "matched_data": self.matched_data,
            "matched_data_type": self.matched_data_type
        }
    

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
    
def _extract_image_data_from_pdf_image(image) -> Image.Image:
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
    

def extract_pii(text):
    for key, value in PATTERNS.items():
        pii_match = re.findall(value, text)
        for match in pii_match:
            if match:
                yield (key, match)

async def _process_pdf(pdf_path: str):
    """ Processes a PDF file to extract text and images, yielding PII data found in the text.
    
    Args:
        pdf_path (str): The path to the PDF file.
    Yields:
        PossibleArtifactFinding: An object containing the page number, extracted text, and artifact type.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            logging.error(f"No pages found in PDF: {pdf_path}")
            raise StopAsyncIteration(f"No pages found in PDF: {pdf_path}")
        
        logging.info(f"Processing PDF: {pdf_path} with {len(pdf.pages)} pages")
        text = extract_text_from_pdf(pdf)
        images = extract_images_from_pdf(pdf)
        for artifact in text:
            if artifact.text:
                for data_type, data in extract_pii(artifact.text):
                    logging.debug(f"Extracted {data_type}: {data} from page {artifact.page_number} in text of PDF {pdf_path}")
                    yield PossibleArtifactFinding.from_extracted_artifact(artifact, data, data_type)

        async for artifact in images:
            if artifact.text:
                for data_type, data in extract_pii(" ".join(artifact.text)):
                    logging.debug(f"Extracted {data_type}: {data} from page {artifact.page_number} in image of PDF {pdf_path}")
                    yield PossibleArtifactFinding.from_extracted_artifact(artifact, data, data_type)

async def process_pdf_collection(pdf_path: list[str]) -> list[PossibleArtifactFinding]:
    """Processes a collection of PDF files to extract text and images, yielding PII data found in the text.
    
    Args:
        pdf_path (list[str]): A list of paths to the PDF files.
    
    Returns:
        list[PossibleArtifactFinding]: A list of PossibleArtifactFinding objects containing the page number, extracted text, and artifact type.
    """
    findings = []
    for path in pdf_path:
        try:
            async for finding in _process_pdf(path):
                findings.append(finding)
        except Exception as e:
            logging.error(f"Error processing PDF {path}: {e}", exc_info=True)
    
    return findings