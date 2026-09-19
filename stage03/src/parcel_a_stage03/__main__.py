import argparse
import json
import sys
import traceback
from pathlib import Path
from .common import write_json
from .pipeline import prepare, run


def main():
    p=argparse.ArgumentParser(description="Build Stage 03 from one verified Stage 02 run")
    p.add_argument("--root",required=True);p.add_argument("--input",required=True)
    p.add_argument("--output-base",required=True);p.add_argument("--result-path",required=True)
    p.add_argument("--cache");p.add_argument("--ee-project");p.add_argument("--preflight",action="store_true")
    args=p.parse_args()
    try:
        if args.preflight:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="stage03-preflight-",dir=Path(args.result_path).parent) as work:
                cfg,inputs,layers,rows,_=prepare(args.root,args.input,work)
                result=dict(needs_earth_engine=any(l["extraction_status"]=="PENDING" and l["adapter"].startswith("ee_") for l in layers),
                    selected_layers=sum(l["extraction_status"]=="PENDING" for l in layers),aoi_sha256=inputs["aoi_sha256"])
        else:result=run(args.root,args.input,args.output_base,args.cache,args.ee_project,progress=lambda _:None)
        write_json(args.result_path,result)
    except Exception as error:
        write_json(args.result_path,dict(outcome="INCOMPLETE",error=str(error),corrective_action="Use the complete, unmodified Stage 02 ZIP; inspect the retained log if extraction failed."))
        traceback.print_exc()
        return 1
    return 0


if __name__=="__main__":sys.exit(main())
