import argparse
import multiprocessing as mp
from pathlib import Path
import logging
from helpers import process_pdf
import asyncio
import json

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_args():
    parser = argparse.ArgumentParser(description="A simple command-line tool.")
    parser.add_argument("files_or_directory", type=str, help="A path to a PDF file or a directory containing them.")
    parser.add_argument("-o", "--output_dir", type=str, default="output", help="Directory to save output files (default: 'output').", required=False)
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for more verbose output.")
    
    args = parser.parse_args()
    
    files_or_directory = Path(args.files_or_directory)
    if files_or_directory.is_dir():
        pdf_files = list(files_or_directory.glob("*.pdf"))
        logging.debug(f"Found {len(pdf_files)} PDF files in directory: {files_or_directory}")
    elif files_or_directory.is_file() and files_or_directory.suffix.lower() == ".pdf":
        pdf_files = [files_or_directory]
        logging.debug(f"Processing single PDF file: {files_or_directory}")
    else:
        raise ValueError(f"Invalid input: {files_or_directory}. Please provide a valid PDF file or directory containing PDF files.")

    if not pdf_files:
        raise ValueError(f"No PDF files found in the specified path: {files_or_directory}. Please check the path and try again.")
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logging.debug(f"Output directory set to: {output_dir}")


    return pdf_files, output_dir

async def run_in_thread(path):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: asyncio.run(process_pdf(path)))
    except Exception as e:
        logging.error(f"Error processing PDF {path}: {e}", exc_info=True)
        return None
    
def main():
    target_files, output_dir = parse_args()
    logging.info(f"Starting processing of {len(target_files)} PDF files...")

    async def process_all_pdfs(pdf_paths):
        tasks = [run_in_thread(path) for path in pdf_paths]
        results = await asyncio.gather(*tasks)
        return [res for res in results if res is not None]

    loop = asyncio.get_event_loop()
    try:
        results = loop.run_until_complete(process_all_pdfs([f.as_posix() for f in target_files]))
    except Exception as e:
        logging.error(f"An error occurred during processing: {e}", exc_info=True)
        return

    with open(output_dir / "results.json", "w") as f:
        json.dump([finding.to_dict() for finding in results], f, indent=4)

if __name__ == "__main__":
    main()