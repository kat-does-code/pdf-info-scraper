# PDF Info Scraper
Scrapes text and images from PDFs in order to retrieve data.

## Getting Started
Ensure you have flox installed, clone this repo and activate from the working directory, or install requirements as necessary. This tool was tested against python version `3.12.10`.

```bash
usage: main.py [-h] [-o OUTPUT_DIR] [--debug] [--no-regex] files_or_directory [files_or_directory ...]

A simple command-line tool for extracting data from PDF files using regex patterns.

positional arguments:
  files_or_directory    A path to a PDF file or a directory containing them.

options:
  -h, --help            show this help message and exit
  -o OUTPUT_DIR, --output_dir OUTPUT_DIR
                        Directory to save output files (default: 'output').
  --debug               Enable debug mode for more verbose output.
  --no-regex            Disable regex matching on provided documents.
  ```

### Finding text
The tool finds white text, black text with black highlighter, and optionally [regexes.py](./regexes.py) that can be defined by the user. All regexes ought to be raw strings in python format.
