"""Unit tests for `site_ui/helpers.js`, `firestore.rules`, and `docs/contracts/schemas_and_routes.json`."""

from __future__ import annotations

import json
import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_contract_schema_and_files_exist() -> None:
    contract_path = os.path.join(REPO_ROOT, "docs", "contracts", "schemas_and_routes.json")
    assert os.path.exists(contract_path)
    with open(contract_path, "r", encoding="utf-8") as f:
        contract = json.load(f)

    assert contract["app"]["baseurl"] == "/College-Basketball-Stats"
    for page in contract["pages"]:
        assert os.path.exists(os.path.join(REPO_ROOT, page["source"]))


def test_common_js_keeps_firebase_placeholders() -> None:
    common_path = os.path.join(REPO_ROOT, "site_ui", "common.js")
    with open(common_path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "FIREBASE_API_KEY_PLACEHOLDER" in text
    assert "FIREBASE_PROJECT_ID_PLACEHOLDER" in text


def test_firestore_rules_enforces_pick_collection_and_owner_guards() -> None:
    rules_path = os.path.join(REPO_ROOT, "firestore.rules")
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = f.read()
    assert "^[0-9]+[mw]$" in rules
    assert "hasOnly(['displayName', 'favoriteTeamId'])" in rules
    assert "hasAll(['name', 'teamId', 'league', 'members', 'isPrivate'])" in rules


def test_helpers_js_pure_functions_via_node() -> None:
    helpers_path = os.path.join(REPO_ROOT, "site_ui", "helpers.js").replace("\\", "/")
    node_script = f"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const code = fs.readFileSync('{helpers_path}', 'utf8');
const sandbox = {{
  window: {{ location: {{ search: '', href: '' }} }},
  localStorage: {{
    _store: {{ favoriteTeamId: '152', league: 'mens' }},
    getItem(k) {{ return this._store[k] || null; }},
    setItem(k, v) {{ this._store[k] = String(v); }},
    removeItem(k) {{ delete this._store[k]; }}
  }},
  sessionStorage: {{ getItem() {{ return null; }}, setItem() {{}} }},
  URLSearchParams,
  TextEncoder,
  Uint8Array,
  console
}};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

// 1. escapeHtml & sanitizeUrl
assert.strictEqual(sandbox.escapeHtml('<script>"x"&\\'y\\'</script>'), '&lt;script&gt;&quot;x&quot;&amp;&#39;y&#39;&lt;/script&gt;');
assert.strictEqual(sandbox.sanitizeUrl('javascript:alert(1)'), '');
assert.strictEqual(sandbox.sanitizeUrl('https://a.espncdn.com/logo.png'), 'https://a.espncdn.com/logo.png');

// 2. calculateVal, getValDetails, getValTooltip, renderValBreakdownHtml
const labels = ['MIN', 'FG', '3PT', 'FT', 'OREB', 'DREB', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PF', 'PTS'];
const stats = ['32', '8-14', '3-6', '4-5', '2', '6', '8', '5', '2', '1', '2', '1', '23'];
// PTS(23) + 3PM(3) - FGA(14) + 2*FGM(16) - FTA(5) + FTM(4) + REB(8) + 2*AST(10) + 4*STL(8) + 4*BLK(4) - 2*TO(4) = 53
assert.strictEqual(sandbox.calculateVal(stats, labels), 53);
const details = sandbox.getValDetails(stats, labels);
assert.strictEqual(details.total, 53);
const tooltip = sandbox.getValTooltip(stats, labels);
assert(tooltip.includes('TOTAL: 53'));
const parsedLegacy = sandbox.parseLegacyBreakdownText(tooltip);
assert.strictEqual(parsedLegacy.total, 53);

// 2b. calculateAdvancedEfficiency & renderValBreakdownHtml efficiency strip
const eff = sandbox.calculateAdvancedEfficiency(stats, labels);
// eFG% = (8 + 0.5 * 3) / 14 = 9.5 / 14 = 67.9%
assert.strictEqual(eff.efgPct, 67.9);
assert.strictEqual(eff.efgDisplay, '67.9%');
// TS% = 23 / (2 * (14 + 0.44 * 5)) = 23 / 32.4 = 71.0%
assert.strictEqual(eff.tsPct, 71.0);
assert.strictEqual(eff.tsDisplay, '71.0%');
// AST/TO = 5 / 2 = 2.5
assert.strictEqual(eff.astToRatio, 2.5);
assert.strictEqual(eff.astToDisplay, '2.5');

const zeroStats = ['10', '0-0', '0-0', '0-0', '0', '1', '1', '3', '0', '0', '0', '1', '0'];
const zeroEff = sandbox.calculateAdvancedEfficiency(zeroStats, labels);
assert.strictEqual(zeroEff.efgPct, null);
assert.strictEqual(zeroEff.tsPct, null);
assert.strictEqual(zeroEff.astToRatio, null);
assert.strictEqual(zeroEff.efgDisplay, 'N/A');
assert.strictEqual(zeroEff.tsDisplay, 'N/A');
assert.strictEqual(zeroEff.astToDisplay, '3.0');

const html = sandbox.renderValBreakdownHtml(details, 'DJ Horne', 'NC State #152');
assert(html.includes('DJ Horne'));
assert(html.includes('+53'));
assert(html.includes('67.9%'));
assert(html.includes('71.0%'));
assert(html.includes('2.5'));
assert(!html.includes('val-formula-math-box'));

const zeroDetails = sandbox.getValDetails(zeroStats, labels);
const zeroHtml = sandbox.renderValBreakdownHtml(zeroDetails, 'Bench Player', 'NC State #152');
assert(zeroHtml.includes('N/A'));
assert(zeroHtml.includes('3.0'));

// 3. League / Collection / Logo / Rank helpers
assert.strictEqual(sandbox.getSportPath('mens'), 'mens-college-basketball');
assert.strictEqual(sandbox.getSportPath('womens'), 'womens-college-basketball');
assert.strictEqual(sandbox.getCollectionName('152', 'mens'), '152m');
assert.strictEqual(sandbox.getCollectionName('152', 'womens'), '152w');
assert.strictEqual(sandbox.getValTierClass(32), 'val-pill-high');
assert.strictEqual(sandbox.getValTierClass(18), 'val-pill-mid');
assert.strictEqual(sandbox.getValTierClass(5), 'val-pill-low');
assert.strictEqual(sandbox.getValTierClass(-2), 'val-pill-neg');
assert.strictEqual(sandbox.formatRankToken('12'), '#12');
assert.strictEqual(sandbox.formatRankToken('Tied-8'), '#8');
const logoHtml = sandbox.getTeamLogoHtml({{ logos: [{{ href: 'https://a.espncdn.com/152.png' }}] }});
assert(logoHtml.includes('https://a.espncdn.com/152.png'));

// 4. getGameQuadrant, calculateScheduleQuadSummary, calculateScheduleSosSummary
assert.strictEqual(sandbox.getGameQuadrant(25, true, false).quad, 1);
assert.strictEqual(sandbox.getGameQuadrant(45, false, true).quad, 1);
assert.strictEqual(sandbox.getGameQuadrant(65, false, false).quad, 1);
assert.strictEqual(sandbox.getGameQuadrant(120, false, false).quad, 2);
assert.strictEqual(sandbox.getGameQuadrant(200, true, false).quad, 4);

const bpiMap = {{ '150': {{ rank: 10 }}, '200': {{ rank: 90 }}, '250': {{ rank: 150 }}, '300': {{ rank: 260 }} }};
const events = [
  {{
    id: '4017',
    date: '2026-11-10T00:00:00Z',
    competitions: [{{
      id: '4017',
      neutralSite: false,
      status: {{ type: {{ state: 'post', completed: true }} }},
      competitors: [
        {{ team: {{ id: '152', shortDisplayName: 'NC State' }}, homeAway: 'home', winner: true, score: '78' }},
        {{ team: {{ id: '150', shortDisplayName: 'Duke' }}, homeAway: 'away', winner: false, score: '74' }}
      ]
    }}]
  }},
  {{
    id: '4018',
    date: '2026-11-18T00:00:00Z',
    competitions: [{{
      id: '4018',
      neutralSite: false,
      status: {{ type: {{ state: 'pre', completed: false }} }},
      competitors: [
        {{ team: {{ id: '152', shortDisplayName: 'NC State' }}, homeAway: 'away' }},
        {{ team: {{ id: '200', displayName: 'Clemson Tigers' }}, homeAway: 'home' }}
      ]
    }}]
  }},
  {{
    id: '4019',
    date: '2026-11-12T00:00:00Z',
    competitions: [{{
      id: '4019',
      neutralSite: true,
      status: {{ type: {{ state: 'post', completed: true }} }},
      competitors: [
        {{ team: {{ id: '152', shortDisplayName: 'NC State' }}, homeAway: 'home', winner: false, score: {{ value: 65, displayValue: '65' }} }},
        {{ team: {{ id: '250', shortDisplayName: 'Wake Forest' }}, homeAway: 'away', winner: true, score: {{ value: 71, displayValue: '71' }} }}
      ]
    }}]
  }},
  {{
    id: '4020',
    date: '2026-11-14T00:00:00Z',
    competitions: [{{
      id: '4020',
      neutralSite: false,
      status: {{ type: {{ state: 'post', completed: true }} }},
      competitors: [
        {{ team: {{ id: '152', shortDisplayName: 'NC State' }}, homeAway: 'home', winner: true, score: '88' }},
        {{ team: {{ id: '300', shortDisplayName: 'Elon' }}, homeAway: 'away', winner: false, score: '60' }}
      ]
    }}]
  }}
];
const quadSum = sandbox.calculateScheduleQuadSummary(events, '152', bpiMap);
assert.strictEqual(quadSum[1].w, 1);
assert.strictEqual(quadSum[1].l, 0);
assert.strictEqual(quadSum[1].rem, 0);
assert.strictEqual(quadSum[1].pct, 100);
assert.strictEqual(Array.isArray(quadSum[1].games), true);
assert.strictEqual(quadSum[1].games.length, 1);
assert.strictEqual(quadSum[1].games[0].id, '4017');
assert.strictEqual(quadSum[1].games[0].opponentName, 'Duke');
assert.strictEqual(quadSum[1].games[0].locationLabel, 'Home');
assert.strictEqual(quadSum[1].games[0].oppRank, 10);
assert.strictEqual(quadSum[1].games[0].completed, true);
assert.strictEqual(quadSum[1].games[0].winner, true);
assert.strictEqual(quadSum[1].games[0].score, '78-74');

assert.strictEqual(quadSum[2].w, 0);
assert.strictEqual(quadSum[2].l, 0);
assert.strictEqual(quadSum[2].rem, 1);
assert.strictEqual(quadSum[2].pct, null);
assert.strictEqual(quadSum[2].games.length, 1);
assert.strictEqual(quadSum[2].games[0].id, '4018');
assert.strictEqual(quadSum[2].games[0].opponentName, 'Clemson Tigers');
assert.strictEqual(quadSum[2].games[0].locationLabel, 'Away');
assert.strictEqual(quadSum[2].games[0].oppRank, 90);
assert.strictEqual(quadSum[2].games[0].completed, false);
assert.strictEqual(quadSum[2].games[0].winner, false);
assert.strictEqual(quadSum[2].games[0].score, '');

assert.strictEqual(quadSum[3].w, 0);
assert.strictEqual(quadSum[3].l, 1);
assert.strictEqual(quadSum[3].pct, 0);
assert.strictEqual(quadSum[3].games.length, 1);
assert.strictEqual(quadSum[3].games[0].id, '4019');
assert.strictEqual(quadSum[3].games[0].opponentName, 'Wake Forest');
assert.strictEqual(quadSum[3].games[0].locationLabel, 'Neutral');
assert.strictEqual(quadSum[3].games[0].oppRank, 150);
assert.strictEqual(quadSum[3].games[0].completed, true);
assert.strictEqual(quadSum[3].games[0].winner, false);
assert.strictEqual(quadSum[3].games[0].score, '65-71');

assert.strictEqual(quadSum[4].w, 1);
assert.strictEqual(quadSum[4].l, 0);
assert.strictEqual(quadSum[4].pct, 100);
assert.strictEqual(quadSum[4].games.length, 1);
assert.strictEqual(quadSum[4].games[0].id, '4020');
assert.strictEqual(quadSum[4].games[0].opponentName, 'Elon');
assert.strictEqual(quadSum[4].games[0].locationLabel, 'Home');
assert.strictEqual(quadSum[4].games[0].oppRank, 260);
assert.strictEqual(quadSum[4].games[0].completed, true);
assert.strictEqual(quadSum[4].games[0].winner, true);
assert.strictEqual(quadSum[4].games[0].score, '88-60');

const emptyQuadSum = sandbox.calculateScheduleQuadSummary(null, '152', null);
assert.strictEqual(JSON.stringify(emptyQuadSum[1]), JSON.stringify({{ w: 0, l: 0, rem: 0, pct: null, games: [] }}));
assert.strictEqual(JSON.stringify(emptyQuadSum[4]), JSON.stringify({{ w: 0, l: 0, rem: 0, pct: null, games: [] }}));

const sosSum = sandbox.calculateScheduleSosSummary(events.slice(0, 2), '152', bpiMap);
assert.strictEqual(sosSum.avgOppRank, 50);

// 5. Live schedule game score resolution (Issue #4: prevent 0-0 while in-game)
assert.strictEqual(sandbox.extractCompetitorScore({{ score: '68' }}), '68');
assert.strictEqual(sandbox.extractCompetitorScore({{ score: {{ value: 72, displayValue: '72' }} }}), '72');
assert.strictEqual(sandbox.extractCompetitorScore({{ score: {{}} }}), null);
assert.strictEqual(sandbox.extractCompetitorScore({{ linescores: [{{ value: 31 }}, {{ displayValue: '37' }}] }}), '68');

const nowMs = Date.parse('2026-11-15T20:00:00Z');
assert.strictEqual(sandbox.isGameInLiveWindow('2026-11-15T19:00:00Z', nowMs), true);
assert.strictEqual(sandbox.isGameInLiveWindow('2026-11-15T21:00:00Z', nowMs), false);
assert.strictEqual(sandbox.isGameInLiveWindow('2026-11-15T10:00:00Z', nowMs), false);

// ESPN /teams/{id}/schedule omits competitor.score (or leaves it 0-0) while state === 'in'
const liveSchedEventNoScores = {{
  id: '401638645',
  date: '2026-11-15T19:00:00Z',
  competitions: [{{
    id: '401638645',
    status: {{ type: {{ state: 'in', completed: false, detail: '8:44 - 2nd Half', shortDetail: '8:44 - 2nd' }} }},
    competitors: [
      {{ id: '152', homeAway: 'home', team: {{ id: '152' }} }},
      {{ id: '153', homeAway: 'away', team: {{ id: '153' }} }}
    ]
  }}]
}};

// Without summary, raw schedule event with missing scores must not fabricate '0-0'
const unhydratedHtml = sandbox.formatScheduleGameResultHtml(liveSchedEventNoScores, null, '152');
assert(unhydratedHtml.includes('LIVE'));
assert(!unhydratedHtml.includes('0-0'));

// With summary from /summary?event=..., live scores 68-64 are resolved and rendered
const liveSummary = {{
  header: {{
    competitions: [{{
      id: '401638645',
      status: {{ type: {{ state: 'in', completed: false, detail: '8:44 - 2nd Half', shortDetail: '8:44 - 2nd' }} }},
      competitors: [
        {{ id: '152', homeAway: 'home', score: '68', team: {{ id: '152' }} }},
        {{ id: '153', homeAway: 'away', score: '64', team: {{ id: '153' }} }}
      ]
    }}]
  }}
}};
const hydratedStatus = sandbox.resolveScheduleGameStatus(liveSchedEventNoScores, liveSummary, '152');
assert.strictEqual(hydratedStatus.state, 'in');
assert.strictEqual(hydratedStatus.myScore, '68');
assert.strictEqual(hydratedStatus.oppScore, '64');
const hydratedHtml = sandbox.formatScheduleGameResultHtml(liveSchedEventNoScores, liveSummary, '152');
assert(hydratedHtml.includes('LIVE'));
assert(hydratedHtml.includes('68-64'));
assert(hydratedHtml.includes('8:44 - 2nd'));

// Fallback when summary header has 0-0 but plays / boxscore have live scores
const headerZeroSummaryWithPlays = {{
  header: {{
    competitions: [{{
      id: '401638645',
      status: {{ type: {{ state: 'in', completed: false, shortDetail: '18:10 - 1st' }} }},
      competitors: [
        {{ id: '152', homeAway: 'home', score: '0', team: {{ id: '152' }} }},
        {{ id: '153', homeAway: 'away', score: '0', team: {{ id: '153' }} }}
      ]
    }}]
  }},
  plays: [
    {{ homeScore: 7, awayScore: 4, text: 'Jumper made' }}
  ]
}};
const playFallback = sandbox.resolveScheduleGameStatus(liveSchedEventNoScores, headerZeroSummaryWithPlays, '152');
assert.strictEqual(playFallback.myScore, '7');
assert.strictEqual(playFallback.oppScore, '4');
assert.strictEqual(playFallback.scoreSource, 'summary_plays');

// Test hydrateLiveScheduleEvents with mocked fetch
sandbox.fetch = async (url) => ({{
  ok: true,
  json: async () => liveSummary
}});
const schedClone = JSON.parse(JSON.stringify([liveSchedEventNoScores]));
sandbox.hydrateLiveScheduleEvents(schedClone, 'mens-college-basketball', '152').then((res) => {{
  const c0 = res[0].competitions[0].competitors.find(c => c.id === '152');
  const c1 = res[0].competitions[0].competitors.find(c => c.id === '153');
  assert.strictEqual(c0.score.displayValue, '68');
  assert.strictEqual(c1.score.displayValue, '64');
}});
"""
    proc = subprocess.run(
        ["node", "-e", node_script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"Node test failed:\n{proc.stdout}\n{proc.stderr}"


def test_modal_overlays_have_dialog_aria_attributes() -> None:
    expected_modals = {
        os.path.join("site_ui", "scoreboard", "index.html"): {
            "val-modal": "val-modal-title",
            "val-formula-modal": "val-formula-modal-title",
        },
        os.path.join("site_ui", "roster", "index.html"): {
            "val-modal": "val-modal-title",
            "val-formula-modal": "val-formula-modal-title",
        },
        os.path.join("site_ui", "group", "index.html"): {
            "member-picks-modal": "member-picks-modal-title",
            "group-privacy-modal": "group-privacy-modal-title",
        },
    }

    overlay_tag_re = re.compile(r'<div\b[^>]*\bclass="[^"]*\bmodal-overlay\b[^"]*"[^>]*>', re.IGNORECASE)

    for rel_path, modal_map in expected_modals.items():
        full_path = os.path.join(REPO_ROOT, rel_path)
        assert os.path.exists(full_path), f"Missing page {rel_path}"
        with open(full_path, "r", encoding="utf-8") as f:
            html_text = f.read()

        tags = overlay_tag_re.findall(html_text)
        assert len(tags) == len(modal_map), f"Expected {len(modal_map)} .modal-overlay tags in {rel_path}, found {len(tags)}"

        found_ids = set()
        for tag in tags:
            id_match = re.search(r'\bid="([^"]+)"', tag)
            assert id_match is not None, f".modal-overlay missing id in {rel_path}: {tag}"
            modal_id = id_match.group(1)
            found_ids.add(modal_id)
            assert 'role="dialog"' in tag, f"#{modal_id} in {rel_path} missing role=\"dialog\": {tag}"
            assert 'aria-modal="true"' in tag, f"#{modal_id} in {rel_path} missing aria-modal=\"true\": {tag}"
            expected_label_id = modal_map[modal_id]
            assert f'aria-labelledby="{expected_label_id}"' in tag, (
                f"#{modal_id} in {rel_path} missing aria-labelledby=\"{expected_label_id}\": {tag}"
            )
            assert f'id="{expected_label_id}"' in html_text, (
                f"Target element id=\"{expected_label_id}\" not found in {rel_path}"
            )

        assert found_ids == set(modal_map.keys())


def test_modal_escape_key_handlers_via_node() -> None:
    pages = [
        (os.path.join(REPO_ROOT, "site_ui", "scoreboard", "index.html"), ["val-modal", "val-formula-modal"]),
        (os.path.join(REPO_ROOT, "site_ui", "roster", "index.html"), ["val-modal", "val-formula-modal"]),
        (os.path.join(REPO_ROOT, "site_ui", "group", "index.html"), ["member-picks-modal", "group-privacy-modal"]),
    ]

    for page_path, modal_ids in pages:
        with open(page_path, "r", encoding="utf-8") as f:
            html_text = f.read()

        match = re.search(
            r"(function\s+handleModalEscapeKey\s*\([^)]*\)\s*\{[\s\S]*?document\.addEventListener\s*\(\s*['\"]keydown['\"]\s*,\s*handleModalEscapeKey\s*\)\s*;)",
            html_text,
        )
        assert match is not None, f"Could not find handleModalEscapeKey & keydown listener in {page_path}"
        handler_js = match.group(1)
        modal_ids_json = json.dumps(modal_ids)

        node_script = f"""
const vm = require('vm');
const assert = require('assert');

const modalIds = {modal_ids_json};
function makeModal(id) {{
  const classes = new Set(['modal-overlay']);
  return {{
    id,
    style: {{ display: 'none' }},
    classList: {{
      add(c) {{ classes.add(c); }},
      remove(c) {{ classes.delete(c); }},
      contains(c) {{ return classes.has(c); }}
    }}
  }};
}}

const modalsById = {{}};
modalIds.forEach(id => {{ modalsById[id] = makeModal(id); }});
const listeners = {{}};

const sandbox = {{
  document: {{
    getElementById(id) {{ return modalsById[id] || null; }},
    querySelectorAll(sel) {{
      if (sel === '.modal-overlay') return Object.values(modalsById);
      return [];
    }},
    addEventListener(type, fn) {{
      listeners[type] = fn;
    }}
  }},
  Array
}};

vm.createContext(sandbox);
vm.runInContext({json.dumps(handler_js)}, sandbox);

assert.strictEqual(typeof listeners.keydown, 'function', 'keydown listener not registered');

const firstModal = modalsById[modalIds[0]];
const secondModal = modalsById[modalIds[1]];

// 1. Pressing Escape when no modal is open returns false and does not preventDefault
let prevented = false;
const resClosed = listeners.keydown({{
  key: 'Escape',
  preventDefault() {{ prevented = true; }},
  stopPropagation() {{}}
}});
assert.strictEqual(resClosed, false);
assert.strictEqual(prevented, false);

// 2. Pressing non-Escape key while modal is open leaves modal open
firstModal.style.display = 'flex';
firstModal.classList.add('open');
const resEnter = listeners.keydown({{
  key: 'Enter',
  preventDefault() {{ prevented = true; }},
  stopPropagation() {{}}
}});
assert.strictEqual(resEnter, false);
assert.strictEqual(firstModal.style.display, 'flex');
assert.strictEqual(firstModal.classList.contains('open'), true);

// 3. Pressing Escape while firstModal has display: 'flex' closes it and prevents default
let stopped = false;
const resEsc = listeners.keydown({{
  key: 'Escape',
  preventDefault() {{ prevented = true; }},
  stopPropagation() {{ stopped = true; }}
}});
assert.strictEqual(resEsc, true);
assert.strictEqual(prevented, true);
assert.strictEqual(stopped, true);
assert.strictEqual(firstModal.style.display, 'none');
assert.strictEqual(firstModal.classList.contains('open'), false);
assert.strictEqual(secondModal.style.display, 'none');

// 4. Pressing Escape while secondModal has .open class closes it
secondModal.style.display = '';
secondModal.classList.add('open');
const resEsc2 = listeners.keydown({{
  key: 'Escape',
  preventDefault() {{}},
  stopPropagation() {{}}
}});
assert.strictEqual(resEsc2, true);
assert.strictEqual(secondModal.style.display, 'none');
assert.strictEqual(secondModal.classList.contains('open'), false);
"""
        proc = subprocess.run(
            ["node", "-e", node_script],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, f"Modal Escape key test failed for {page_path}:\n{proc.stdout}\n{proc.stderr}"


def test_standings_quadrant_drilldown_toggle_via_node() -> None:
    standings_path = os.path.join(REPO_ROOT, "site_ui", "standings", "index.html")
    with open(standings_path, "r", encoding="utf-8") as f:
        html_text = f.read()

    assert "standings-quad-card-interactive" in html_text
    assert "standings-quad-drilldown" in html_text
    assert "toggleQuadGamesDrilldown" in html_text

    fn_match = re.search(
        r"(function\s+toggleQuadGamesDrilldown\s*\([^)]*\)\s*\{[\s\S]*?\n    \})",
        html_text,
    )
    assert fn_match is not None, "Could not find toggleQuadGamesDrilldown in site_ui/standings/index.html"
    toggle_fn_js = fn_match.group(1)

    node_script = f"""
const vm = require('vm');
const assert = require('assert');

function makeCard(q) {{
  const classes = new Set(['standings-quad-card', 'standings-quad-card-interactive']);
  const attrs = {{ 'data-quad': String(q), 'aria-expanded': 'false' }};
  const hint = {{ textContent: 'Tap to view ▸' }};
  return {{
    dataset: {{ quad: String(q), teamId: '152' }},
    classList: {{
      add(c) {{ classes.add(c); }},
      remove(c) {{ classes.delete(c); }},
      contains(c) {{ return classes.has(c); }}
    }},
    setAttribute(k, v) {{ attrs[k] = String(v); }},
    getAttribute(k) {{ return attrs[k]; }},
    querySelector(sel) {{
      if (sel === '.standings-quad-toggle-hint') return hint;
      return null;
    }},
    _hint: hint
  }};
}}

function makePanel(q) {{
  return {{
    id: `standings-quad-drilldown-152-${{q}}`,
    dataset: {{ quad: String(q), teamId: '152' }},
    style: {{ display: 'none' }}
  }};
}}

const cards = {{ 1: makeCard(1), 2: makeCard(2), 3: makeCard(3), 4: makeCard(4) }};
const panels = {{ 1: makePanel(1), 2: makePanel(2), 3: makePanel(3), 4: makePanel(4) }};

const drawerEl = {{
  querySelectorAll(sel) {{
    if (sel === '.standings-quad-card[data-quad]') return Object.values(cards);
    if (sel === '.standings-quad-drilldown[data-quad]') return Object.values(panels);
    return [];
  }},
  querySelector(sel) {{
    const m = sel.match(/data-quad="(\\d+)"/);
    if (m) return cards[Number(m[1])] || null;
    return null;
  }}
}};

const sandbox = {{
  document: {{
    getElementById(id) {{
      if (id === 'standings-drawer-content-152') return drawerEl;
      const m = id.match(/^standings-quad-drilldown-152-(\\d+)$/);
      if (m) return panels[Number(m[1])] || null;
      return null;
    }}
  }}
}};

vm.createContext(sandbox);
vm.runInContext({json.dumps(toggle_fn_js)}, sandbox);

// 1. Tapping Q1 opens Q1 panel and marks Q1 card active
sandbox.toggleQuadGamesDrilldown('152', '1');
assert.strictEqual(panels[1].style.display, 'block');
assert.strictEqual(cards[1].classList.contains('active'), true);
assert.strictEqual(cards[1].getAttribute('aria-expanded'), 'true');
assert.strictEqual(cards[1]._hint.textContent, 'Expanded ▾');
assert.strictEqual(panels[2].style.display, 'none');

// 2. Tapping Q2 switches from Q1 to Q2
sandbox.toggleQuadGamesDrilldown('152', '2');
assert.strictEqual(panels[1].style.display, 'none');
assert.strictEqual(cards[1].classList.contains('active'), false);
assert.strictEqual(cards[1].getAttribute('aria-expanded'), 'false');
assert.strictEqual(cards[1]._hint.textContent, 'Tap to view ▸');
assert.strictEqual(panels[2].style.display, 'block');
assert.strictEqual(cards[2].classList.contains('active'), true);
assert.strictEqual(cards[2].getAttribute('aria-expanded'), 'true');
assert.strictEqual(cards[2]._hint.textContent, 'Expanded ▾');

// 3. Tapping Q2 again collapses Q2
sandbox.toggleQuadGamesDrilldown('152', '2');
assert.strictEqual(panels[2].style.display, 'none');
assert.strictEqual(cards[2].classList.contains('active'), false);
assert.strictEqual(cards[2].getAttribute('aria-expanded'), 'false');
assert.strictEqual(cards[2]._hint.textContent, 'Tap to view ▸');
"""
    proc = subprocess.run(
        ["node", "-e", node_script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"Standings quadrant drilldown test failed:\n{proc.stdout}\n{proc.stderr}"


