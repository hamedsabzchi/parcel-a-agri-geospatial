"""Real offline file:// regression checks for the original and extended dashboard."""
import os
from pathlib import Path
from .common import now


def inspect(path,stage04=False):
    from playwright.sync_api import sync_playwright
    errors=[];requests=[];checks={};screens=[]
    with sync_playwright() as p:
        kwargs={'args':['--no-sandbox']}
        if os.getenv('CHROMIUM_EXECUTABLE'):kwargs['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
        browser=p.chromium.launch(**kwargs)
        context=browser.new_context(offline=True,accept_downloads=True,viewport={'width':1440,'height':1000})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('requestfailed',lambda r:requests.append(r.url))
        page.goto(Path(path).resolve().as_uri(),timeout=90000);page.wait_for_function('window.stage03Ready===true',timeout=90000)
        original=['overview','maps','tables','graphs','methods']
        for tab in original:
            page.locator('[data-tab="'+tab+'"]').click();checks['tab_'+tab]=page.locator('#'+tab).is_visible()
        checks['all_original_map_controls']=page.evaluate('''()=>{document.querySelector('[data-tab="maps"]').click();for(const record of D.maps){activate(record.layer_id);if(!document.getElementById('layer-downloads').textContent.includes('Native data'))return false;if(overlays[record.layer_id]){mainMap.removeLayer(overlays[record.layer_id]);delete overlays[record.layer_id];}const check=document.querySelector('[data-layer="'+CSS.escape(record.layer_id)+'"]');if(check)check.checked=false;}return true;}''')
        checks['all_original_tables']=page.evaluate('''()=>{for(const t of D.tables){document.getElementById('table-select').value=t.id;resetTable();if(!document.getElementById('page-info').textContent.includes('records'))return false;}return true;}''')
        checks['all_original_graphs']=page.evaluate('''()=>{for(const c of D.charts){document.getElementById('chart-select').value=c.id;drawChart();if(!document.querySelector('#chart-space svg'))return false;}return true;}''')
        page.locator('[data-tab="maps"]').click();page.locator('#active-layer').select_option(index=0)
        page.locator('#opacity').evaluate("n=>{n.value='0.4';n.dispatchEvent(new Event('input'));}")
        checks['opacity_control']=page.evaluate("Object.values(overlays).some(g=>g.getLayers().some(l=>l.options.opacity===0.4))")
        page.locator('#reset-map').click();checks['aoi_zoom']=page.evaluate('mainMap.getBounds().contains(L.latLngBounds(D.bounds))')
        groups=page.locator('#comparison-group option').evaluate_all('xs=>xs.map(x=>x.value)')
        for g in groups:
            page.locator('#comparison-group').select_option(g)
            checks['comparison_'+g]=page.locator('#compare-left option').count()>0 and page.locator('#compare-right option').count()>0
            for side in ['left','right']:
                if page.locator('#compare-'+side+' option').count():page.locator('#compare-'+side).select_option(index=0)
            checks['comparison_legends_'+g]=bool(page.locator('#left-legend').inner_text()) and bool(page.locator('#right-legend').inner_text())
        page.locator('[data-tab="tables"]').click()
        with page.expect_download() as download:page.locator('#export-csv').click()
        checks['original_table_download']=download.value.suggested_filename.endswith('.csv')
        if stage04:
            page.locator('#stage04-tab').click();page.wait_for_function('window.ParcelAStage04?.ready===true')
            checks['one_stage04_tab']=page.locator('#stage04-tab').count()==1
            keys=page.evaluate('ParcelAStage04.data.scenarios.map(r=>r.key)')
            for key in keys:
                page.evaluate('(key)=>ParcelAStage04.selectKey(key)',key)
                if page.locator('#s4-status').inner_text().find('undefined')>=0:errors.append('Undefined selection')
                for ident in ['s4-suit-diagnostic','s4-yield-diagnostic']:
                    for value in page.locator('#'+ident+' option').evaluate_all('xs=>xs.filter(x=>!x.disabled).map(x=>x.value)'):
                        page.locator('#'+ident).select_option(value)
            checks['all_verified_selections_and_diagnostics']=not errors and page.evaluate('ParcelAStage04.state.errors.length===0')
            if keys:
                page.locator('#s4-current-only').check()
                checks['selected_table_filter']=page.locator('#s4-scenarios tbody tr').count()==1
                page.locator('#s4-current-only').uncheck()
                page.locator('#s4-search').fill('NO_MATCH_EXPECTED')
                checks['table_search']=page.locator('#s4-scenarios tbody').inner_text().startswith('No verified combinations')
                page.locator('#s4-search').fill('')
                page.locator('[data-s4-sort="1"]').click()
                checks['table_sort']=page.locator('#s4-scenarios th').nth(1).get_attribute('aria-sort')=='ascending'
                page.locator('[data-s4-sort="1"]').click()
                checks['table_reverse_sort']=page.locator('#s4-scenarios th').nth(1).get_attribute('aria-sort')=='descending'
                checks['only_selected_geometry_active']=page.evaluate('Object.values(ParcelAStage04.state.layers).filter(Boolean).length<=2')
            for value in page.locator('#s4-trend-metric option').evaluate_all('xs=>xs.map(x=>x.value)'):page.locator('#s4-trend-metric').select_option(value)
            with page.expect_download() as download:page.locator('#s4-export').click()
            checks['stage04_filtered_csv']=download.value.suggested_filename.endswith('.csv')
            checks['namespaced_state']=page.evaluate('typeof D==="object" && window.stage03Ready===true')
            checks['no_invalid_values']=not any(x in page.locator('#stage04').inner_text() for x in ['NaN','Infinity','undefined'])
            checks['no_caught_interface_errors']=page.evaluate('ParcelAStage04.state.errors.length===0')
            page.locator('#s4-period').focus();page.keyboard.press('ArrowDown');page.keyboard.press('Tab')
            checks['keyboard_focus']=page.evaluate('document.activeElement.tagName==="SELECT"')
            for width in [375,768]:
                page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(150)
                checks['mobile_no_overflow_'+str(width)]=page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                checks['mobile_map_'+str(width)]=page.locator('#s4-map-suit').bounding_box()['width']>100
            page.locator('[data-tab="overview"]').click();page.locator('#stage04-tab').click()
            checks['repeat_activation']=page.locator('#s4-map-suit .leaflet-map-pane').count()<=1
            if os.getenv('STAGE04_SCREENSHOTS'):
                folder=Path(os.environ['STAGE04_SCREENSHOTS']);folder.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(folder/('stage04-mobile.png')),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(folder/'stage04-desktop.png'),full_page=True)
            page.reload();page.wait_for_function('window.stage03Ready===true');page.locator('#stage04-tab').click()
            checks['offline_reload']=page.locator('#stage04').is_visible()
            touch=browser.new_context(offline=True,has_touch=True,is_mobile=True,viewport={'width':390,'height':844})
            mobile=touch.new_page();mobile.on('pageerror',lambda e:errors.append(str(e)))
            mobile.goto(Path(path).resolve().as_uri(),timeout=90000);mobile.wait_for_function('window.stage03Ready===true',timeout=90000)
            mobile.locator('#stage04-tab').tap();checks['touch_tab_activation']=mobile.locator('#stage04').is_visible()
            if keys:
                before=mobile.evaluate('ParcelAStage04.state.maps.suitability.getZoom()')
                mobile.locator('#s4-map-suit .leaflet-control-zoom-in').tap();mobile.wait_for_timeout(300)
                checks['touch_map_zoom']=mobile.evaluate('ParcelAStage04.state.maps.suitability.getZoom()')>before
                mobile.locator('#s4-reset-suit').tap()
                mobile.locator('#s4-product').tap();mobile.locator('#s4-product').select_option(index=0)
                checks['touch_controls']=mobile.evaluate('ParcelAStage04.state.errors.length===0')
            touch.close()
        checks['no_browser_exceptions']=not errors
        checks['no_required_network_requests']=not any(u.startswith(('http:','https:')) for u in requests)
        browser.close()
    return dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,errors=errors,network_failures=requests,tested_at_utc=now(),
                coverage='Every original tab, map selector, chart and table; core controls and CSV downloads; Stage 04 selections and diagnostics; offline reload and mobile widths when applicable')
