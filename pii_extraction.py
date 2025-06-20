import re

def extract_pii(text):
    """
    Extracts Personally Identifiable Information (PII) from the given text.

    Args:
        text (str): The input text from which to extract PII.

    Returns:
        dict: A dictionary containing extracted PII such as email, phone number, and address.
    """
    pii = {
        'email': r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])""",
        'phone': r"\(?([+]31|0031|0)\s?-?6(\s?|-)([0-9]\s{0,3}){8}",
        'postcode': r"(\d{4}\s?[a-zA-Z]{2})",
        'bsn': r"\d{9}",
        'address': r"\d{1,5}\s\w+\s\w+,\s\w+\s\d{5}"
    }

    for key, value in pii.items():
        pii_match = re.findall(value, text)
        for match in pii_match:
            if match:
                yield (key, match)

    yield (None, None)