"use strict";
const D=JSON.parse(document.getElementById('dashboard-data').textContent);
const el=id=>document.getElementById(id), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=x=>x===null||x===undefined?'No data':Number(x).toLocaleString(undefined,{maximumFractionDigits:2});
const mapById=Object.fromEntries(D.maps.map(x=>[x.layer_id,x]));
let mainMap=null,leftMap=null,rightMap=null,active=null,overlays={},baseLayers={},compareOverlays={},sync=false;
function option(value,text){const o=document.createElement('option');o.value=value;o.textContent=text;return o;}
function safeLink(path,label){return `<a class="link-button" href="${esc(path)}" download>${esc(label)}</a>`;}
function boundary(map){L.geoJSON(D.aoi,{style:{color:'#174c32',weight:3,fillOpacity:0}}).addTo(map);}
function makeMap(id){const m=L.map(id,{preferCanvas:true,attributionControl:true}).fitBounds(D.bounds);L.control.scale({imperial:false}).addTo(m);boundary(m);return m;}
const overviewMap=makeMap('overview-map');
const vertices=D.aoi.features[0].geometry.coordinates[0];
vertices.slice(0,-1).forEach((p,i)=>L.circleMarker([p[1],p[0]],{radius:4,color:'#1b7248'}).bindTooltip(`Point ${i+1} · X ${p[0].toFixed(6)}, Y ${p[1].toFixed(6)} (WGS84)`).addTo(overviewMap));
el('cards').innerHTML=[[number(D.summary.aoi_area_ha),'AOI area · ha'],[D.summary.source_count,'Sources retained'],[D.summary.extracted_layer_count,'Layers extracted'],[`${D.summary.gaez_extracted}/16`,'GAEZ layers extracted']].map(x=>`<div class="card"><strong>${esc(x[0])}</strong><span>${esc(x[1])}</span></div>`).join('');
el('outcome').textContent=D.summary.outcome.replaceAll('_',' ');
el('availability').textContent=`${D.summary.extracted_source_count} sources produced data. Other sources remain visible with their status and next action in Tables.`;
el('count-details').textContent=JSON.stringify(D.summary,null,2);
el('provenance').textContent=JSON.stringify(D.methods,null,2);
el('gaps').innerHTML=D.summary.gaps.length?`<details><summary>${D.summary.gaps.length} selected layers need attention</summary><ul>${D.summary.gaps.map(x=>`<li>${esc(x.layer_id)}: ${esc(x.reason)}</li>`).join('')}</ul></details>`:'';
const groups=[...new Set(D.maps.map(x=>x.group))];
el('layer-list').innerHTML=groups.map(g=>`<details open><summary>${esc(g)}</summary>${D.maps.filter(x=>x.group===g).map(x=>`<label class="layer-check"><input type="checkbox" data-layer="${esc(x.layer_id)}">${esc(x.title)}</label>`).join('')}</details>`).join('');
D.maps.forEach(x=>el('active-layer').append(option(x.layer_id,x.title)));
function legendHTML(legend){if(!legend)return 'Legend unavailable';let s=`<strong>${esc(legend.title)}</strong><div class="muted">${esc(legend.unit)}</div>`;
 if(legend.type==='categorical'){const rows=e=>`<div class="legend-row ${e.present?'':'absent'}"><span class="swatch" style="background:${e.colour}"></span><span>${esc(e.code)} · ${esc(e.caption)}${e.present?'':' · absent'}</span></div>`;s+=legend.entries.filter(x=>x.present).map(rows).join('');s+=`<details><summary>Full source legend (${legend.entries.length} classes)</summary>${legend.entries.map(rows).join('')}</details>`;}
 else if(legend.type==='binned'){s+=legend.labels.map((x,i)=>`<div class="legend-row"><span class="swatch" style="background:${legend.colours[i]}"></span>${esc(x)}</div>`).join('');}
 else{s+=legend.constant?`<p>Single value: ${number(legend.domain[0])}</p>`:`<div class="gradient"></div><div class="domain"><span>${number(legend.domain[0])}</span><span>${number(legend.domain[1])}</span></div>`;s+=`<small>${esc(legend.domain_method)}</small>`;}
 return s+`<div class="legend-row"><span class="swatch"></span>No data · transparent</div><small>${esc(legend.palette_origin)}</small>`;}
