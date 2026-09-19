"""One legend registry for static exports, overlays, and the offline dashboard."""
from __future__ import annotations
import base64
import io
import math
import textwrap
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, to_rgba, to_hex
from matplotlib.patches import Patch
import numpy as np
from PIL import Image
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds, reproject, Resampling
from shapely.geometry import mapping
from .spatial import project_geometry


def resolve_legends(results,registry):
    import copy
    resolved={}
    for layer,result in results:
        key=layer.get("legend_id",layer["layer_id"])
        legend=copy.deepcopy(registry[key] if key in registry else dict(legend_id=key,title=layer["display_name"],type="continuous",
            unit=layer["unit"],palette="viridis",palette_origin="Project Viridis",source_url=layer["metadata_url"],
            validation_status="SOURCE_UNITS_VERIFIED",nodata="No data (transparent)"))
        if legend["type"]=="continuous":
            pool=[r["values"][np.isfinite(r["values"])] for l,r in results if l.get("legend_id",l["layer_id"])==key]
            values=np.concatenate(pool)
            if not values.size:raise ValueError("No valid values for a continuous legend")
            lo,hi=float(values.min()),float(values.max())
            legend.update(domain=[lo,hi],constant=lo==hi,domain_method="Pooled valid min/max; same scale for every member")
            legend["display_domain"]=[lo-.5,hi+.5] if lo==hi else [lo,hi]
        elif legend["type"]=="categorical":
            observed=set(map(int,np.unique(result["values"][np.isfinite(result["values"])])))
            legend["entries"]=[dict(e,present=e["code"] in observed) for e in legend["entries"]]
        resolved[layer["layer_id"]]=legend
    return resolved


def rgba(values,legend):
    valid=np.isfinite(values)
    colours=np.zeros((*values.shape,4),dtype="uint8")
    if legend["type"]=="categorical":
        for e in legend["entries"]:colours[values==e["code"]]=np.array(to_rgba(e["colour"]))*255
    elif legend["type"]=="binned":
        index=np.searchsorted(legend["breaks"],values,side="left")
        for i,c in enumerate(legend["colours"]):colours[valid&(index==i)]=np.array(to_rgba(c))*255
    else:
        lo,hi=legend["display_domain"]
        norm=Normalize(lo,hi)
        colours=(matplotlib.colormaps[legend.get("palette","viridis")](norm(np.nan_to_num(values,nan=lo)))*255).astype("uint8")
    colours[~valid,3]=0
    return colours


def overlay(result,legend,aoi,maximum=1000):
    values=result["values"]
    h,w=values.shape
    t=result["transform"]
    from rasterio.transform import array_bounds
    bounds=transform_bounds(result["crs"],"EPSG:3857",*array_bounds(h,w,t),densify_pts=21)
    width=maximum; height=max(1,round(width*(bounds[3]-bounds[1])/(bounds[2]-bounds[0])))
    if height>maximum:
        width=max(1,round(width*maximum/height));height=maximum
    target=from_bounds(*bounds,width,height)
    view=np.full((height,width),np.nan,dtype="float64")
    reproject(values,view,src_transform=t,src_crs=result["crs"],src_nodata=np.nan,
        dst_transform=target,dst_crs="EPSG:3857",dst_nodata=np.nan,resampling=Resampling.nearest)
    aoim=project_geometry(aoi,4326,3857,.0005)
    inside=geometry_mask([mapping(aoim)],view.shape,target,invert=True)
    view[~inside]=np.nan
    image=rgba(view,legend)
    buf=io.BytesIO();Image.fromarray(image).save(buf,format="PNG",optimize=True)
    wgs=transform_bounds(3857,4326,*bounds)
    return dict(png=buf.getvalue(),image=image,bounds=[[wgs[1],wgs[0]],[wgs[3],wgs[2]]],extent=bounds,
                display_projection="EPSG:3857",display_resampling="nearest; visual AOI mask only",aoi=aoim)


def outline(ax,geometry):
    for polygon in geometry.geoms if geometry.geom_type=="MultiPolygon" else [geometry]:
        ax.plot(*polygon.exterior.xy,color="#102f26",linewidth=1.5)


def decorations(ax,aoi):
    ax.annotate("N",xy=(.96,.92),xytext=(.96,.8),xycoords="axes fraction",ha="center",fontweight="bold",
                arrowprops=dict(arrowstyle="-|>",color="#102f26"))
    xmin,xmax=ax.get_xlim();ymin,ymax=ax.get_ylim()
    latitude=aoi.centroid.y
    distance=1000/math.cos(math.radians(latitude))
    x=xmin+.06*(xmax-xmin);y=ymin+.07*(ymax-ymin)
    ax.plot([x,x+distance],[y,y],color="#102f26",linewidth=3)
    ax.text(x+distance/2,y+.02*(ymax-ymin),"1 km",ha="center",fontsize=9)
    ax.set_aspect("equal");ax.set_xticks([]);ax.set_yticks([]);ax.set_facecolor("#f1f4f1")


