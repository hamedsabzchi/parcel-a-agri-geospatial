"""Isolated worker; structured errors are always retained for the notebook."""
import argparse
import json
from pathlib import Path
import traceback


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output-base',required=True)
    parser.add_argument('--result-path',required=True)
    args=parser.parse_args();result=Path(args.result_path)
    result.parent.mkdir(parents=True,exist_ok=True)
    try:
        from .pipeline import run
        output=run(args.input,args.output_base)
        result.write_text(json.dumps(output,allow_nan=False),encoding='utf-8')
        return 0
    except Exception as error:
        traceback.print_exc()
        result.write_text(json.dumps(dict(status='INCOMPLETE',error=f'{type(error).__name__}: {error}')),encoding='utf-8')
        return 1


if __name__=='__main__':raise SystemExit(main())
