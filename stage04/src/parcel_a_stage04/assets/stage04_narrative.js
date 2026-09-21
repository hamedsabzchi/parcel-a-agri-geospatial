/* Plain-English descriptions of existing verified statistics; no new suitability scores. */
(function(root){
'use strict';
const fmt=(x,n=2)=>Number.isFinite(x)?x.toLocaleString('en',{minimumFractionDigits:n,maximumFractionDigits:n}):'not available';
const pct=x=>Number.isFinite(x)?(x>0&&x<.1?'<0.1%':fmt(x,1)+'%'):'not available';
const valid=p=>p?.status==='VERIFIED';
const coverage=p=>p?`${fmt(p.common_valid_area_ha)} ha (${pct(p.common_valid_percentage)} of the study area)`:'coverage unavailable';
const suitability=s=>!valid(s)?'Suitability evidence is unavailable for this selection.':s.dominant_class!==null?
  `“${s.dominant_class_label}” has the largest mapped share: ${pct(s.dominant_class_percentage)}.`:
  Object.values(s.modal_area_by_class||{}).some(v=>v>0)?'Several suitability classes tie for the largest mapped share. The map shows where each occurs.':
  'The five models give a tied class result in every mapped cell, so a single suitability class cannot be assigned.';

function suitabilityMap(s,metric){
 if(!valid(s))return 'No verified suitability map is available. Resolve the missing evidence before using this scenario for crop screening.';
 const notes={modal_class:suitability(s)+' A cell is coloured only when one class occurs more often than any other; a transparent cell can indicate a tie.',
  modal_count:'Each number shows how many of the five models share the most common class. A count of two can still be a tie.',
  full_agreement:`All five models choose the same class on ${pct(s.full_agreement_percentage)} of the mapped area.`,
  strong_agreement:`At least four of the five models choose the same class on ${pct(s.strong_agreement_percentage)} of the mapped area.`,
  majority_agreement:`Exactly three models choose the same class on ${pct(s.majority_agreement_percentage)} of the mapped area.`,
  unique_class_count:'Larger numbers mean that the five models return a wider variety of suitability classes for the same cell.',
  tie_flag:`There is no unique most common class on ${pct(s.tie_flag_percentage)} of the mapped area.`,
  tied_or_dispersed:`Fewer than three models share a class on ${pct(s.tied_or_dispersed_percentage)} of the mapped area.`};
 return `${notes[metric]||suitability(s)} Coverage: ${coverage(s)}. Use this regional pattern to target local soil and field checks.`;
}

function agreement(s){
 if(!valid(s))return 'Model agreement cannot be assessed without verified suitability evidence.';
 return `At least four models agree on ${pct(s.strong_agreement_percentage)} of the mapped area. The four segments are separate shares and total 100%. Agreement shows consistency within these five models; field suitability still needs checking.`;
}

function yieldMap(y,metric){
 if(!valid(y))return 'No verified yield map is available. Missing evidence has not been treated as zero yield.';
 const descriptions={model_mean:`The five models give an average of ${fmt(y.whole_aoi_mean)} kg dry weight/ha across the mapped area. Zero-yield cells are included.`,
  model_median:'Each cell shows the middle of its five modelled yield values.',model_minimum:'Each cell shows its lowest yield value among the five models.',
  model_maximum:'Each cell shows its highest yield value among the five models.',model_range:'Each cell shows the difference between its highest and lowest modelled yield. Larger values mean more model disagreement.',
  model_iqr:'Each cell shows the spread of the middle half of its five yield values; the lowest and highest values have less influence.',
  model_standard_deviation:'Each cell shows how far the five modelled yields spread around their mean, in kg dry weight/ha.',
  model_coefficient_of_variation:'Each cell shows model spread divided by mean yield (CV, a ratio). CV cannot be calculated when the mean is zero; those cells are transparent.'};
 return `${descriptions[metric]||descriptions.model_mean} Coverage: ${coverage(y)}. Use attainable yield to compare modelled conditions; local harvest performance requires field evidence.`;
}

function yieldArea(y){
 if(!valid(y))return 'No verified yield-area breakdown is available.';
 if(y.positive_yield_area_ha===0)return `All ${fmt(y.common_valid_area_ha)} mapped hectares have a valid five-model mean of zero. There is no positive-yield area to average. Investigate the source constraints before planning crop trials.`;
 return `${pct(y.positive_yield_percentage)} of mapped yield area has a five-model mean above zero; ${pct(y.valid_zero_percentage)} has a valid mean of zero. A positive mean can include zero values from some models and does not establish profitable farming.`;
}

function periods(records,kind,field,label,unit){
 const present=records.filter(r=>valid(r?.products[kind]?.summary)&&r.products[kind].summary[field]!=null);
 const quantity=(r)=>{const p=r.products[kind].summary,v=p[field];return field==='dominant_class'?p.dominant_class_label:unit.startsWith('%')?pct(v):fmt(v,field==='inter_model_cv'?3:2)+' '+unit;};
 if(!present.length)return `No verified ${label.toLowerCase()} values are available across these periods. Gaps are left visible.`;
 const first=present[0],last=present[present.length-1];
 const findings=present.length===1?`Only ${first.period_label} has an available value: ${quantity(first)}.`:
  `${first.period_label}: ${quantity(first)}. ${last.period_label}: ${quantity(last)}.`;
 return `${findings} The crop, climate pathway and farming system stay fixed. Each bar represents a 20-year period with its own coverage, so use this comparison to identify periods that need closer investigation. Missing periods are gaps; no annual trend or percentage change is inferred.`;
}

function management(records){
 const names=['Rainfed','Irrigated'];
 const findings=records.map((r,i)=>{const y=r?.products.yield?.summary;return valid(y)?`${names[i]}: ${fmt(y.whole_aoi_mean)} kg dry weight/ha over ${pct(y.common_valid_percentage)} of the area.`:`${names[i]} yield evidence is unavailable.`;}).join(' ');
 return findings+' Both cases use the same crop, period and climate pathway, but can cover different cells. Check dependable water supply, water quality, infrastructure and costs before using the irrigated case in project planning.';
}

function decisions(r){
 const s=r?.products.suitability?.summary,y=r?.products.yield?.summary;
 const checks=[];
 if(!valid(s)||!valid(y))checks.push({title:'Complete the evidence',text:'Resolve the missing '+[!valid(s)?'suitability':null,!valid(y)?'yield':null].filter(Boolean).join(' and ')+' evidence before assessing this scenario as a whole.'});
 else checks.push({title:'Check the crop locally',text:suitability(s)+' Compare this pattern with local soils, drainage and crop performance before selecting field trials.'});
 const partial=[['Suitability',s],['Yield',y]].filter(([,p])=>valid(p)&&p.common_valid_percentage<99.99);
 if(partial.length)checks.push({title:'Check the uncovered area',text:partial.map(([label,p])=>label+' covers '+pct(p.common_valid_percentage)+' of the AOI.').join(' ')+' Obtain evidence for the remaining area before extending these conclusions to the whole site.'});
 else if(valid(s)&&s.tied_or_dispersed_percentage>0)checks.push({title:'Investigate model disagreement',text:`The suitability models split on ${pct(s.tied_or_dispersed_percentage)} of mapped area. Compare the class and agreement maps and check local constraints where the models differ.`});
 else checks.push({title:'Check different futures',text:'Repeat the comparison for the other available periods and climate pathways. A result in one scenario does not establish how the crop performs in every future.'});
 if(valid(y)&&y.valid_zero_area_ha>0)checks.push({title:'Investigate zero-yield cells',text:`${fmt(y.valid_zero_area_ha)} ha have a valid mean yield of zero. Examine the documented source constraints and local evidence before planning crop trials there.`});
 checks.push({title:r?.management_code==='HILM'?'Check the irrigation assumptions':'Check the water assumptions',text:r?.management_code==='HILM'?'Verify seasonal water availability, water quality, delivery infrastructure and costs. The irrigated model case does not establish that these requirements can be met.':'Check rainfall timing, dry-season water balance and soil water storage. If irrigation is being considered, assess its water supply and costs separately.'});
 return checks;
}
const api={fmt,pct,coverage,suitability,suitabilityMap,agreement,yieldMap,yieldArea,periods,management,decisions};
if(typeof module==='object'&&module.exports)module.exports=api;else root.ParcelAStage04Narrative=api;
})(typeof window==='object'?window:globalThis);
