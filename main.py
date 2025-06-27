import argparse
import multiprocessing as mp
from pathlib import Path
import logging
from helpers import process_pdf
import asyncio
import json
from classes import ExecutionConfiguration

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_args() -> ExecutionConfiguration:
    parser = argparse.ArgumentParser(description="A simple command-line tool for extracting data from PDF files using regex patterns.")
    parser.add_argument("files_or_directory", type=str, nargs="+", help="A path to a PDF file or a directory containing them.")
    parser.add_argument("-o", "--output_dir", type=str, default="output", help="Directory to save output files (default: 'output').", required=False)
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for more verbose output.")
    parser.add_argument("--no-regex", action="store_true", help="Disable regex matching on provided documents.")
    
    args = parser.parse_args()
    
    files_or_directory = [ Path(f) for f in args.files_or_directory ]
    has_only_valid_paths = all([ f.is_dir() or f.is_file() for f in files_or_directory ])
    if not has_only_valid_paths:
        raise ValueError("One or more paths are invalid. ")
    
    pdf_files = []
    for fp in files_or_directory:
        if fp.is_dir():
            pdf_files += list(fp.glob("*.pdf"))
            logging.debug(f"Found {len(pdf_files)} PDF files in directory: {fp}")
        elif fp.is_file() and fp.suffix.lower() == ".pdf":
            pdf_files += [fp]
            logging.debug(f"Processing single PDF file: {fp}")
        else:
            raise ValueError(f"Invalid input: {fp}. Please provide a valid PDF file or directory containing PDF files.")

    if not pdf_files:
        raise ValueError(f"No PDF files found in the provided paths. Please check the path and try again.")
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(Path.cwd())
    logging.debug(f"Output will be placed in: {output_dir}")

    return ExecutionConfiguration(pdf_files, output_dir, do_execute_regex=(not args.no_regex))

async def run_in_thread(**kwargs):
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: asyncio.run(process_pdf(**kwargs)))
    except Exception as e:
        logging.error(f"Error processing PDF {kwargs.get('pdf_path')}: {e}", exc_info=True)
        return None
    
async def process_all_pdfs(config: ExecutionConfiguration):
    tasks = [run_in_thread(pdf_path=path, do_regex=config.do_execute_regex, output_path=config.output_dir) for path in config.pdf_files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [res for res in results if res is not None]

def main():
    config = parse_args()
    logging.info(f"Starting processing of {len(config.pdf_files)} PDF files...")


    loop = asyncio.get_event_loop()
    try:
        results = loop.run_until_complete(process_all_pdfs(config))
    except Exception as e:
        logging.error(f"An error occurred during processing: {e}", exc_info=True)
        return

    with open(config.output_dir / "results.json", "w") as f:
        json.dump([pdf.to_dict() for pdf in results], f, indent=4)

if __name__ == "__main__":
    main()