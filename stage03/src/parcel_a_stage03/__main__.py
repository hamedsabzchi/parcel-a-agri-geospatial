import argparse
import json
import sys
import traceback
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description="Build Stage 03 from one verified Stage 02 run")
    p.add_argument("--root",required=True);p.add_argument("--input",required=True)
    p.add_argument("--output-base",required=True);p.add_argument("--result-path",required=True)
    p.add_argument("--core-only",action="store_true",help="Advanced: build only the original Stage 03 core")
    p.add_argument("--cache");p.add_argument("--ee-project");p.add_argument("--preflight",action="store_true")
    args=p.parse_args()
    phase="loading Stage 03 dependencies"
    try:
        # Keep dependency imports inside the error boundary. A broken environment
        # must still produce a readable result for the notebook's parent process.
        from .common import write_json
        from .pipeline import prepare, run
        from . import maize_workflow
        if not args.core_only:run=maize_workflow.run
        if args.preflight:
            phase="checking the Stage 02 or Stage 03 package"
            import tempfile
            with tempfile.TemporaryDirectory(prefix="stage03-preflight-",dir=Path(args.result_path).parent) as work:
                if not args.core_only:result=maize_workflow.preflight(args.root,args.input,work)
                else:
                    cfg,inputs,layers,rows,_=prepare(args.root,args.input,work)
                    result=dict(needs_earth_engine=any(l["extraction_status"]=="PENDING" and l["adapter"].startswith("ee_") for l in layers),
                        selected_layers=sum(l["extraction_status"]=="PENDING" for l in layers),aoi_sha256=inputs["aoi_sha256"])
        else:
            phase="building Stage 03 results"
            result=run(args.root,args.input,args.output_base,args.cache,args.ee_project,progress=lambda _:None)
        write_json(args.result_path,result)
    except Exception as error:
        traceback.print_exc()
        # This path intentionally uses only the standard library, including when
        # NumPy/rasterio or another dependency could not be imported.
        result_path=Path(args.result_path)
        result_path.parent.mkdir(parents=True,exist_ok=True)
        result_path.write_text(json.dumps(dict(outcome="INCOMPLETE",phase=phase,
            error=f"{type(error).__name__}: {error}"),indent=2),encoding="utf-8")
        return 1
    return 0


if __name__=="__main__":sys.exit(main())