function layerGroup(record,map,opacity=.85){const group=L.layerGroup();if(record.type==='vector'){L.geoJSON(record.geojson,{style:{color:'#336eae',weight:2,fillOpacity:.3},pointToLayer:(f,p)=>L.circleMarker(p,{radius:4,color:'#336eae'}),onEachFeature:(f,l)=>l.bindPopup('<pre>'+esc(JSON.stringify(f.properties,null,2))+'</pre>')}).addTo(group);return group.addTo(map);}L.imageOverlay(record.image,record.bounds,{opacity,zIndex:record.z_index,attribution:record.attribution}).addTo(group);
 if(record.cells?.length){L.geoJSON({type:'FeatureCollection',features:record.cells},{style:{color:'#345446',weight:.8,fillOpacity:0,opacity:.5},onEachFeature:(f,l)=>{const p=f.properties;l.bindPopup(`<b>${esc(record.title)}</b><br>Native value: ${number(p.value)} ${esc(p.unit)}<br>Valid: ${p.valid?'yes':'no'}<br>AOI intersection: ${number(p.intersection_area_ha)} ha<br><small>${esc(p.cell_id)}</small>`);}}).addTo(group);}return group.addTo(map);}
function activate(id){active=mapById[id];if(!active)return;el('active-layer').value=id;el('active-legend').innerHTML=legendHTML(active.legend);el('map-note').textContent=active.metadata.limitation;
 el('layer-downloads').innerHTML=safeLink(active.download_path,'Native data')+safeLink(active.static_map_path,'Map PNG');
 const fields={Source:active.metadata.source_id,Variable:active.metadata.variable,Period:active.metadata.period||[active.metadata.period_start,active.metadata.period_end].filter(Boolean).join(' to ')||'See source metadata',Unit:active.metadata.unit,'Native grid':`${active.metadata.native_crs} · ${JSON.stringify(active.metadata.native_resolution)}`,Processing:active.metadata.processing,Mask:active.metadata.mask_rule,'Stage 02':active.metadata.stage02_status,'Stage 03':active.metadata.extraction_status,Model:active.metadata.climate_model_code,Scenario:active.metadata.ssp_code,Management:active.metadata.management_code,View:active.metadata.view,'Valid native cells':active.metadata.valid_native_cell_count,'True minimum':active.metadata.minimum,'True maximum':active.metadata.maximum,'Common valid area (ha)':active.metadata.common_valid_area_ha,'Quality flag':active.metadata.quality_flag,Licence:active.metadata.licence,'Valid AOI area':number(active.metadata.valid_area_percentage)+'%'};
 el('layer-details').innerHTML=Object.entries(fields).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
 if(D.maize)maizeLinks(active);
 if(mainMap&&!overlays[id]){overlays[id]=layerGroup(active,mainMap,Number(el('opacity').value));const check=document.querySelector(`[data-layer="${CSS.escape(id)}"]`);if(check)check.checked=true;}
 if(overlays[id])overlays[id].eachLayer(l=>{if(l.setZIndex)l.setZIndex(999);});}
function initMaps(){if(mainMap){[mainMap,leftMap,rightMap].forEach(m=>m.invalidateSize());return;}mainMap=makeMap('main-map');leftMap=makeMap('left-map');rightMap=makeMap('right-map');
 mainMap.on('mousemove',e=>{el('coordinates').textContent=`Longitude ${e.latlng.lng.toFixed(6)} · Latitude ${e.latlng.lat.toFixed(6)} · WGS84`;});
 [leftMap,rightMap].forEach((m,i)=>m.on('moveend',()=>{if(sync)return;const target=i?leftMap:rightMap;if(target.getCenter().equals(m.getCenter(),1e-7)&&target.getZoom()===m.getZoom())return;sync=true;target.setView(m.getCenter(),m.getZoom(),{animate:false});sync=false;}));
 activate(D.maps[0]?.layer_id);comparisonOptions();}
document.querySelectorAll('[data-layer]').forEach(c=>c.addEventListener('change',()=>{const id=c.dataset.layer;if(c.checked){if(!overlays[id])overlays[id]=layerGroup(mapById[id],mainMap);activate(id);}else if(overlays[id]){mainMap.removeLayer(overlays[id]);delete overlays[id];}}));
el('active-layer').addEventListener('change',e=>activate(e.target.value));
el('opacity').addEventListener('input',e=>{if(overlays[active?.layer_id])overlays[active.layer_id].eachLayer(l=>{if(l.setOpacity)l.setOpacity(Number(e.target.value));});});
el('background').addEventListener('change',e=>{Object.values(baseLayers).forEach(l=>mainMap.removeLayer(l));baseLayers={};const choice=e.target.value;if(choice==='blank')return;
 const url=choice==='light'?'https://tile.openstreetmap.org/{z}/{x}/{y}.png':'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
 baseLayers[choice]=L.tileLayer(url,{attribution:choice==='light'?'© OpenStreetMap contributors':'Tiles © Esri and imagery providers',maxZoom:20}).addTo(mainMap);baseLayers[choice].on('tileerror',()=>{el('coordinates').textContent='Background unavailable offline. Thematic layers remain available.';});});
