// Available, verified map records drive all selectors. No invented source layer.
const maizeKeys=['map_code','period_code','ssp_code','climate_model_code','management_code','view'];
const maizeLabels={map_code:'Product',period_code:'Period',ssp_code:'Scenario',climate_model_code:'Model',management_code:'Management',view:'View'};
const maizeNames={HP0120:'2001–2020',FP2140:'2021–2040',FP4160:'2041–2060',FP6180:'2061–2080',FP8100:'2081–2100',SSP126:'SSP1-2.6',SSP370:'SSP3-7.0',SSP585:'SSP5-8.5',HIST:'Historical',HRLM:'Rainfed · high input',HILM:'Irrigated · high input',LRLM:'Rainfed · low input',LILM:'Irrigated · low input',source:'Source layer',FIVE_MODELS:'Five-model derived',ENSEMBLE:'FAO ENSEMBLE · diagnostic','RES05-SXX30AS':'Continuous suitability · ~1 km','RES05-SIX':'Suitability classes · ~10 km','RES05-YXX':'Attainable yield · ~10 km'};
function maizeValue(record,key){const m=record.metadata;if(m[key])return m[key];if(!['RES05-SIX','RES05-YXX'].includes(record.comparison_group))return '';return {map_code:record.comparison_group,period_code:'HP0120',ssp_code:'HIST',climate_model_code:'AGERA5',management_code:m.management_code,view:'source'}[key]||'';}
function maizeMatches(record,except){return maizeKeys.every(k=>k===except||!el('maize-'+k)?.value||maizeValue(record,k)===el('maize-'+k).value);}
function refreshMaize(changed){
 for(const key of maizeKeys){const select=el('maize-'+key),old=select.value;const values=[...new Set(D.maps.filter(m=>maizeMatches(m,key)).map(m=>maizeValue(m,key)).filter(Boolean))].sort();select.replaceChildren(option('','All '+maizeLabels[key].toLowerCase()+'s'),...values.map(v=>option(v,maizeNames[v]||v.replaceAll('_',' '))));select.value=values.includes(old)?old:'';}
 const records=D.maps.filter(m=>maizeMatches(m)),ids=new Set(records.map(m=>m.layer_id));
 document.querySelectorAll('[data-layer]').forEach(c=>{c.closest('label').hidden=!ids.has(c.dataset.layer);if(!ids.has(c.dataset.layer)&&overlays[c.dataset.layer]){mainMap.removeLayer(overlays[c.dataset.layer]);delete overlays[c.dataset.layer];c.checked=false;}});
 el('layer-list').querySelectorAll('details').forEach(detail=>{detail.hidden=![...detail.querySelectorAll('.layer-check')].some(n=>!n.hidden);});
 const current=el('active-layer').value;el('active-layer').replaceChildren(...records.map(m=>option(m.layer_id,m.title)));el('active-layer').value=ids.has(current)?current:records[0]?.layer_id||'';
 el('maize-filter-count').textContent=`${records.length} available maps. Clear filters to see all original Stage 03 layers.`;
 if(mainMap){if(records.length)activate(el('active-layer').value);comparisonOptions();}
}
function maizeLinks(record){
 const holder=el('layer-downloads');const table=(record.table_ids||[]).find(x=>x.startsWith('maize_model'))||(record.table_ids||[])[0];const chartId=(record.chart_ids||[])[0];
 if(table){const b=document.createElement('button');b.textContent='Related table';b.onclick=()=>{document.querySelector('[data-tab="tables"]').click();el('table-select').value=table;el('search').value=record.metadata.group_id||record.metadata.original_layer_id||record.layer_id;resetTable();};holder.append(b);}
 if(chartId){const b=document.createElement('button');b.textContent='Related graph';b.onclick=()=>{el('chart-select').value=chartId;document.querySelector('[data-tab="graphs"]').click();};holder.append(b);}
 if(record.metadata.analytical_geometry_path)holder.insertAdjacentHTML('beforeend',safeLink('../'+record.metadata.analytical_geometry_path,'Exact support GeoJSON'));
}
if(D.maize){
 const summary=D.maize.summary;el('maize-overview').hidden=false;el('maize-overview').innerHTML=`<div class="panel"><h2>Maize suitability and climate scenarios</h2><div class="cards"><div class="card"><strong>${summary.available_layers}/${summary.planned_assets}</strong><span>Supplemental maps with AOI data</span></div><div class="card"><strong>${summary.verified_assets}/${summary.planned_assets}</strong><span>Sources checked successfully</span></div><div class="card"><strong>${summary.groups_with_common_support}/${summary.planned_five_model_groups}</strong><span>Five-model groups with shared data</span></div><div class="card"><strong>16/16</strong><span>Original required GAEZ layers retained</span></div></div><p>${esc(D.maize.note)}</p><p class="warning">Future continuous suitability at ~1 km: no verified public source in the supplied inventory. It remains blocked. Future ~10 km suitability classes and yield are separate products.</p><p>${summary.empty_or_outside_layers} sources have no valid AOI coverage; ${summary.failed_layers} checks failed. See Tables for the exact records.</p><button id="maize-start">Explore maps</button></div>`;
 el('maize-start').onclick=()=>document.querySelector('[data-tab="maps"]').click();
 el('maize-filters').hidden=false;
 for(const key of maizeKeys){const label=document.createElement('label');label.textContent=maizeLabels[key]+' ';const select=document.createElement('select');select.id='maize-'+key;select.setAttribute('aria-label',maizeLabels[key]);label.append(select);el('maize-filter-controls').append(label);select.append(option('','All'));select.onchange=()=>refreshMaize(key);}
 const reset=document.createElement('button');reset.textContent='Clear filters';reset.onclick=()=>{maizeKeys.forEach(k=>el('maize-'+k).value='');refreshMaize();};el('maize-filter-controls').append(reset);
 if(D.maps.some(m=>m.comparison_group==='RES05-SXX30AS')){el('comparison-group').append(option('RES05-SXX30AS','Historical continuous suitability'));el('comparison-group').append(option('SIX_AND_SXX','Classes and continuous index · different products'));}
 el('method-links').insertAdjacentHTML('beforeend',safeLink('../metadata/maize/methodology.md','Maize methods')+safeLink('../metadata/maize/requirements_traceability.md','Guideline coverage')+safeLink('../qa/maize_validation_report.json','Maize quality checks'));
 refreshMaize();
}
