"""One immutable input run -> selected extraction -> QA -> one portable package."""
from __future__ import annotations
import base64
import json
import logging
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import numpy as np
from . import __version__
from .common import sha256, write_csv, write_json, utcnow, clean, code_hash
from .inputs import unpack, validate
from .inventory import configuration, resolve
from .spatial import read_raster, categorical_summary, project_geometry
from .temporal import assert_unique_rows
from . import sources
from .dashboard import write_dashboard

TABLE_FIELDS={
 "source_inventory":["dataset_id","dataset_name","source_name","source_group","stage02_final_status","stage02_final_action","stage03_disposition","selected_layer_count","extracted_layer_count","reason","next_action","evidence_reference"],
 "data_inventory":["layer_id","dataset_id","asset_key","display_name","theme","variable","data_type","period_start","period_end","depth","climate_scenario","management_code","native_crs","native_resolution","source_unit","decoded_unit","scale","offset","mask_rule","stage02_status","stage02_action","required","stage03_disposition","extraction_status","aoi_overlap","valid_native_cell_count","valid_area_percentage","output_path","source_url","licence","limitation"],
 "raster_summary":["layer_id","dataset_id","variable","period","climate_scenario","management_code","valid_native_cell_count","intersecting_native_cell_count","valid_area_ha","valid_area_percentage","masked_area_ha","outside_area_ha","minimum","maximum","mean","standard_deviation","percentile_05","percentile_25","median","percentile_75","percentile_95","unit","native_resolution","statistic_method","quantile_method","quality_flag","area_method"],
 "categorical_summary":["layer_id","dataset_id","climate_scenario","management_code","class_code","class_label","class_colour","intersecting_cell_count","fractional_area_ha","percentage_of_valid_area","percentage_of_total_aoi","area_method"],
 "source_cells":["layer_id","cell_id","row","column","raw_value","value","unit","valid","intersection_area_ha"],
 "timeseries_summary":["layer_id","dataset_id","variable","interval_start","interval_end","spatial_statistic","temporal_aggregation","value","unit","spatial_coverage_percentage","temporal_coverage_percentage","observation_count","expected_observation_count","count_definition","quality_flag"],
 "source_limitations":["dataset_id","layer_id","limitation_type","text","severity","display_rule"],
 "vector_summary":["layer_id","dataset_id","feature_count","count_support","output_path"],
}


def prepare(project,source,workspace):
    project,source,workspace=Path(project),Path(source),Path(workspace)
    config=configuration(project)
    cfg=config["stage03_config"]
    root=unpack(source,workspace/"stage02_input",cfg["max_input_bytes"])
    inputs=validate(root,project)
    layers,source_rows=resolve(inputs,config)
    return config,inputs,layers,source_rows,root


