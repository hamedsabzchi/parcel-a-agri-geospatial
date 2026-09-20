from __future__ import annotations
import json
from pathlib import Path
from .common import clean


def write_dashboard(path,data,maximum):
    assets=Path(__file__).parent/"assets"
    html=(assets/"dashboard.html").read_text()
    for key,name in [("__LEAFLET_CSS__","leaflet.css"),("__LEAFLET_JS__","leaflet.js"),("__DASHBOARD_JS__","dashboard.js")]:
        text=(assets/name).read_text()
        if name=="leaflet.js":text=text.split("//# sourceMappingURL=")[0]
        if name=="dashboard.js":text=text.replace("__MAIZE_UI__",(assets/"maize.js").read_text())
        html=html.replace(key,text)
    payload=json.dumps(clean(data),ensure_ascii=False,allow_nan=False,separators=(",",":")).replace("<","\\u003c").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
    html=html.replace("__DATA__",payload)
    if len(html.encode())>maximum:raise ValueError("Offline dashboard exceeds its configured size budget")
    Path(path).write_text(html,encoding="utf-8")
