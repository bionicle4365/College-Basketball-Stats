"""Unit tests for `site_ui/helpers.js`, `firestore.rules`, and `docs/contracts/schemas_and_routes.json`."""

from __future__ import annotations

import json
import os
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

const bpiMap = {{ '150': {{ rank: 10 }}, '200': {{ rank: 90 }} }};
const events = [
  {{
    competitions: [{{
      neutralSite: false,
      status: {{ type: {{ state: 'post', completed: true }} }},
      competitors: [
        {{ team: {{ id: '152' }}, homeAway: 'home', winner: true }},
        {{ team: {{ id: '150' }}, homeAway: 'away', winner: false }}
      ]
    }}]
  }},
  {{
    competitions: [{{
      neutralSite: false,
      status: {{ type: {{ state: 'pre', completed: false }} }},
      competitors: [
        {{ team: {{ id: '152' }}, homeAway: 'away' }},
        {{ team: {{ id: '200' }}, homeAway: 'home' }}
      ]
    }}]
  }}
];
const quadSum = sandbox.calculateScheduleQuadSummary(events, '152', bpiMap);
assert.strictEqual(quadSum[1].w, 1);
assert.strictEqual(quadSum[2].rem, 1);
const sosSum = sandbox.calculateScheduleSosSummary(events, '152', bpiMap);
assert.strictEqual(sosSum.avgOppRank, 50);
"""
    proc = subprocess.run(
        ["node", "-e", node_script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"Node test failed:\n{proc.stdout}\n{proc.stderr}"
