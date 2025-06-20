import imagehash
from PIL import Image

def compare_images(image1_path, image2_path):
    """
    Compares two images and returns a similarity score.

    Args:
        image1 (PIL.Image): The first image.
        image2 (PIL.Image): The second image.

    Returns:
        float: A similarity score between 0 and 1, where 1 means identical.
    """

    image1 = Image.open(image1_path)
    image2 = Image.open(image2_path)

    hash1 = imagehash.average_hash(image1)
    hash2 = imagehash.average_hash(image2)
    return 1 - (hash1 - hash2) / len(hash1.hash) ** 2