def static_map(path,layer,legend,display,aoi):
    entries=legend.get("entries",[])
    many=len(entries)>20
    fig=plt.figure(figsize=(18,12) if many else (14,9))
    ax=fig.add_axes([.04,.18,.40 if many else .52,.70])
    leg=fig.add_axes([.48 if many else .60,.16,.50 if many else .36,.73]);leg.axis("off")
    xmin,ymin,xmax,ymax=display["extent"]
    ax.imshow(display["image"],extent=[xmin,xmax,ymin,ymax],interpolation="nearest")
    outline(ax,display["aoi"])
    bx0,by0,bx1,by1=display["aoi"].bounds
    dx,dy=(bx1-bx0)*.12,(by1-by0)*.12
    ax.set_xlim(bx0-dx,bx1+dx);ax.set_ylim(by0-dy,by1+dy)
    decorations(ax,aoi)
    if legend["type"]=="categorical":
        handles=[Patch(facecolor=e["colour"],edgecolor="#aaa",label=textwrap.fill(f"{e['code']} · {e['caption']}"+(" [absent]" if not e.get('present') else ""),36 if many else 42)) for e in entries]
        handles.append(Patch(facecolor="none",edgecolor="#aaa",label="No data (transparent)"))
        leg.legend(handles=handles,loc="center left",frameon=False,fontsize=7.2 if many else 9,
                   ncols=2 if many else 1,columnspacing=1.5,
                   title=f"{legend['title']} ({legend['unit']})",labelspacing=.4)
    elif legend["type"]=="binned":
        leg.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(legend["colours"],legend["labels"])]+[Patch(facecolor="none",edgecolor="#aaa",label="No data (transparent)")],loc="center",frameon=False,title=layer["unit"])
    else:
        cb=fig.colorbar(matplotlib.cm.ScalarMappable(norm=Normalize(*legend["display_domain"]),cmap=legend.get("palette","viridis")),ax=leg,fraction=.35,shrink=.5)
        cb.set_label(layer["unit"])
        if legend.get("constant"):cb.set_ticks([legend["domain"][0]])
        leg.text(.1,.2,"No data: transparent\n"+legend["domain_method"],wrap=True,fontsize=9)
    fig.suptitle(layer["display_name"],fontsize=16,fontweight="bold",y=.95)
    note=f"{layer['attribution']} | Native resolution: {layer.get('native_resolution')} {layer.get('native_crs')} | Period: {layer.get('period') or 'see source metadata'}\n{layer['limitation']}\n{legend['palette_origin']} | Source: {layer['metadata_url']}"
    fig.text(.04,.035,textwrap.fill(note,180 if many else 150),fontsize=8,va="bottom")
    fig.savefig(path,dpi=140);plt.close(fig)


def aoi_map(path,aoi,area):
    fig,ax=plt.subplots(figsize=(9,8),layout="constrained")
    geom=project_geometry(aoi,4326,3857,.0005)
    outline(ax,geom);ax.fill(*geom.exterior.xy,color="#d9eee0")
    for i,(x,y) in enumerate(list(geom.exterior.coords)[:-1],1):ax.annotate(str(i),(x,y),xytext=(5,5),textcoords="offset points")
    decorations(ax,aoi);ax.set_title(f"Parcel A · {area:,.2f} ha\nEqual-area calculation; unchanged Stage 01 boundary")
    fig.savefig(path,dpi=140);plt.close(fig)


def static_chart(path,spec):
    fig,ax=plt.subplots(figsize=(10,5),layout="constrained")
    if spec["type"] in {"series","coverage"}:
        x=list(range(len(spec["data"])))
        y=[np.nan if r.get("value") is None else r["value"] for r in spec["data"]]
        ax.plot(x,y,"o-",color="#18734c")
        ax.set_xticks(x,[r["interval_start"][:7] for r in spec["data"]],rotation=45,ha="right")
    elif spec["type"]=="comparison":
        rows=spec["data"];x=list(range(len(rows)))
        ax.bar(x,[r["value"] for r in rows],color="#238568",alpha=.65)
        for i,r in enumerate(rows):
            for cell in r.get("cells",[]):ax.scatter(i,cell["value"],color="#182942",s=15)
        ax.set_xticks(x,[r["label"] for r in rows],rotation=15)
    else:
        rows=spec["data"];x=list(range(len(rows)))
        ax.bar(x,[r["value"] for r in rows],color=[r.get("colour","#238568") for r in rows])
        ax.set_xticks(x,[textwrap.fill(r["label"],18) for r in rows],rotation=20,ha="right")
    ax.set_title(spec["title"]);ax.set_ylabel(spec["unit"]);ax.grid(axis="y",alpha=.2)
    fig.supxlabel(textwrap.fill(spec.get("note",""),130),fontsize=8)
    fig.savefig(path,dpi=130);plt.close(fig)


def vector_map(path,layer,geojson,aoi):
    import geopandas as gpd
    frame=gpd.GeoDataFrame.from_features(geojson["features"],crs=4326).to_crs(3857)
    fig,ax=plt.subplots(figsize=(10,8),layout="constrained")
    frame.plot(ax=ax,color="#336eae",linewidth=1.5,markersize=18)
    outline(ax,project_geometry(aoi,4326,3857,.0005));decorations(ax,aoi)
    ax.legend(handles=[Patch(facecolor="#336eae",label="Clipped source features")],loc="lower right")
    ax.set_title(layer["display_name"])
    fig.supxlabel(textwrap.fill(layer["attribution"]+" | "+layer["limitation"],120),fontsize=8)
    fig.savefig(path,dpi=140);plt.close(fig)