el('reset-map').onclick=()=>mainMap.fitBounds(D.bounds);el('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else el('main-map').requestFullscreen?.();};
function comparisonOptions(){const group=el('comparison-group').value;const records=D.maps.filter(x=>(group==='SIX_AND_SXX'?['RES05-SIX','RES05-SXX30AS'].includes(x.comparison_group):x.comparison_group===group)&&(!D.maize||maizeMatches(x)));['left','right'].forEach((side,i)=>{const s=el('compare-'+side);s.replaceChildren(...records.map(x=>option(x.layer_id,x.title)));if(records.length)s.value=records[Math.min(i,records.length-1)].layer_id;drawComparison(side);});}
function drawComparison(side){const id=el('compare-'+side).value,record=mapById[id],map=side==='left'?leftMap:rightMap;if(compareOverlays[side])map.removeLayer(compareOverlays[side]);if(!record)return;compareOverlays[side]=layerGroup(record,map);el(side+'-support').textContent=`Valid AOI support: ${number(record.metadata.valid_area_percentage)}% · ${record.metadata.valid_native_cell_count} distinct cells`;el(side+'-legend').innerHTML=legendHTML(record.legend);el('compare-legend').textContent=el('comparison-group').value==='SIX_AND_SXX'?'These are different products and resolutions. No class conversion or difference is implied.':'';}
el('comparison-group').onchange=comparisonOptions;['left','right'].forEach(side=>el('compare-'+side).onchange=()=>drawComparison(side));
let page=0,sortKey=null,ascending=true,filtered=[];
D.tables.forEach(t=>el('table-select').append(option(t.id,t.title)));
function currentTable(){return D.tables.find(t=>t.id===el('table-select').value)||D.tables[0];}
function drawTable(){const t=currentTable(),search=el('search').value.toLowerCase(),status=el('table-filter').value;
 filtered=t.rows.filter(r=>(!search||Object.values(r).some(v=>String(v??'').toLowerCase().includes(search)))&&(!status||Object.values(r).includes(status)));
 if(sortKey)filtered.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??'')))*(ascending?1:-1);});
 const cols=t.columns||Object.keys(t.rows[0]||{});page=Math.max(0,Math.min(page,Math.ceil(filtered.length/20)-1));
 el('table-head').innerHTML='<tr>'+cols.map(c=>`<th scope="col" tabindex="0" data-column="${esc(c)}">${esc(c.replaceAll('_',' '))}${c===sortKey?(ascending?' ↑':' ↓'):''}</th>`).join('')+'</tr>';
 el('table-body').innerHTML=filtered.slice(page*20,page*20+20).map(r=>'<tr>'+cols.map(c=>`<td>${esc(r[c]===null?'':typeof r[c]==='object'?JSON.stringify(r[c]):r[c])}</td>`).join('')+'</tr>').join('')||`<tr><td colspan="${cols.length||1}">No matching records.</td></tr>`;
 el('page-info').textContent=`${filtered.length} records · page ${page+1} of ${Math.max(1,Math.ceil(filtered.length/20))}`;el('previous').disabled=page===0;el('next').disabled=(page+1)*20>=filtered.length;
 document.querySelectorAll('[data-column]').forEach(h=>{const sort=()=>{ascending=sortKey===h.dataset.column?!ascending:true;sortKey=h.dataset.column;drawTable();};h.onclick=sort;h.onkeydown=e=>{if(e.key==='Enter')sort();};});}
