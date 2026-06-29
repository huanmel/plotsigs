/* plotsigs browser — auto-loaded by Dash from assets/
   1. Forwards ALL console output to Flask /_log → temp/dash_debug.log
   2. Directly registers AG Grid event listeners via the API (bypasses eventListeners prop)
   3. Updates Dash stores via window.dash_clientside.set_props
*/
(function () {
    /* ── 1. Console forwarding ─────────────────────────────────────────── */
    var _origLog   = console.log.bind(console);
    var _origWarn  = console.warn.bind(console);
    var _origError = console.error.bind(console);

    function send(level, args) {
        var msg = Array.from(args).map(function (a) {
            if (a instanceof Error) return a.stack || String(a);
            try { return typeof a === 'object' ? JSON.stringify(a) : String(a); }
            catch (_) { return String(a); }
        }).join(' ');
        fetch('/_log', {
            method: 'POST',
            body: '[' + level + '] ' + msg,
            headers: { 'Content-Type': 'text/plain' }
        }).catch(function () {});
    }

    console.log   = function () { _origLog.apply(console, arguments);   send('LOG',  arguments); };
    console.warn  = function () { _origWarn.apply(console, arguments);  send('WARN', arguments); };
    console.error = function () { _origError.apply(console, arguments); send('ERROR', arguments); };

    window.onerror = function (msg, url, line, col, error) {
        var stack = error && error.stack ? error.stack : '';
        send('EXCEPTION', [msg + ' @ ' + url + ':' + line + (stack ? '\n' + stack : '')]);
    };
    window.addEventListener('unhandledrejection', function (ev) {
        var r = ev.reason;
        send('REJECTION', [r instanceof Error ? (r.stack || String(r)) : String(r)]);
    });

    send('LOG', ['[plotsigs] assets/logger.js loaded']);

    /* ── 2. AG Grid direct listener registration ───────────────────────── */
    /* Polls until dash_ag_grid.getApi('signal-library') is available,
       then registers selectionChanged and rowDragEnd directly.
       Updates Dash stores via window.dash_clientside.set_props.         */

    var _registered = false;

    function tryRegister() {
        if (_registered) return;
        if (typeof dash_ag_grid === 'undefined' || !dash_ag_grid.getApi) return;
        var api;
        try { api = dash_ag_grid.getApi('signal-library'); } catch (_) { return; }
        if (!api) return;

        /* selectionChanged → update ag-sel-store with selected signal names */
        api.addEventListener('selectionChanged', function (ev) {
            try {
                var rows  = api.getSelectedRows();
                var names = rows.map(function (r) { return r.name; });
                console.log('[plotsigs sel] selectionChanged names:', names);
                if (window.dash_clientside && window.dash_clientside.set_props) {
                    window.dash_clientside.set_props('ag-sel-store', { data: names });
                }
            } catch (e) {
                console.error('[plotsigs sel] error:', e);
            }
        });

        /* rowDragEnd → find panel at drop position → update layout-store */
        api.addEventListener('rowDragEnd', function (ev) {
            try {
                var nodes   = ev.nodes || (ev.node ? [ev.node] : []);
                var nd      = nodes.length ? nodes[0] : null;
                var sigName = nd && nd.data && nd.data.name;
                console.log('[plotsigs drag] rowDragEnd sigName:', sigName,
                            'pos:', window._lastMX, window._lastMY);
                if (!sigName) return;

                /* Resolve panel under mouse */
                var mx = window._lastMX || 0, my = window._lastMY || 0;
                var toPanel = null;
                if (mx || my) {
                    var els = document.elementsFromPoint(mx, my) || [];
                    for (var i = 0; i < els.length; i++) {
                        if (els[i].dataset && els[i].dataset.layoutDrop !== undefined) {
                            toPanel = els[i].dataset.layoutDrop; break;
                        }
                    }
                    if (!toPanel) {
                        for (var j = 0; j < els.length; j++) {
                            var spEl = els[j].closest && els[j].closest('.subplot');
                            if (spEl) {
                                var spCls = Array.from(spEl.classList)
                                    .find(function (c) { return c !== 'subplot'; });
                                if (spCls) {
                                    var ym = spCls.match(/y(\d*)$/);
                                    var gIdx = ym ? (ym[1] ? parseInt(ym[1]) - 1 : 0) : 0;
                                    window._plotsigsResolvePanel(sigName, gIdx);
                                    return;  /* async path */
                                }
                                break;
                            }
                        }
                    }
                }
                if (!toPanel) toPanel = window._agDragOverPanel;
                window._agDragOverPanel = null;
                document.querySelectorAll('[data-layout-drop]')
                    .forEach(function (z) { z.classList.remove('ag-drag-active'); });

                console.log('[plotsigs drag] toPanel:', toPanel);
                if (!toPanel) return;

                /* Add signal to panel via set_props on layout-store */
                window._plotsigsAddToPanel(sigName, toPanel);
            } catch (e) {
                console.error('[plotsigs drag] error:', e);
            }
        });

        _registered = true;
        console.log('[plotsigs] AG Grid listeners registered on signal-library');
    }

    /* Poll every 300 ms until the grid API is available (max ~30 s) */
    var _attempts = 0;
    var _poll = setInterval(function () {
        _attempts++;
        tryRegister();
        if (_registered || _attempts > 100) clearInterval(_poll);
    }, 300);

    /* ── 3. Helpers called by the event listeners ──────────────────────── */

    /* Add sigName to panel toPanel — reads current layout-store via Dash */
    window._plotsigsAddToPanel = function (sigName, toPanel) {
        /* Use Dash's Redux store to get current layout */
        try {
            var store = window.dash_clientside;
            if (!store || !store.set_props) {
                console.error('[plotsigs] dash_clientside.set_props not available');
                return;
            }
            /* Get current layout from the Dash store via DOM/Dash internal */
            var layoutEl = document.getElementById('layout-store');
            var layout = layoutEl && layoutEl._dashprivate_isLoading !== undefined
                ? null : null; /* can't read store this way */

            /* Best effort: use window._plotsigsLayout if set by a clientside cb */
            var currentLayout = window._plotsigsLayout;
            if (!currentLayout) {
                console.warn('[plotsigs] layout not cached yet, signal will be added on next layout sync');
                /* Store pending add for pickup by a polling clientside callback */
                window._plotsigsPendingAdd = { sigName: sigName, toPanel: toPanel };
                return;
            }

            var newLayout = currentLayout.map(function (p) {
                if (p.ylabel !== toPanel) return p;
                if (p.signals.indexOf(sigName) >= 0) return p;
                return Object.assign({}, p, { signals: p.signals.concat([sigName]) });
            });
            console.log('[plotsigs] set_props layout-store');
            store.set_props('layout-store', { data: newLayout });
        } catch (e) {
            console.error('[plotsigs drag] _plotsigsAddToPanel error:', e);
        }
    };

    /* Subplot path: resolve by panel index (called asynchronously) */
    window._plotsigsResolvePanel = function (sigName, gIdx) {
        var currentLayout = window._plotsigsLayout;
        if (!currentLayout) return;
        var active = currentLayout.filter(function (p) {
            return (p.signals || []).length > 0;
        });
        var panel = active[gIdx];
        if (!panel) return;
        console.log('[plotsigs drag] subplot resolved panel:', panel.ylabel);
        window._plotsigsAddToPanel(sigName, panel.ylabel);
    };

})();
