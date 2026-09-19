"""Keep all source decisions, while planning only explicit eligible products."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import yaml


def configuration(project):
    base=Path(project)/"config/stage03"
    return {name:yaml.safe_load((base/(name+".yml")).read_text()) for name in
            ("stage03_config","layer_catalog","symbology","timeseries_config")}


def disposition(row):
    status,action=row["FINAL_STATUS"],row["FINAL_ACTION"]
    if row["dataset_id"].startswith("FUTURE_") or row["dataset_id"] in {"FAO_GAEZ_V5_FUTURE","FAO_CAVA"}:
        return "DEFERRED","A separate approved model, scenario and period plan is needed."
    if status=="INPUT_NOT_SUPPLIED": return "INPUT_MISSING","No project file supplied."
    if status in {"SERVICE_OR_ENDPOINT_FAILED","AUTHENTICATION_OR_LICENSE_REQUIRED"}:
        return "BLOCKED",row["FINAL_EVIDENCE"]
    if status=="DEFERRED": return "DEFERRED",row["FINAL_EVIDENCE"]
    return "CATALOG_ONLY",row["FINAL_EVIDENCE"]


def resolve(inputs, config):
    sources={r["dataset_id"]:r for r in inputs["sources"]}
    specs=copy.deepcopy(config["layer_catalog"]["layers"])
    # Explicitly configured supplemental files do not rewrite Stage 02 evidence.
    for supplied in config["stage03_config"].get("supplemental_files",[]):
        needed={"layer_id","dataset_id","display_name","local_path","expected_sha256","unit","data_type",
                "variable","mask_rule","licence","licence_url","source_url","metadata_url","limitation"}
        if needed-set(supplied):raise ValueError("Supplemental file definition is incomplete: "+", ".join(sorted(needed-set(supplied))))
        if supplied["dataset_id"] not in sources:raise ValueError("Supplemental file must link to a retained Stage 02 source")
        if supplied["data_type"]=="categorical" and supplied.get("legend_id") not in config["symbology"]["legends"]:
            raise ValueError("Supplemental categorical file requires a documented code-to-caption legend")
        defaults=dict(required=False,enabled=True,scale=1,offset=0,scale_already_applied=False,
            nodata=None,source_version=supplied["expected_sha256"],source_id=supplied["local_path"],
            theme="Supplied project data",provider="User-supplied source",attribution="See supplied source metadata",
            processing="Supplemental file verification then native AOI clipping",download_eligible=True,
            adapter="local_vector" if supplied["data_type"]=="vector" else "local_raster",supplemental=True)
        specs.append({**defaults,**supplied})
    layers=[]
    for layer in specs:
        row=sources[layer["dataset_id"]]
        state,reason=disposition(row)
        layer.update(stage02_status=row["FINAL_STATUS"],stage02_action=row["FINAL_ACTION"],
                     stage02_evidence=row["FINAL_EVIDENCE"], extraction_status="NOT_REQUESTED")
        action=row["FINAL_ACTION"]
        eligible=row["FINAL_STATUS"]=="VERIFIED_INSIDE_AOI" and (
            action=="USE_NEXT" or (action in {"USE_LATER","OPTIONAL"} and layer.get("enable_later",False)))
        if eligible and layer.get("enabled",True) and state!="DEFERRED":
            state="SELECTED_REQUIRED" if layer["required"] else "SELECTED_OPTIONAL"
            reason="Selected exact product; extraction-specific QA is still required."
            layer["extraction_status"]="PENDING"
        if layer.get("supplemental") and state!="DEFERRED":
            state="SELECTED_REQUIRED" if layer["required"] else "SELECTED_OPTIONAL"
            reason="Supplied file: independent checksum, geometry, units and AOI verification required. Original Stage 02 decision preserved."
            layer["extraction_status"]="PENDING"
        if layer.get("resolve_from_evidence"):
            evidence=row.get("Stage_02B_evidence_json",[])
            if isinstance(evidence,str):
                try: evidence=json.loads(evidence)
                except (ValueError,TypeError): evidence=[]
            candidates=[e for e in evidence if isinstance(e,dict) and any(
                isinstance(v,(int,float)) and v is not None for v in e.get("sample",{}).values())] if isinstance(evidence,list) else []
            match=next((e for e in candidates if e.get("collection")==layer["source_id"]),None)
            if not match:
                state,reason="CATALOG_ONLY","This exact WaPOR variable was not the verified Level 2 sample."
                layer["extraction_status"]="NOT_REQUESTED"
            else:
                layer["verified_sample"]=match
        if layer["required"] and state!="SELECTED_REQUIRED":
            raise ValueError(f"Required layer is not eligible: {layer['layer_id']}")
        layer.update(stage03_disposition=state,reason=reason)
        if layer.get("adapter")=="ee_series" or layer.get("adapter")=="power":
            layer.update(config["timeseries_config"]["defaults"])
            layer.update(config["timeseries_config"].get("overrides",{}).get(layer["layer_id"],{}))
            layer.update(period_start=layer["start"],period_end=layer["end"])
        layers.append(layer)
    if len({l["layer_id"] for l in layers})!=len(layers): raise ValueError("Duplicate planned layer ID")
    source_rows=[]
    for row in inputs["sources"]:
        planned=[l for l in layers if l["dataset_id"]==row["dataset_id"]]
        selected=[l for l in planned if l["extraction_status"]=="PENDING"]
        state,reason=disposition(row)
        if selected:
            state="SELECTED_REQUIRED" if any(l["required"] for l in selected) else "SELECTED_OPTIONAL"
            reason="See the exact variables, dates and extraction outcomes in the layer inventory."
        source_rows.append(dict(dataset_id=row["dataset_id"],dataset_name=row["dataset_name"],
            source_name=row["source_name"],source_group=row["source_group"],
            stage02_final_status=row["FINAL_STATUS"],stage02_final_action=row["FINAL_ACTION"],
            stage03_disposition=state,selected_layer_count=len(selected),extracted_layer_count=0,
            reason=reason,next_action=row["FINAL_ACTION"],
            evidence_reference="Stage 02 final/metadata/final_data_inventory.json#"+row["dataset_id"]))
    return layers,source_rows