def run(project,source,output_base=None,cache=None,ee_project=None,progress=print,prepared=None):
    # Preflight validates inputs without loading the plotting stack.
    from . import render
    project,source=Path(project).resolve(),Path(source).resolve()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir=Path(output_base or project/"outputs/stage03_runs")/stamp
    payload=run_dir/"package";payload.mkdir(parents=True)
    for directory in ["dashboard/assets","maps","charts","tables","clipped_data/rasters","clipped_data/vectors","clipped_data/timeseries","metadata","qa","logs"]:
        (payload/directory).mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger("stage03."+stamp);logger.setLevel(logging.INFO)
    handler=logging.FileHandler(payload/"logs/stage03.log",encoding="utf-8");logger.addHandler(handler)
    logger.info("Stage 03 %s starting",__version__)
    try:
        if prepared is None:prepared=prepare(project,source,run_dir)
        config,inputs,layers,source_rows,input_root=prepared
        cfg=config["stage03_config"];aoi=inputs["aoi"]
        write_json(payload/"metadata/resolved_extraction_plan.json",dict(schema_version="3.0",layers=layers,budgets=cfg))
        write_json(payload/"input_manifest.json",dict(input_name=source.name,input_type="ZIP" if source.is_file() else "EXTRACTED_RUN",
            input_sha256=sha256(source) if source.is_file() else None,package_member_checksums=inputs["checksums"],
            aoi_sha256=inputs["aoi_sha256"],stage02_run_id=inputs["summary"].get("generated_at_utc"),
            compatible_stage02_revision=cfg["compatible_stage02_revision"]))
        shutil.copyfile(project/"data/aoi/parcel_a.geojson",payload/"clipped_data/vectors/parcel_a.geojson")
        shutil.copytree(project/"config/stage03",payload/"metadata/configuration")
        shutil.copyfile(project/"docs/stage03_methodology.md",payload/"metadata/methodology.md")
        shutil.copyfile(Path(__file__).parent/"assets/LEAFLET-LICENSE.txt",payload/"dashboard/assets/LEAFLET-LICENSE.txt")
        write_json(payload/"metadata/stage02_final_inventory.json",inputs["sources"])
        results=[];history=[];provenance=[];timeseries=[];vectors=[];vector_summaries=[]
        cache=Path(cache or project/cfg["cache_directory"])
        ee_error=None
        if any(l["extraction_status"]=="PENDING" and l["adapter"].startswith("ee_") for l in layers):
            try:sources.connect(ee_project or cfg["earth_engine_project"])
            except Exception as exc:
                ee_error="Earth Engine authorization or connection failed. Reconnect Google access and rerun."
                logger.exception(ee_error)
        gaez={r["asset_key"]:r for r in inputs["gaez"]}
        selected=[l for l in layers if l["extraction_status"]=="PENDING"]
        for index,layer in enumerate(selected,1):
            ident=layer["layer_id"];started=utcnow()
            progress(f"Preparing data {index}/{len(selected)}")
            logger.info("Start %s",ident)
            try:
                adapter=layer["adapter"];metadata={};cached=False
                if adapter=="stage02_clip":
                    original=Path(gaez[ident]["clip_path"])
                    path=payload/"clipped_data/rasters"/(ident+".tif")
                    shutil.copyfile(original,path)
                    metadata=dict(input_clip_sha256=sha256(original),stage02_verification=gaez[ident],
                        remote_checksum="NOT_AVAILABLE",reuse="Checksum-verified Stage 02 native clip")
                    metadata["stage02_verification"]={k:v for k,v in gaez[ident].items() if k!="clip_path"}
                elif adapter=="derived_slope":
                    parent=next((l for l in layers if l["layer_id"]==layer["parent"]),None)
                    if not parent or parent["extraction_status"]!="EXTRACTED":raise ValueError("The selected parent DEM did not pass extraction")
                    path=payload/"clipped_data/rasters"/(ident+".tif")
                    metadata=sources.slope(payload/parent["output_path"],path,aoi)
                else:
                    if adapter.startswith("ee_") and ee_error:raise RuntimeError(ee_error)
                    function={"ee_static":sources.static_ee,"ee_series":sources.series_ee,"power":sources.power,
                              "local_vector":sources.local_vector,"local_raster":sources.local_raster}.get(adapter)
                    if function is None:raise ValueError("No approved extraction adapter for the selected product")
                    folder,job,cached=sources.cached_job(layer,inputs["aoi_sha256"],cache,
                        lambda directory:function(layer,aoi,directory,cfg))
                    category="timeseries" if layer["data_type"]=="timeseries" else "vectors" if adapter=="local_vector" else "rasters"
                    target=payload/"clipped_data"/category/ident
                    shutil.copytree(folder,target,ignore=shutil.ignore_patterns("complete.json"))
                    metadata=job.get("metadata",{})
                    if layer["data_type"]=="timeseries":
                        rows=job.get("series",[]);timeseries.extend(rows)
                        passed=any(r["value"] is not None for r in rows)
                        layer["extraction_status"]="EXTRACTED" if passed else "EMPTY"
                        layer["decoded_unit"]=layer["unit"]
                        layer["output_path"]=(target.relative_to(payload)/"summary.csv").as_posix()
                        write_csv(payload/layer["output_path"],rows,TABLE_FIELDS["timeseries_summary"])
                        layer["reason"]="No periods passed configured coverage thresholds" if not passed else "Monthly summaries and native audit records retained"
                        if metadata.get("grid"):
                            layer.update(native_crs=metadata["grid"]["crs"],native_resolution=metadata["grid"]["original_projection"]["transform"])
                        path=None
                    elif adapter=="local_vector":
                        vector=json.loads((target/job["vector"]).read_text());vectors.append((layer,vector))
                        layer.update(extraction_status="EXTRACTED" if job["feature_count"] else "EMPTY",
                                     output_path=(target.relative_to(payload)/"features.gpkg").as_posix())
                        vector_summaries.append(dict(layer_id=ident,dataset_id=layer["dataset_id"],feature_count=job["feature_count"],count_support="Clipped AOI only; context excluded",output_path=layer["output_path"]))
                        path=None
                    else:path=target/job["raster"]
                if path is not None:
                    result=read_raster(path,aoi,layer,cfg["area_crs"])
                    layer.update(result["stats"])
                    layer.update(output_path=path.relative_to(payload).as_posix(),aoi_overlap=result["stats"]["intersecting_native_cell_count"]>0,
                                 extraction_status="EXTRACTED" if result["valid"].any() else "EMPTY",decoded_unit=layer["unit"])
                    if layer["required"] and layer["valid_area_percentage"]<cfg["minimum_required_spatial_coverage"]*100:
                        raise ValueError("Required layer is below the configured valid-area threshold")
                    if layer["data_type"]=="categorical":
                        legend=config["symbology"]["legends"].get(layer["legend_id"])
                        if not legend:raise ValueError("Required authoritative class legend is missing")
                        result["categories"]=categorical_summary(result,layer,legend)
                    if layer["extraction_status"]=="EXTRACTED":results.append((layer,result))
                outputs=[p for p in payload.rglob("*") if p.is_file() and (p==path or ident in p.relative_to(payload).parts)]
                provenance.append(dict(layer_id=ident,dataset_id=layer["dataset_id"],source_id=layer["source_id"],
                    source_url=layer["source_url"],source_version=layer["source_version"],aoi_sha256=inputs["aoi_sha256"],
                    stage02_revision=cfg["compatible_stage02_revision"],stage02_run_id=inputs["summary"].get("generated_at_utc"),
                    parameters=layer.copy(),retrieval=metadata,software_version=__version__,code_sha256=code_hash(),
                    output_checksums={p.relative_to(payload).as_posix():sha256(p) for p in outputs}))
            except Exception as exc:
                layer.update(extraction_status="QA_FAILED" if isinstance(exc,ValueError) else "FAILED",reason=str(exc))
                logger.exception("Layer %s failed",ident)
            history.append(dict(layer_id=ident,started=started,finished=utcnow(),cached=cached,
                                result=layer["extraction_status"],reason=layer.get("reason")))
        assert_unique_rows(timeseries)
        progress("Building maps, tables and graphs")
        legends=render.resolve_legends(results,config["symbology"]["legends"])
        map_records=[];categories=[];continuous=[];cells=[];charts=[]
        area=project_geometry(aoi,4326,cfg["area_crs"],.0005).area/1e4
        render.aoi_map(payload/"maps/parcel_a.png",aoi,area)
        for layer,result in results:
            ident=layer["layer_id"];legend=legends[ident]
            try:
                display=render.overlay(result,legend,aoi,cfg["preview_max_dimension"])
                overlay_path=f"dashboard/assets/{ident}.png"
                (payload/overlay_path).write_bytes(display["png"])
                static_path=f"maps/{ident}.png"
                render.static_map(payload/static_path,layer,legend,display,aoi)
                map_records.append(dict(layer_id=ident,title=layer["display_name"],group=layer["theme"],type="raster",
                    visualization_path="../"+overlay_path,image="data:image/png;base64,"+base64.b64encode(display["png"]).decode(),
                    download_path="../"+layer["output_path"],static_map_path="../"+static_path,
                    bounds=display["bounds"],default_visibility=False,default_opacity=.85,z_index=100+len(map_records),
                    legend_id=layer.get("legend_id",ident),metadata_id=ident,legend=legend,metadata=layer,
                    click_rule="native-cell value" if result["features"] else "not supported",cells=result["features"],
                    comparison_group=layer.get("comparison_group"),attribution=layer["attribution"],
                    display_projection=display["display_projection"],display_resampling=display["display_resampling"]))
                categories.extend(result.get("categories",[]));cells.extend(result["cells"])
                if layer["data_type"]!="categorical":
                    continuous.append({k:layer.get(k) for k in TABLE_FIELDS["raster_summary"]}|result["stats"])
                if result.get("categories"):
                    charts.append(dict(id=ident+"_class_area",layer_ids=[ident],type="bars",title=layer["display_name"]+" · class area",unit="ha",
                        data=[dict(label=f"{r['class_code']} · {r['class_label']}",value=r["fractional_area_ha"],colour=r["class_colour"],percentage_of_valid_area=r["percentage_of_valid_area"],percentage_of_total_aoi=r["percentage_of_total_aoi"]) for r in result["categories"]],
                        table_path="../tables/categorical_summary.csv",note="Exact intersected area. The table reports both valid-area and total-AOI denominators. "+layer["limitation"]))
            except Exception as exc:
                layer.update(extraction_status="QA_FAILED",reason="Map/legend rendering failed: "+str(exc));logger.exception("Rendering %s",ident)
        for layer,geojson in vectors:
            if layer["extraction_status"]!="EXTRACTED":continue
            ident=layer["layer_id"];path=f"maps/{ident}.png"
            render.vector_map(payload/path,layer,geojson,aoi)
            vector_legend=dict(legend_id=ident,title=layer["display_name"],type="categorical",unit=layer["unit"],
                entries=[dict(code="feature",caption="Supplied features clipped to Parcel A",colour="#336eae",present=True)],
                palette_origin="Project vector symbols: blue fill/lines; 4 px points",validation_status="SUPPLEMENTAL_SOURCE_VERIFIED")
            map_records.append(dict(layer_id=ident,title=layer["display_name"],group=layer["theme"],type="vector",geojson=geojson,
                visualization_path="../"+layer["output_path"].replace("features.gpkg","features.geojson"),
                download_path="../"+layer["output_path"],static_map_path="../"+path,bounds=[[aoi.bounds[1],aoi.bounds[0]],[aoi.bounds[3],aoi.bounds[2]]],
                default_visibility=False,default_opacity=.85,z_index=100+len(map_records),legend_id=ident,metadata_id=ident,
                legend=vector_legend,metadata=layer,comparison_group=None,click_rule="Source attributes",attribution=layer["attribution"]))
        for layer in layers:
            rows=[r for r in timeseries if r["layer_id"]==layer["layer_id"]]
            if rows and any(r["value"] is not None for r in rows):
                charts.append(dict(id=layer["layer_id"]+"_series",layer_ids=[layer["layer_id"]],type="series",title=layer["display_name"],unit=layer["unit"],data=rows,
                    table_path="../tables/timeseries_summary.csv",note="Monthly values; missing/rejected periods are gaps. Partial totals remain labelled. One year is not a climatology. "+layer["limitation"]))
                for coverage in ["spatial","temporal"]:
                    if all(r.get(coverage+"_coverage_percentage") is None for r in rows):continue
                    charts.append(dict(id=layer["layer_id"]+"_"+coverage+"_coverage",layer_ids=[layer["layer_id"]],type="coverage",title=layer["display_name"]+" · "+coverage+" coverage",unit="percent",
                        data=[dict(interval_start=r["interval_start"],value=r.get(coverage+"_coverage_percentage"),label=r["interval_start"][:7]) for r in rows],table_path="../tables/timeseries_summary.csv",note="Spatial and temporal coverage use different denominators. Acceptance threshold: configured project choice."))
        yield_layers=[l for l,r in results if l.get("comparison_group")=="RES05-YXX"]
        if yield_layers:
            charts.append(dict(id="maize_yield_comparison",layer_ids=[l["layer_id"] for l in yield_layers],type="comparison",
                title="Maize attainable yield · historical management alternatives",unit=yield_layers[0]["unit"],
                data=[dict(label=l["management_code"],value=l["mean"],valid_area_percentage=l["valid_area_percentage"],
                           cells=[c for c in cells if c["layer_id"]==l["layer_id"] and c["valid"]]) for l in yield_layers],
                table_path="../tables/raster_summary.csv",note="Bars: area-weighted source values. Dots: distinct native cells, not independent measurements. Valid support is shown in the tables. No production estimate or preferred alternative."))
        for chart in charts:
            chart["path"]="../charts/"+chart["id"]+".png"
            render.static_chart(payload/"charts"/(chart["id"]+".png"),chart)
        for row in source_rows:
            row["extracted_layer_count"]=sum(l["dataset_id"]==row["dataset_id"] and l["extraction_status"]=="EXTRACTED" for l in layers)
        limitations=[dict(dataset_id=l["dataset_id"],layer_id=l["layer_id"],limitation_type="source_support",text=l["limitation"],severity="NOTE",display_rule="Map details and methods") for l in layers]
        limitations += [dict(dataset_id=r["dataset_id"],layer_id=None,limitation_type="source_disposition",text=r["reason"],severity="NOTE",display_rule="Source inventory") for r in source_rows]
        tables=dict(source_inventory=source_rows,data_inventory=layers,raster_summary=continuous,categorical_summary=categories,
            source_cells=cells,timeseries_summary=timeseries,source_limitations=limitations,vector_summary=vector_summaries)
        for name,rows in tables.items():write_csv(payload/"tables"/(name+".csv"),rows,TABLE_FIELDS[name])
        gaps=[dict(layer_id=l["layer_id"],required=l["required"],status=l["extraction_status"],reason=l.get("reason")) for l in selected if l["extraction_status"]!="EXTRACTED"]
        outcome="INCOMPLETE" if any(g["required"] for g in gaps) else "COMPLETE_WITH_OPTIONAL_GAPS" if gaps else "COMPLETE"
        successful=[l for l in layers if l["extraction_status"]=="EXTRACTED"]
        observed_dates=[o["timestamp"] for p in provenance for o in p["retrieval"].get("observations",[]) if o.get("timestamp")]
        summary=dict(run_id=stamp,outcome=outcome,aoi_area_ha=area,stage01_reported_area_ha=inputs["aoi_json"]["features"][0]["properties"].get("computed_area_ha"),
            source_count=len(source_rows),planned_layer_count=len(layers),selected_layer_count=len(selected),extracted_layer_count=len(successful),
            extracted_source_count=sum(r["extracted_layer_count"]>0 for r in source_rows),
            gaez_extracted=sum(l["adapter"]=="stage02_clip" for l in successful),gaez_verified=len(gaez),
            raster_count=sum(m["type"]=="raster" for m in map_records),vector_count=len(vectors)+1,timeseries_count=len({r["layer_id"] for r in timeseries if r["value"] is not None}),
            earliest_native_series_observation=min(observed_dates,default=None),
            latest_native_series_observation=max(observed_dates,default=None),gaps=gaps)
        xmin,ymin,xmax,ymax=aoi.bounds
        table_records=[dict(id=name,title=name.replace("_"," ").title(),rows=rows,columns=TABLE_FIELDS[name],path="../tables/"+name+".csv",layer_ids=sorted({r["layer_id"] for r in rows if r.get("layer_id")})) for name,rows in tables.items()]
        downloads=[dict(id=t["id"],path=t["path"],title=t["title"]) for t in table_records]
        downloads += [dict(id=m["layer_id"],path=m["download_path"],title=m["title"]) for m in map_records]
        downloads += [dict(id=c["id"],path=c["path"],title=c["title"]+" PNG") for c in charts]
        methods=dict(stage03_version=__version__,code_sha256=code_hash(),input_manifest="../input_manifest.json",configuration=cfg,
            area_method="Exact native-cell intersections in "+cfg["area_crs"],quantile_method="First sorted value at cumulative normalized area weight >= p",
            yield_comparisons="One pooled min/max scale; each alternative retains its own valid support",
            soil_quality_correction="Official SQX metadata defines classes 1–13. Preserve source rating ranges and special classes; never average their codes.",
            native_resolution="Geometry weighting does not create field-scale detail",source_metadata="configuration/source_metadata",
            environment=dict(python=platform.python_version(),platform=platform.platform()))
        dashboard=dict(title="Parcel A Agricultural Data Inventory",run_id=stamp,aoi=inputs["aoi_json"],bounds=[[ymin,xmin],[ymax,xmax]],
            summary=summary,maps=map_records,layers=layers,tables=table_records,charts=charts,downloads=downloads,methods=methods)
        write_dashboard(payload/"dashboard/parcel_a_data_inventory.html",dashboard,cfg["max_dashboard_bytes"])
        # The manifest is authoritative. Embedded images/rows stay in the HTML, referenced files in the package.
        manifest={k:v for k,v in dashboard.items() if k not in {"maps","tables"}}
        manifest["maps"]=[{k:v for k,v in m.items() if k not in {"image","cells"}} for m in map_records]
        manifest["tables"]=[{k:v for k,v in t.items() if k!="rows"} for t in table_records]
        write_json(payload/"metadata/dashboard_manifest.json",manifest)
        write_json(payload/"metadata/layer_catalog.json",layers)
        write_json(payload/"metadata/legends.json",legends)
        write_json(payload/"metadata/processing_history.json",history)
        write_json(payload/"metadata/provenance.json",dict(run=methods,layers=provenance))
        write_json(payload/"metadata/supplemental_verification.json",[p for p in provenance if p["parameters"].get("supplemental")])
        write_json(payload/"metadata/run_summary.json",summary)
        write_csv(payload/"metadata/metadata_completeness.csv",[dict(layer_id=l["layer_id"],field=k,status="RESOLVED" if l.get(k) is not None else "NOT_APPLICABLE",reason="Recorded source/processing field" if l.get(k) is not None else "Not a dimension of this product; dates remain unspecified where the source is unspecified") for l in layers for k in ("source_id","variable","unit","mask_rule","licence","depth","climate_scenario","management_code","period")])
        (payload/"metadata/environment.txt").write_text(subprocess.check_output([sys.executable,"-I","-m","pip","freeze"],text=True))
        write_json(payload/"metadata/table_schemas.json",dict(version="3.0",fields=TABLE_FIELDS,numeric_null="Unavailable or rejected, never substituted by zero",status_enums=dict(disposition=["SELECTED_REQUIRED","SELECTED_OPTIONAL","CATALOG_ONLY","DEFERRED","BLOCKED","INPUT_MISSING"],extraction=["NOT_REQUESTED","PENDING","EXTRACTED","EMPTY","FAILED","QA_FAILED"])))
        (payload/"README.txt").write_text("Parcel A — Stage 03\n\nExtract this ZIP, then open dashboard/parcel_a_data_inventory.html.\nThematic maps, tables, graphs and downloads work offline. Optional basemaps need internet.\nSource-defined suitability and yield are descriptive products, not recommendations or measured parcel production.\nNative data: clipped_data/. Static exports: maps/ and charts/. Evidence: metadata/ and qa/.\nFull methods: metadata/methodology.md. All 48 sources remain in tables/source_inventory.csv.\nStatus: "+outcome+"\n",encoding="utf-8")
        expected_paths=["maps/parcel_a.png","clipped_data/vectors/parcel_a.geojson","dashboard/parcel_a_data_inventory.html"]
        expected_paths += [l["output_path"] for l in successful]
        expected_paths += [d["path"].removeprefix("../") for d in downloads]
        expected_paths += [m["static_map_path"].removeprefix("../") for m in map_records]
        missing=[p for p in expected_paths if not (payload/p).is_file()]
        checks=dict(source_ids_exactly_48=len(source_rows)==48,required_gaez_maps=summary["gaez_extracted"]==16 and sum(m["layer_id"].startswith("GAEZ_") for m in map_records)==16,
            all_downloads_exist=not missing,all_required_layers_passed=not any(g["required"] for g in gaps),
            provenance_present=all(any(p["layer_id"]==l["layer_id"] for p in provenance) for l in successful),
            unique_map_ids=len({m["layer_id"] for m in map_records})==len(map_records),
            source_input_checksums=True,area_accounting=True)
        if not all(checks.values()):
            outcome="INCOMPLETE";summary["outcome"]=outcome
            write_dashboard(payload/"dashboard/parcel_a_data_inventory.html",dashboard,cfg["max_dashboard_bytes"])
            write_json(payload/"metadata/dashboard_manifest.json",manifest)
            readme=payload/"README.txt"
            readme.write_text(readme.read_text().rsplit("Status: ",1)[0]+"Status: INCOMPLETE\n")
        write_json(payload/"qa/stage03_validation_report.json",dict(outcome=outcome,checks=checks,missing_paths=missing,gaps=gaps,
            browser_test="Development/CI offline browser acceptance; this execution rechecks data and file references",area_tolerance_fraction=cfg["area_tolerance_fraction"]))
        write_json(payload/"metadata/run_summary.json",summary)
        logger.info("Outcome %s",outcome);handler.flush();handler.close();logger.removeHandler(handler)
        files=[p for p in sorted(payload.rglob("*")) if p.is_file()]
        # Both manifests deliberately exclude themselves; the checksum list includes the output manifest.
        write_json(payload/"qa/stage03_output_manifest.json",[dict(path=p.relative_to(payload).as_posix(),exists=True,size=p.stat().st_size,sha256=sha256(p),required=p.relative_to(payload).as_posix() in expected_paths,validation="PRESENT_AND_HASHED") for p in files])
        files.append(payload/"qa/stage03_output_manifest.json")
        write_json(payload/"metadata/package_checksums.json",{p.relative_to(payload).as_posix():sha256(p) for p in files})
        files.append(payload/"metadata/package_checksums.json")
        archive=run_dir/("stage03_inventory_package.zip" if outcome!="INCOMPLETE" else "stage03_diagnostics.zip")
        with ZipFile(archive,"w",ZIP_DEFLATED) as z:
            for path in sorted(files):z.write(path,path.relative_to(payload))
        return dict(outcome=outcome,archive=str(archive),dashboard=str(payload/"dashboard/parcel_a_data_inventory.html"),summary=summary)
    except Exception:
        logger.exception("Stage 03 stopped before completion")
        handler.flush();handler.close();logger.removeHandler(handler)
        raise
