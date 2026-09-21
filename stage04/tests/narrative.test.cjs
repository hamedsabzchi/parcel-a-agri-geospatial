// Synthetic wording cases: these values are test inputs, never project results.
const test=require('node:test'),assert=require('node:assert/strict');
const n=require('../src/parcel_a_stage04/assets/stage04_narrative.js');
const suit={status:'VERIFIED',dominant_class:null,dominant_class_label:'No unique class',common_valid_area_ha:100,common_valid_percentage:80,
 modal_area_by_class:{1:50,2:50},strong_agreement_percentage:100,full_agreement_percentage:100,majority_agreement_percentage:0,tied_or_dispersed_percentage:0,tie_flag_percentage:0};
const yieldValue={status:'VERIFIED',common_valid_area_ha:75,common_valid_percentage:60,whole_aoi_mean:50,positive_yield_area_ha:50,positive_yield_percentage:200/3,valid_zero_area_ha:25,valid_zero_percentage:100/3};
const record=(period,summary=yieldValue)=>({period_label:period,management_code:'HILM',products:{suitability:{summary:suit},yield:{summary}}});

test('An AOI class-area tie is not misdescribed as model disagreement',()=>{
 assert.match(n.suitability(suit),/classes tie for the largest mapped share/);
 assert.doesNotMatch(n.suitability(suit),/models give a tied/);
 assert.match(n.agreement(suit),/100.0%/);
 assert.match(n.suitability({...suit,modal_area_by_class:{1:0,2:0}}),/tied class result in every mapped cell/);
});
test('Yield captions retain units, coverage and the zero-versus-missing distinction',()=>{
 assert.match(n.yieldMap(yieldValue,'model_mean'),/50.00 kg dry weight\/ha/);
 assert.match(n.yieldMap(yieldValue,'model_mean'),/75.00 ha \(60.0%/);
 assert.match(n.yieldArea(yieldValue),/66.7%/);
 assert.match(n.yieldArea(yieldValue),/zero values from some models/);
 const zero={...yieldValue,whole_aoi_mean:0,positive_yield_area_ha:0,positive_yield_percentage:0,valid_zero_area_ha:75,valid_zero_percentage:100};
 assert.match(n.yieldArea(zero),/All 75.00 mapped hectares.*zero/);
 assert.match(n.yieldMap(zero,'model_coefficient_of_variation'),/cannot be calculated when the mean is zero/);
 assert.match(n.yieldMap(null,'model_mean'),/Missing evidence has not been treated as zero/);
});
test('Period captions give values and preserve coverage caveats and gaps',()=>{
 const text=n.periods([record('2021–2040'),null,record('2081–2100',{...yieldValue,whole_aoi_mean:90,common_valid_area_ha:100})],'yield','whole_aoi_mean','Modelled yield','kg dry weight/ha');
 assert.match(text,/2021–2040: 50.00/);assert.match(text,/2081–2100: 90.00/);
 assert.match(text,/own coverage/);assert.match(text,/Missing periods are gaps/);
 assert.doesNotMatch(text,/increased|decreased|benefit|higher by/);
 assert.match(n.periods([null,record('2021–2040')],'yield','whole_aoi_mean','Modelled yield','kg dry weight/ha'),/Only 2021–2040/);
});
test('Management captions do not fabricate the absent management or estimate benefits',()=>{
 const text=n.management([record('2021–2040'),undefined]);
 assert.match(text,/Rainfed: 50.00 kg dry weight\/ha/);assert.match(text,/Irrigated yield evidence is unavailable/);
 assert.match(text,/can cover different cells/);assert.match(text,/water supply/);
 assert.doesNotMatch(text,/recommended|best|increase of/);
});
test('Follow-up checks respond to missing coverage, zeros and selected farming system',()=>{
 const checks=n.decisions(record('2021–2040'));
 assert.ok(checks.some(c=>c.title==='Check the uncovered area'));
 assert.ok(checks.some(c=>c.title==='Investigate zero-yield cells'&&c.text.includes('25.00 ha')));
 assert.ok(checks.some(c=>c.title==='Check the irrigation assumptions'));
 assert.ok(n.decisions(null).some(c=>c.title==='Complete the evidence'));
 assert.match(n.suitability(null),/unavailable/);
});