function resetTable(){page=0;sortKey=null;const states=[...new Set(currentTable().rows.flatMap(r=>[r.stage03_disposition,r.extraction_status,r.quality_flag,r.verification_status,r.availability_status]).filter(Boolean))];el('table-filter').replaceChildren(option('','All statuses'),...states.map(x=>option(x,x.replaceAll('_',' '))));drawTable();}
el('table-select').onchange=resetTable;el('search').oninput=()=>{page=0;drawTable();};el('table-filter').onchange=()=>{page=0;drawTable();};el('previous').onclick=()=>{page--;drawTable();};el('next').onclick=()=>{page++;drawTable();};
function saveBlob(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
el('export-csv').onclick=()=>{const cols=currentTable().columns||Object.keys(filtered[0]||{}),quote=x=>'"'+String(x??'').replaceAll('"','""')+'"';const csv=[cols,...filtered.map(r=>cols.map(c=>typeof r[c]==='object'&&r[c]!==null?JSON.stringify(r[c]):r[c]))].map(row=>row.map(quote).join(',')).join('\r\n');saveBlob(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}),currentTable().id+'.csv');};
D.charts.forEach(c=>el('chart-select').append(option(c.id,c.title)));
function drawChart(){const c=D.charts.find(x=>x.id===el('chart-select').value)||D.charts[0];if(!c){el('chart-space').textContent='No accepted chart data.';return;}
 const rows=c.data,W=1000,H=480,left=85,right=35,top=45,bottom=125,w=W-left-right,h=H-top-bottom;
 let values=rows.map(r=>r.value).filter(v=>v!==null&&Number.isFinite(v));let lo=Math.min(0,...values),hi=Math.max(0,...values);if(c.type==='coverage'){lo=0;hi=100;}if(lo===hi){lo-=.5;hi+=.5;}
 const y=v=>top+(hi-v)/(hi-lo)*h,x=i=>left+(i+.5)*w/Math.max(1,rows.length);let svg=`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.title)}"><text x="${left}" y="22" font-weight="bold">${esc(c.title)}</text>`;
 for(let i=0;i<=5;i++){const v=lo+(hi-lo)*i/5;svg+=`<line x1="${left}" y1="${y(v)}" x2="${W-right}" y2="${y(v)}" stroke="#e1e8e2"/><text x="${left-10}" y="${y(v)+4}" text-anchor="end">${number(v)}</text>`;}
 svg+=`<text x="15" y="${top+h/2}" transform="rotate(-90 15 ${top+h/2})" text-anchor="middle">${esc(c.unit)}</text>`;
 if(c.type==='series'||c.type==='coverage'){let previous=null;rows.forEach((r,i)=>{if(r.value===null){previous=null;return;}if(previous!==null)svg+=`<line x1="${x(previous)}" y1="${y(rows[previous].value)}" x2="${x(i)}" y2="${y(r.value)}" stroke="#19764f" stroke-width="2"/>`;svg+=`<circle data-tip="${esc(JSON.stringify(r))}" cx="${x(i)}" cy="${y(r.value)}" r="5" fill="#19764f"><title>${esc(JSON.stringify(r))}</title></circle>`;previous=i;});}
 else{rows.forEach((r,i)=>{if(r.value===null)return;const width=Math.min(70,w/rows.length*.65);svg+=`<rect data-tip="${esc(JSON.stringify(r))}" x="${x(i)-width/2}" y="${Math.min(y(r.value),y(0))}" width="${width}" height="${Math.abs(y(r.value)-y(0))}" fill="${r.colour||'#278362'}"><title>${esc(JSON.stringify(r))}</title></rect>`;(r.cells||[]).forEach(cell=>{svg+=`<circle cx="${x(i)}" cy="${y(cell.value)}" r="4" fill="#162b45"><title>Native cell ${esc(cell.cell_id)}: ${number(cell.value)}; AOI intersection ${number(cell.intersection_area_ha)} ha</title></circle>`;});});}
 rows.forEach((r,i)=>{const label=r.label||r.interval_start?.slice(0,7)||'';svg+=`<text x="${x(i)}" y="${H-bottom+22}" transform="rotate(30 ${x(i)} ${H-bottom+22})" text-anchor="start">${esc(label)}</text>`;});svg+='</svg>';el('chart-space').innerHTML=svg;el('chart-note').textContent=c.note;el('chart-downloads').innerHTML=safeLink(c.path,'Chart PNG')+safeLink(c.table_path,'Underlying CSV');
 document.querySelectorAll('[data-tip]').forEach(n=>n.onmouseenter=()=>{el('chart-tip').textContent=n.dataset.tip;});}
el('chart-select').onchange=drawChart;
el('method-links').innerHTML=safeLink('../README.txt','How to use')+safeLink('../metadata/methodology.md','Methods')+safeLink('../metadata/provenance.json','Provenance')+safeLink('../qa/stage03_validation_report.json','Quality checks');
el('licences').innerHTML=D.layers.map(l=>`<p><strong>${esc(l.display_name)}</strong><br>${esc(l.licence)}<br>${esc(l.limitation)}</p>`).join('');
el('all-downloads').innerHTML=D.downloads.map(d=>safeLink(d.path,d.title)).join('');
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.setAttribute('aria-selected',x===b?'true':'false'));document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab));if(b.dataset.tab==='maps')initMaps();if(b.dataset.tab==='overview')overviewMap.invalidateSize();if(b.dataset.tab==='graphs')drawChart();});
__MAIZE_UI__
resetTable();window.stage03Ready=true;
