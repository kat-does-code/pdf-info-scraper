import io
from pydoc import resolve
import zlib
import pdfplumber 
import easyocr
from PIL import Image

def extract_text_from_pdf(pdf_path):
    """ 
    Extracts text from a PDF file.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        str: The extracted text from the PDF.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ''
            for page in pdf.pages:
                text += page.extract_text(x_tolerance=1, y_tolerance=1)  + '\n'
            return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None
    
def _extract_images_as_pdfstream_from_pdf(pdf_path):
    """
    Extracts images from a PDF file.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        list: A list of images extracted from the PDF.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            images = []
            for page in pdf.pages:
                for img in page.images:
                    images.append(img)
            return images
    except Exception as e:
        print(f"Error extracting images from PDF: {e}")
        return []
    
def extract_images_from_pdf(pdf_path):
    """
    Extracts images from a PDF file and returns them as a list of bytes.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        list: A list of image data in bytes.
    """
    images = _extract_images_as_pdfstream_from_pdf(pdf_path)
    for i,image in enumerate(images):
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
            yield Image.open(io.BytesIO(data))

        elif  "FlateDecode" in str(filter_):
            # Assume RGB or grayscale (add more checks if needed)
            mode = "L" if "DeviceGray" in resolve(color_space) else "RGB"
            yield Image.frombytes(mode, (width, height), data)

        elif "JPXDecode" in str(filter_):
            # JPEG2000 - supported by Pillow
            yield Image.open(io.BytesIO(data))

        else:
            raise NotImplementedError(f"Unsupported filter: {filter_}")
    
def extract_text_from_image(image):
    """
    Extracts text from an image using OCR.

    Args:
        image_stream (bytes): The image data in bytes.

    Returns:
        str: The extracted text from the image.
    """
    try:
        reader = easyocr.Reader(['en', 'nl'], gpu=False)
        result = reader.readtext(image, detail=0)
        return ' '.join(result)
    except Exception as e:
        print(f"Error extracting text from image: {e}")
        return None
    
