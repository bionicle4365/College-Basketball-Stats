function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function sanitizeUrl(url) {
    if (!url) return '';
    const trimmed = String(url).trim();
    if (/^(https?:|\/|\.\/)/i.test(trimmed)) {
        return escapeHtml(trimmed);
    }
    return '';
}

function generateSalt(byteLength = 16) {
    const buffer = new Uint8Array(byteLength);
    crypto.getRandomValues(buffer);
    return Array.from(buffer, b => b.toString(16).padStart(2, '0')).join('');
}

async function hashPassword(password, salt = '') {
    const encoder = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        'raw',
        encoder.encode(password),
        { name: 'PBKDF2' },
        false,
        ['deriveBits']
    );
    const derivedBits = await crypto.subtle.deriveBits(
        {
            name: 'PBKDF2',
            salt: encoder.encode(salt),
            iterations: 100000,
            hash: 'SHA-256'
        },
        keyMaterial,
        256
    );
    const hashArray = Array.from(new Uint8Array(derivedBits));
    return 'pbkdf2:' + hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function verifyPassword(enteredPassword, salt, storedHash) {
    if (!storedHash || !enteredPassword) return false;
    if (storedHash.startsWith('pbkdf2:')) {
        const computed = await hashPassword(enteredPassword, salt);
        return computed === storedHash;
    }
    // Backward compatibility for legacy single-round SHA-256 hashes
    const encoder = new TextEncoder();
    const data = encoder.encode(enteredPassword + ':' + (salt || ''));
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const legacyHash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return legacyHash === storedHash;
}

function checkAuth() {
    const isMock = Boolean(new URLSearchParams(window.location.search).get('mock') || new URLSearchParams(window.location.search).get('demo'));
    if (isMock) return;
    if (localStorage.getItem('isLoggedIn') !== 'true') {
        window.location.href = '/College-Basketball-Stats/login';
        return;
    }
    if (typeof auth !== 'undefined' && auth) {
        auth.onAuthStateChanged(user => {
            if (!user) {
                localStorage.removeItem('isLoggedIn');
                localStorage.removeItem('username');
                localStorage.removeItem('displayName');
                window.location.href = '/College-Basketball-Stats/login';
            }
        });
    }
}

function calculateVal(stats, labels) {
    if (!stats) return 0;
    
    const getStat = (key) => {
        const idx = labels.indexOf(key);
        return idx > -1 ? (stats[idx] || '0') : '0';
    };
    
    const parseMA = (val) => {
        const parts = val.split('-');
        return { m: parseInt(parts[0]) || 0, a: parseInt(parts[1]) || 0 };
    };

    const pts = parseInt(getStat('PTS')) || 0;
    const fg = parseMA(getStat('FG'));
    const threePt = parseMA(getStat('3PT'));
    const ft = parseMA(getStat('FT'));
    const reb = parseInt(getStat('REB')) || 0;
    const ast = parseInt(getStat('AST')) || 0;
    const stl = parseInt(getStat('STL')) || 0;
    const blk = parseInt(getStat('BLK')) || 0;
    const tov = parseInt(getStat('TO')) || 0;

    return pts + threePt.m - fg.a + (fg.m * 2) - ft.a + ft.m + reb + (ast * 2) + (stl * 4) + (blk * 4) - (tov * 2);
}

function getValTooltip(stats, labels) {
    if (!stats) return '';
    
    const getStat = (key) => {
        const idx = labels.indexOf(key);
        return idx > -1 ? (stats[idx] || '0') : '0';
    };
    
    const parseMA = (val) => {
        const parts = val.split('-');
        return { m: parseInt(parts[0]) || 0, a: parseInt(parts[1]) || 0 };
    };

    const pts = parseInt(getStat('PTS')) || 0;
    const fg = parseMA(getStat('FG'));
    const threePt = parseMA(getStat('3PT'));
    const ft = parseMA(getStat('FT'));
    const reb = parseInt(getStat('REB')) || 0;
    const ast = parseInt(getStat('AST')) || 0;
    const stl = parseInt(getStat('STL')) || 0;
    const blk = parseInt(getStat('BLK')) || 0;
    const tov = parseInt(getStat('TO')) || 0;

    const total = calculateVal(stats, labels);

    return `VAL BREAKDOWN\n` +
           `----------------\n` +
           `PTS:  ${pts}\n` +
           `3PM:  +${threePt.m}\n` +
           `FGA:  -${fg.a}\n` +
           `FGM:  +${fg.m * 2} (${fg.m} x 2)\n` +
           `FTA:  -${ft.a}\n` +
           `FTM:  +${ft.m}\n` +
           `REB:  +${reb}\n` +
           `AST:  +${ast * 2} (${ast} x 2)\n` +
           `STL:  +${stl * 4} (${stl} x 4)\n` +
           `BLK:  +${blk * 4} (${blk} x 4)\n` +
           `TO:   -${tov * 2} (${tov} x 2)\n` +
           `----------------\n` +
           `TOTAL: ${total}`;
}

function getValDetails(stats, labels) {
    if (!stats || !labels) return null;
    
    const getStat = (key) => {
        const idx = labels.indexOf(key);
        return idx > -1 ? (stats[idx] || '0') : '0';
    };
    
    const parseMA = (val) => {
        const parts = String(val || '0-0').split('-');
        return { m: parseInt(parts[0], 10) || 0, a: parseInt(parts[1], 10) || 0 };
    };

    const pts = parseInt(getStat('PTS'), 10) || 0;
    const fg = parseMA(getStat('FG'));
    const threePt = parseMA(getStat('3PT'));
    const ft = parseMA(getStat('FT'));
    const reb = parseInt(getStat('REB'), 10) || 0;
    const ast = parseInt(getStat('AST'), 10) || 0;
    const stl = parseInt(getStat('STL'), 10) || 0;
    const blk = parseInt(getStat('BLK'), 10) || 0;
    const tov = parseInt(getStat('TO'), 10) || 0;

    const total = pts + threePt.m - fg.a + (fg.m * 2) - ft.a + ft.m + reb + (ast * 2) + (stl * 4) + (blk * 4) - (tov * 2);

    return {
        pts,
        fg,
        threePt,
        ft,
        reb,
        ast,
        stl,
        blk,
        tov,
        total
    };
}

function parseLegacyBreakdownText(text) {
    if (!text) return null;
    const getVal = (prefix) => {
        const match = text.match(new RegExp(`${prefix}:\\s*([+-]?\\d+)`));
        return match ? parseInt(match[1], 10) : 0;
    };
    const pts = getVal('PTS');
    const threePtM = getVal('3PM');
    const fga = Math.abs(getVal('FGA'));
    const fgmMatch = text.match(/FGM:\s*\+?(\d+)\s*\((\d+)\s*x/);
    const fgm = fgmMatch ? parseInt(fgmMatch[2], 10) : 0;
    const fta = Math.abs(getVal('FTA'));
    const ftm = getVal('FTM');
    const reb = getVal('REB');
    const astMatch = text.match(/AST:\s*\+?(\d+)\s*\((\d+)\s*x/);
    const ast = astMatch ? parseInt(astMatch[2], 10) : 0;
    const stlMatch = text.match(/STL:\s*\+?(\d+)\s*\((\d+)\s*x/);
    const stl = stlMatch ? parseInt(stlMatch[2], 10) : 0;
    const blkMatch = text.match(/BLK:\s*\+?(\d+)\s*\((\d+)\s*x/);
    const blk = blkMatch ? parseInt(blkMatch[2], 10) : 0;
    const tovMatch = text.match(/TO:\s*-?(\d+)\s*\((\d+)\s*x/);
    const tov = tovMatch ? parseInt(tovMatch[2], 10) : 0;
    const totalMatch = text.match(/TOTAL:\s*([+-]?\d+)/);
    const total = totalMatch ? parseInt(totalMatch[1], 10) : (pts + threePtM - fga + (fgm * 2) - fta + ftm + reb + (ast * 2) + (stl * 4) + (blk * 4) - (tov * 2));

    return {
        pts,
        fg: { m: fgm, a: fga },
        threePt: { m: threePtM, a: 0 },
        ft: { m: ftm, a: fta },
        reb,
        ast,
        stl,
        blk,
        tov,
        total
    };
}

function calculateAdvancedEfficiency(stats, labels) {
    let pts = 0;
    let fg = { m: 0, a: 0 };
    let threePt = { m: 0, a: 0 };
    let ft = { m: 0, a: 0 };
    let ast = 0;
    let tov = 0;

    if (stats && !Array.isArray(stats) && typeof stats === 'object') {
        pts = Number(stats.pts) || 0;
        fg = { m: Number(stats.fg?.m) || 0, a: Number(stats.fg?.a) || 0 };
        threePt = { m: Number(stats.threePt?.m) || 0, a: Number(stats.threePt?.a) || 0 };
        ft = { m: Number(stats.ft?.m) || 0, a: Number(stats.ft?.a) || 0 };
        ast = Number(stats.ast) || 0;
        tov = Number(stats.tov) || 0;
    } else if (Array.isArray(stats) && Array.isArray(labels)) {
        const details = getValDetails(stats, labels);
        if (details) {
            pts = details.pts;
            fg = details.fg;
            threePt = details.threePt;
            ft = details.ft;
            ast = details.ast;
            tov = details.tov;
        }
    }

    const efgPct = fg.a > 0 ? Math.round(((fg.m + 0.5 * threePt.m) / fg.a) * 1000) / 10 : null;
    const tsDenominator = 2 * (fg.a + 0.44 * ft.a);
    const tsPct = tsDenominator > 0 ? Math.round((pts / tsDenominator) * 1000) / 10 : null;
    const astToRatio = tov > 0 ? Math.round((ast / tov) * 100) / 100 : null;

    const efgDisplay = efgPct !== null ? `${efgPct.toFixed(1)}%` : 'N/A';
    const tsDisplay = tsPct !== null ? `${tsPct.toFixed(1)}%` : 'N/A';
    const astToDisplay = tov > 0 ? `${(ast / tov).toFixed(1)}` : (ast > 0 ? `${ast}.0` : '0.0');

    return {
        efgPct,
        tsPct,
        astToRatio,
        efgDisplay,
        tsDisplay,
        astToDisplay,
        fgm: fg.m,
        fga: fg.a,
        threePm: threePt.m,
        ftm: ft.m,
        fta: ft.a,
        pts,
        ast,
        tov
    };
}

function renderValBreakdownHtml(details, playerName, teamInfo) {
    if (!details) return '';
    const { pts, fg, threePt, ft, reb, ast, stl, blk, tov, total } = details;

    const netShooting = pts + threePt.m - fg.a + (fg.m * 2) - ft.a + ft.m;
    const fgPct = fg.a > 0 ? Math.round((fg.m / fg.a) * 100) : 0;
    const ftPct = ft.a > 0 ? Math.round((ft.m / ft.a) * 100) : 0;
    const advEff = calculateAdvancedEfficiency(details);

    const cardItems = [
        {
            label: 'Points',
            val: pts > 0 ? `+${pts}` : `${pts}`,
            detail: `${pts} total points scored`,
            type: pts > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: '3-Point Bonus',
            val: threePt.m > 0 ? `+${threePt.m}` : `${threePt.m}`,
            detail: `${threePt.m} made 3PT (+1 bonus each)`,
            type: threePt.m > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Field Goals Made (2×)',
            val: fg.m > 0 ? `+${fg.m * 2}` : `${fg.m * 2}`,
            detail: `${fg.m} made FG × 2 VAL`,
            type: fg.m > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Field Goal Attempts (-1×)',
            val: fg.a > 0 ? `-${fg.a}` : `${fg.a}`,
            detail: `${fg.a} shot attempts (-1 VAL each)`,
            type: fg.a > 0 ? 'val-negative' : 'val-neutral'
        },
        {
            label: 'Free Throws Made',
            val: ft.m > 0 ? `+${ft.m}` : `${ft.m}`,
            detail: `${ft.m} made FT (+1 VAL each)`,
            type: ft.m > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Free Throw Attempts (-1×)',
            val: ft.a > 0 ? `-${ft.a}` : `${ft.a}`,
            detail: `${ft.a} FT attempts (-1 VAL each)`,
            type: ft.a > 0 ? 'val-negative' : 'val-neutral'
        },
        {
            label: 'Rebounds',
            val: reb > 0 ? `+${reb}` : `${reb}`,
            detail: `${reb} total boards (+1 VAL each)`,
            type: reb > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Assists (2×)',
            val: ast > 0 ? `+${ast * 2}` : `${ast * 2}`,
            detail: `${ast} assists × 2 VAL`,
            type: ast > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Steals (4×)',
            val: stl > 0 ? `+${stl * 4}` : `${stl * 4}`,
            detail: `${stl} steals × 4 VAL`,
            type: stl > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Blocks (4×)',
            val: blk > 0 ? `+${blk * 4}` : `${blk * 4}`,
            detail: `${blk} blocks × 4 VAL`,
            type: blk > 0 ? 'val-positive' : 'val-neutral'
        },
        {
            label: 'Turnovers (-2×)',
            val: tov > 0 ? `-${tov * 2}` : `${tov * 2}`,
            detail: `${tov} turnovers × -2 VAL`,
            type: tov > 0 ? 'val-negative' : 'val-neutral'
        },
        {
            label: 'Net Shooting Impact',
            val: netShooting >= 0 ? `+${netShooting}` : `${netShooting}`,
            detail: `${fg.m}/${fg.a} FG (${fgPct}%) · ${ft.m}/${ft.a} FT (${ftPct}%)`,
            type: netShooting > 0 ? 'val-positive' : (netShooting < 0 ? 'val-negative' : 'val-neutral')
        }
    ];

    const cardsHtml = cardItems.map(c => `
        <div class="val-card ${c.type}">
            <span class="val-card-val">${c.val}</span>
            <div class="val-card-desc">
                <strong>${escapeHtml(c.label)}</strong>
                <small>${escapeHtml(c.detail)}</small>
            </div>
        </div>
    `).join('');

    const scorePillClass = getValTierClass(total);
    const scorePillSign = total > 0 ? '+' : '';

    return `
        <div class="val-formula-header">
            <div>
                <h3 style="margin: 0; font-size: 1.25rem;">${escapeHtml(playerName || 'Player VAL Breakdown')}</h3>
                ${teamInfo ? `<div class="val-breakdown-player-sub">${escapeHtml(teamInfo)}</div>` : ''}
            </div>
            <div class="val-score-pill ${scorePillClass}">
                <span>Total VAL</span>
                <span style="font-size: 1.15rem; font-weight: 800;">${scorePillSign}${total}</span>
            </div>
        </div>

        <p class="val-intro-text" style="margin-bottom: 12px;">
            Live efficiency and performance breakdown for <strong>${escapeHtml(playerName || 'player')}</strong> based on ESPN Standard Fantasy VAL scoring.
        </p>

        <div class="val-section-title">Advanced Shooting &amp; Playmaking Efficiency</div>
        <div class="val-efficiency-strip">
            <div class="val-eff-pill">
                <span class="val-eff-label">Effective FG% (eFG%)</span>
                <span class="val-eff-value">${escapeHtml(advEff.efgDisplay)}</span>
                <span class="val-eff-sub">${fg.m}/${fg.a} FG · ${threePt.m} 3PM</span>
            </div>
            <div class="val-eff-pill">
                <span class="val-eff-label">True Shooting (TS%)</span>
                <span class="val-eff-value">${escapeHtml(advEff.tsDisplay)}</span>
                <span class="val-eff-sub">${pts} PTS · ${fg.a} FGA · ${ft.a} FTA</span>
            </div>
            <div class="val-eff-pill">
                <span class="val-eff-label">Assist / Turnover (AST/TO)</span>
                <span class="val-eff-value">${escapeHtml(advEff.astToDisplay)}</span>
                <span class="val-eff-sub">${ast} AST · ${tov} TO</span>
            </div>
        </div>

        <div class="val-section-title">Point Contribution Breakdown</div>
        <div class="val-cards-grid">
            ${cardsHtml}
        </div>

        <div class="val-footer-note val-breakdown-footer">
            <span>💡 <em>Total VAL rewards efficient scoring, playmaking, and defense while penalizing missed shots and turnovers.</em></span>
            <button type="button" class="btn-text-link" onclick="openFormulaFromBreakdown()">ℹ️ View Complete VAL Formula &amp; Rules →</button>
        </div>
    `;
}

function getFavoriteTeamId() {
    return localStorage.getItem('favoriteTeamId') || '152';
}

function getLeague() {
    return localStorage.getItem('league') || 'mens';
}

function getSportPath(league) {
    return (league || getLeague()) === 'womens' ? 'womens-college-basketball' : 'mens-college-basketball';
}

function getCollectionName(teamId, league) {
    return `${teamId || getFavoriteTeamId()}${(league || getLeague()) === 'mens' ? 'm' : 'w'}`;
}

function getAppContext() {
    const teamId = getFavoriteTeamId();
    const league = getLeague();
    const sportPath = getSportPath(league);
    const collectionName = getCollectionName(teamId, league);
    return { teamId, league, sportPath, collectionName };
}

function getTeamLogoHtml(team) {
    if (!team) return '';
    const logoLight = team.logos?.[0]?.href || team.logo || '';
    const logoDark = team.logos?.[1]?.href || logoLight;
    const safeLight = sanitizeUrl(logoLight);
    const safeDark = sanitizeUrl(logoDark);
    return `<img src="${safeLight}" class="team-logo logo-light" alt=""><img src="${safeDark}" class="team-logo logo-dark" alt="">`;
}

async function fetchAllTeams(league) {
    const sportPath = getSportPath(league);
    try {
        const response = await fetch(`https://site.api.espn.com/apis/v2/sports/basketball/${sportPath}/standings`);
        if (response.ok) {
            const data = await response.json();
            const teams = [];
            if (data.children) {
                data.children.forEach(conf => {
                    if (conf.standings && conf.standings.entries) {
                        conf.standings.entries.forEach(entry => {
                            if (entry.team) teams.push(entry.team);
                        });
                    }
                });
            }
            if (teams.length > 0) return teams;
        }
    } catch (e) {
        console.warn('Standings endpoint unavailable for teams list, trying groups:', e);
    }

    try {
        const response = await fetch(`https://site.api.espn.com/apis/site/v2/sports/basketball/${sportPath}/groups`);
        if (response.ok) {
            const data = await response.json();
            const teams = [];
            if (data.groups) {
                data.groups.forEach(g => {
                    (g.children || []).forEach(conf => {
                        (conf.teams || []).forEach(t => teams.push(t));
                    });
                });
            }
            return teams;
        }
    } catch (e) {
        console.error('Error fetching teams:', e);
    }
    return [];
}

function extractCompetitorScore(competitor) {
    if (!competitor || typeof competitor !== 'object') return null;

    if (competitor.score !== null && competitor.score !== undefined) {
        if (typeof competitor.score === 'object') {
            const raw = competitor.score.displayValue ?? competitor.score.value;
            if (raw !== null && raw !== undefined && String(raw).trim() !== '' && !isNaN(Number(raw))) {
                return String(Math.round(Number(raw)));
            }
        } else if (typeof competitor.score === 'string' || typeof competitor.score === 'number') {
            const trimmed = String(competitor.score).trim();
            if (trimmed !== '' && !isNaN(Number(trimmed))) {
                return String(Math.round(Number(trimmed)));
            }
        }
    }

    if (Array.isArray(competitor.linescores) && competitor.linescores.length > 0) {
        let sum = 0;
        let hasPeriodScore = false;
        competitor.linescores.forEach(ls => {
            const rawVal = ls?.value ?? ls?.displayValue;
            if (rawVal !== null && rawVal !== undefined && String(rawVal).trim() !== '' && !isNaN(Number(rawVal))) {
                sum += Number(rawVal);
                hasPeriodScore = true;
            }
        });
        if (hasPeriodScore) {
            return String(Math.round(sum));
        }
    }

    return null;
}

function isGameInLiveWindow(gameDateStr, nowMs) {
    if (!gameDateStr) return false;
    const targetTime = new Date(gameDateStr).getTime();
    if (isNaN(targetTime)) return false;
    const refNow = typeof nowMs === 'number' ? nowMs : Date.now();
    const elapsed = refNow - targetTime;
    return elapsed >= 0 && elapsed < 4 * 60 * 60 * 1000;
}

function resolveScheduleGameStatus(event, summary, teamId) {
    const tIdStr = String(teamId || getFavoriteTeamId());
    const schedGame = event?.competitions?.[0] || event || {};
    const summaryGame = summary?.header?.competitions?.[0] || null;

    const summaryStatusType = summaryGame?.status?.type || summary?.header?.status?.type || null;
    const schedStatusType = schedGame?.status?.type || event?.status?.type || null;

    let activeStatusType = schedStatusType || summaryStatusType || {};
    if (summaryStatusType && summaryStatusType.state) {
        if (
            summaryStatusType.state === 'post' ||
            summaryStatusType.state === 'in' ||
            !schedStatusType?.state ||
            schedStatusType.state === 'pre'
        ) {
            activeStatusType = summaryStatusType;
        }
    }

    const state = activeStatusType.state || 'pre';
    const completed = Boolean(activeStatusType.completed || state === 'post');
    const detail = activeStatusType.detail || '';
    const shortDetail = activeStatusType.shortDetail || detail || '';

    const findTeams = (comp) => {
        const comps = comp?.competitors;
        if (!Array.isArray(comps) || comps.length === 0) return { myTeam: null, opponent: null };
        const myTeam = comps.find(c => String(c?.team?.id ?? c?.id) === tIdStr) || null;
        const opponent = comps.find(c => String(c?.team?.id ?? c?.id) !== tIdStr) || null;
        return { myTeam, opponent };
    };

    const { myTeam: sumMy, opponent: sumOpp } = findTeams(summaryGame);
    const { myTeam: schedMy, opponent: schedOpp } = findTeams(schedGame);

    const candidates = [];

    if (sumMy && sumOpp) {
        const sMy = extractCompetitorScore({ score: sumMy.score });
        const sOpp = extractCompetitorScore({ score: sumOpp.score });
        if (sMy !== null && sOpp !== null) {
            candidates.push({ myScore: sMy, oppScore: sOpp, source: 'summary_header' });
        }
        const lMy = extractCompetitorScore({ linescores: sumMy.linescores });
        const lOpp = extractCompetitorScore({ linescores: sumOpp.linescores });
        if (lMy !== null && lOpp !== null) {
            candidates.push({ myScore: lMy, oppScore: lOpp, source: 'summary_linescores' });
        }
    }

    if (Array.isArray(summary?.plays) && summary.plays.length > 0) {
        for (let i = summary.plays.length - 1; i >= 0; i--) {
            const p = summary.plays[i];
            if (p && p.homeScore !== undefined && p.awayScore !== undefined && p.homeScore !== null && p.awayScore !== null) {
                const homeAway = sumMy?.homeAway || schedMy?.homeAway;
                if (homeAway === 'home' || homeAway === 'away') {
                    const isHome = homeAway === 'home';
                    const pMy = String(Math.round(Number(isHome ? p.homeScore : p.awayScore)));
                    const pOpp = String(Math.round(Number(isHome ? p.awayScore : p.homeScore)));
                    if (!isNaN(Number(pMy)) && !isNaN(Number(pOpp))) {
                        candidates.push({ myScore: pMy, oppScore: pOpp, source: 'summary_plays' });
                        break;
                    }
                }
            }
        }
    }

    if (Array.isArray(summary?.boxscore?.players) && summary.boxscore.players.length >= 2) {
        const myBox = summary.boxscore.players.find(p => String(p?.team?.id) === tIdStr);
        const oppBox = summary.boxscore.players.find(p => String(p?.team?.id) !== tIdStr);
        const sumBoxPts = (teamBox) => {
            const statGroup = teamBox?.statistics?.[0];
            if (!statGroup || !Array.isArray(statGroup.names)) return null;
            const ptsIdx = statGroup.names.indexOf('PTS');
            if (ptsIdx === -1) return null;
            if (Array.isArray(statGroup.totals) && statGroup.totals[ptsIdx] !== undefined && statGroup.totals[ptsIdx] !== '') {
                const tot = parseInt(statGroup.totals[ptsIdx], 10);
                if (!isNaN(tot)) return String(tot);
            }
            if (!Array.isArray(statGroup.athletes) || statGroup.athletes.length === 0) return null;
            let totalPts = 0;
            let hasStats = false;
            statGroup.athletes.forEach(a => {
                if (a && Array.isArray(a.stats) && a.stats[ptsIdx] !== undefined && !a.didNotPlay) {
                    const v = parseInt(a.stats[ptsIdx], 10);
                    if (!isNaN(v)) {
                        totalPts += v;
                        hasStats = true;
                    }
                }
            });
            return hasStats ? String(totalPts) : null;
        };
        if (myBox && oppBox) {
            const bMy = sumBoxPts(myBox);
            const bOpp = sumBoxPts(oppBox);
            if (bMy !== null && bOpp !== null) {
                candidates.push({ myScore: bMy, oppScore: bOpp, source: 'summary_boxscore' });
            }
        }
    }

    if (schedMy && schedOpp) {
        const eMy = extractCompetitorScore(schedMy);
        const eOpp = extractCompetitorScore(schedOpp);
        if (eMy !== null && eOpp !== null) {
            candidates.push({ myScore: eMy, oppScore: eOpp, source: 'schedule' });
        }
    }

    let chosen = candidates.find(c => Number(c.myScore) > 0 || Number(c.oppScore) > 0) || null;
    if (!chosen) {
        if (state === 'post') {
            chosen = candidates[0] || null;
        } else if (state === 'in') {
            chosen = candidates.find(c => c.source.startsWith('summary_')) || null;
        }
    }

    const myScore = chosen ? chosen.myScore : null;
    const oppScore = chosen ? chosen.oppScore : null;

    let isWin = Boolean(sumMy?.winner ?? schedMy?.winner);
    if (state === 'post' && sumMy?.winner === undefined && schedMy?.winner === undefined && myScore !== null && oppScore !== null) {
        if (Number(myScore) !== Number(oppScore)) {
            isWin = Number(myScore) > Number(oppScore);
        }
    }

    return {
        state,
        completed,
        detail,
        shortDetail,
        myScore,
        oppScore,
        isWin,
        scoreSource: chosen ? chosen.source : null
    };
}

function formatScheduleGameResultHtml(event, summary, teamId) {
    const schedGame = event?.competitions?.[0] || event || {};
    const resolved = resolveScheduleGameStatus(event, summary, teamId);

    if (resolved.state === 'post') {
        const hasScores = resolved.myScore !== null && resolved.oppScore !== null && resolved.myScore !== '' && resolved.oppScore !== '';
        const score = hasScores ? `${escapeHtml(resolved.myScore)}-${escapeHtml(resolved.oppScore)}` : '';
        let otInfo = '';
        if (resolved.shortDetail && resolved.shortDetail.includes('/')) {
            otInfo = ` <span style="font-size:0.85em; color:#666;">(${escapeHtml(resolved.shortDetail.split('/')[1])})</span>`;
        }
        return `<span class="${resolved.isWin ? 'win' : 'loss'}">${resolved.isWin ? 'W' : 'L'}</span>${score ? ' ' + score : ''}${otInfo}`;
    }

    if (resolved.state === 'in') {
        const detail = escapeHtml(resolved.shortDetail || resolved.detail || 'LIVE');
        const hasScores = resolved.myScore !== null && resolved.oppScore !== null && resolved.myScore !== '' && resolved.oppScore !== '';
        const scorePart = hasScores ? ` ${escapeHtml(resolved.myScore)}-${escapeHtml(resolved.oppScore)}` : '';
        return `<span class="badge-live" style="background:#cc0000; color:white; padding:2px 6px; border-radius:3px; font-size:0.75rem; font-weight:bold; margin-right:4px;">LIVE</span>${scorePart} <span style="font-size:0.85em; color:#666;">(${detail})</span>`;
    }

    const rawDate = event?.date || schedGame?.date;
    const date = rawDate ? new Date(rawDate) : null;
    if (date && !isNaN(date.getTime())) {
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }
    return escapeHtml(resolved.detail || 'TBD');
}

async function hydrateLiveScheduleEvents(events, sportPath, teamId) {
    if (!Array.isArray(events) || events.length === 0 || typeof fetch !== 'function') {
        return events;
    }
    const sPath = sportPath || getSportPath();
    const tId = String(teamId || getFavoriteTeamId());

    const liveCandidates = events.filter(ev => {
        const comp = ev?.competitions?.[0];
        if (!comp) return false;
        const state = comp.status?.type?.state || ev.status?.type?.state;
        if (state === 'in') return true;
        if (state === 'pre' && isGameInLiveWindow(ev.date || comp.date)) return true;
        return false;
    });

    if (liveCandidates.length === 0) return events;

    await Promise.all(liveCandidates.map(async (ev) => {
        const comp = ev.competitions?.[0];
        const gameId = comp?.id || ev.id;
        if (!gameId) return;
        try {
            const summaryUrl = `https://site.api.espn.com/apis/site/v2/sports/basketball/${encodeURIComponent(sPath)}/summary?event=${encodeURIComponent(gameId)}`;
            const res = await fetch(summaryUrl);
            if (!res || !res.ok) return;
            const summary = await res.json();
            if (!summary) return;
            ev._liveSummary = summary;
            const resolved = resolveScheduleGameStatus(ev, summary, tId);
            if (comp.status && summary.header?.competitions?.[0]?.status) {
                comp.status = summary.header.competitions[0].status;
            }
            if (Array.isArray(comp.competitors)) {
                comp.competitors.forEach(c => {
                    const isMyTeam = String(c?.team?.id ?? c?.id) === tId;
                    const resolvedScore = isMyTeam ? resolved.myScore : resolved.oppScore;
                    if (resolvedScore !== null && resolvedScore !== undefined) {
                        c.score = {
                            value: Number(resolvedScore) || 0,
                            displayValue: String(resolvedScore)
                        };
                    }
                    if (resolved.state === 'post' && isMyTeam) {
                        c.winner = Boolean(resolved.isWin);
                    }
                });
            }
        } catch (err) {
            console.warn(`Failed to hydrate live schedule event ${gameId}:`, err);
        }
    }));

    return events;
}

async function fetchTeamSchedule(sportPath, teamId) {
    const sPath = sportPath || getSportPath();
    const tId = teamId || getFavoriteTeamId();
    const baseUrl = `https://site.api.espn.com/apis/site/v2/sports/basketball/${sPath}/teams/${tId}/schedule`;

    try {
        let data = null;
        try {
            const response = await fetch(baseUrl);
            if (response.ok) {
                data = await response.json();
            }
        } catch (fetchErr) {
            console.warn('Initial schedule fetch failed:', fetchErr);
        }

        let events = data?.events || [];
        // In NCAA college basketball, ESPN often defaults the season phase to Preseason (seasontype=1)
        // in October, which contains 0 events. The regular season schedule is under seasontype=2.
        const isPreseasonOnly = (data?.season && data.season.type === 1) && (!data.requestedSeason || data.requestedSeason.type === 1);
        if (events.length === 0 || isPreseasonOnly) {
            try {
                const regResponse = await fetch(`${baseUrl}?seasontype=2`);
                if (regResponse.ok) {
                    const regData = await regResponse.json();
                    const regEvents = regData.events || [];
                    if (events.length === 0) {
                        data = regData;
                        events = data?.events || [];
                    } else if (regEvents.length > 0) {
                        const eventIds = new Set(events.map(e => String(e.id)));
                        regEvents.forEach(e => {
                            if (!eventIds.has(String(e.id))) {
                                events.push(e);
                                eventIds.add(String(e.id));
                            }
                        });
                        events.sort((a, b) => new Date(a.date) - new Date(b.date));
                        data.events = events;
                    }
                }
            } catch (regErr) {
                console.warn('Error fetching regular season schedule fallback:', regErr);
            }
        }
        if (data && Array.isArray(data.events) && data.events.length > 0) {
            await hydrateLiveScheduleEvents(data.events, sPath, tId);
        }
        return data || { events: [] };
    } catch (e) {
        console.error('Error fetching team schedule:', e);
    }
    return { events: [] };
}

async function fetchTeamRoster(sportPath, teamId) {
    const sPath = sportPath || getSportPath();
    const tId = teamId || getFavoriteTeamId();
    const rosterUrl = `https://site.api.espn.com/apis/site/v2/sports/basketball/${encodeURIComponent(sPath)}/teams/${encodeURIComponent(tId)}/roster`;

    try {
        const response = await fetch(rosterUrl);
        if (response.ok) {
            const data = await response.json();
            const athletes = data.athletes || data.team?.athletes || [];
            if (!data.team) data.team = {};
            if (!data.team.athletes) data.team.athletes = athletes;
            if (!data.athletes) data.athletes = athletes;
            return data;
        }
    } catch (err) {
        console.warn('Error fetching team roster from /roster endpoint:', err);
    }

    // Fallback attempt in case proxy/environment enables query param
    try {
        const fallbackUrl = `https://site.api.espn.com/apis/site/v2/sports/basketball/${encodeURIComponent(sPath)}/teams/${encodeURIComponent(tId)}?enable=roster`;
        const res = await fetch(fallbackUrl);
        if (res.ok) {
            const data = await res.json();
            const athletes = data.athletes || data.team?.athletes || [];
            if (!data.team) data.team = {};
            if (!data.team.athletes) data.team.athletes = athletes;
            if (!data.athletes) data.athletes = athletes;
            return data;
        }
    } catch (fallbackErr) {
        console.warn('Fallback roster fetch failed:', fallbackErr);
    }

    return null;
}


function getValTierClass(val) {
    const num = Number(val);
    if (isNaN(num)) return 'val-pill-low';
    if (num < 0) return 'val-pill-neg';
    if (num >= 30) return 'val-pill-high';
    if (num >= 15) return 'val-pill-mid';
    return 'val-pill-low';
}

const _bpiMapMemoryCache = {};
const _teamStatsMemoryCache = {};
const BPI_CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes

function formatRankToken(val, fallback = '-') {
    if (val === null || val === undefined || val === '' || val === '-') return fallback;
    const str = String(val).trim();
    if (!str || str === '-') return fallback;
    if (str.startsWith('#')) return str;
    const num = parseInt(str.replace(/^Tied-/i, ''), 10);
    if (!isNaN(num) && num > 0) return `#${num}`;
    return str;
}

async function fetchBpiAndResumeMap(sportPath) {
    const sPath = sportPath || getSportPath();
    if (_bpiMapMemoryCache[sPath]) {
        return _bpiMapMemoryCache[sPath];
    }

    const storageKey = `espn_bpi_map_v3_${sPath}`;
    try {
        const raw = sessionStorage.getItem(storageKey);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && parsed.ts && (Date.now() - parsed.ts < BPI_CACHE_TTL_MS) && parsed.map && Object.keys(parsed.map).length > 0) {
                const sample = Object.values(parsed.map)[0];
                // For Men's, only reuse sessionStorage if it came from the full BPI endpoint
                if (sPath !== 'mens-college-basketball' || sample?.source === 'BPI') {
                    _bpiMapMemoryCache[sPath] = parsed.map;
                    return parsed.map;
                }
            }
        }
    } catch (e) {}

    const map = {};

    // Primary: ESPN FITT Power Index (BPI) endpoint (try both site.api.espn.com and site.web.api.espn.com)
    const bpiUrls = [
        `https://site.api.espn.com/apis/fitt/v3/sports/basketball/${encodeURIComponent(sPath)}/powerindex?region=us&lang=en&limit=400`,
        `https://site.web.api.espn.com/apis/fitt/v3/sports/basketball/${encodeURIComponent(sPath)}/powerindex?region=us&lang=en&limit=400`
    ];

    for (const bpiUrl of bpiUrls) {
        if (Object.keys(map).length > 0) break;
        try {
            const response = await fetch(bpiUrl);
            if (response.ok) {
                const data = await response.json();
                const teams = data?.teams || [];
                teams.forEach(item => {
                    const tId = item?.team?.id ? String(item.team.id) : null;
                    if (!tId) return;
                    const bpiCat = (item.categories || []).find(c => c.name === 'bpi');
                    const resumeCat = (item.categories || []).find(c => c.name === 'resume');
                    const rankNum = Number(item.team.rankValue) || Number(bpiCat?.values?.[1]) || null;
                    if (rankNum && rankNum > 0) {
                        const rawSos = resumeCat?.values?.[5] ?? resumeCat?.totals?.[5] ?? resumeCat?.ranks?.[5] ?? '-';
                        const rawSor = resumeCat?.values?.[0] ?? resumeCat?.totals?.[0] ?? resumeCat?.ranks?.[0] ?? '-';
                        const rawRemSos = bpiCat?.values?.[6] ?? bpiCat?.totals?.[6] ?? bpiCat?.ranks?.[6] ?? '-';
                        const rawNonConfSos = resumeCat?.values?.[6] ?? resumeCat?.totals?.[6] ?? resumeCat?.ranks?.[6] ?? '-';

                        map[tId] = {
                            rank: rankNum,
                            rankDisplay: `#${rankNum}`,
                            bpi: bpiCat?.totals?.[0] ?? '-',
                            offRank: formatRankToken(bpiCat?.ranks?.[3]),
                            defRank: formatRankToken(bpiCat?.ranks?.[4]),
                            remSosRank: formatRankToken(rawRemSos),
                            sorRank: formatRankToken(rawSor),
                            sosRank: formatRankToken(rawSos),
                            nonConfSosRank: formatRankToken(rawNonConfSos),
                            projW: bpiCat?.totals?.[9] || null,
                            projL: bpiCat?.totals?.[10] || null,
                            source: 'BPI'
                        };
                    }
                });
            }
        } catch (err) {
            console.warn('BPI endpoint attempt failed:', bpiUrl, err);
        }
    }

    // Fallback (e.g. Women's College Basketball when ESPN powerindex returns 400):
    // Rank all Division I teams using ESPN national standings (AP Rank + Win % + Avg Point Differential)
    if (Object.keys(map).length === 0) {
        try {
            const stRes = await fetch(`https://site.api.espn.com/apis/v2/sports/basketball/${encodeURIComponent(sPath)}/standings`);
            if (stRes.ok) {
                const stData = await stRes.json();
                const allEntries = [];
                (stData.children || []).forEach(conf => {
                    const entries = conf.standings?.entries || [];
                    entries.forEach(entry => {
                        if (!entry?.team?.id) return;
                        const stats = entry.stats || [];
                        const getStatVal = (type) => {
                            const s = stats.find(x => x.type === type || x.name === type);
                            return s && s.value !== undefined ? Number(s.value) : 0;
                        };
                        const winPct = getStatVal('winpercent');
                        const wins = getStatVal('wins');
                        const losses = getStatVal('losses');
                        const vsApWins = getStatVal('vsaprankedteams_wins');
                        const ppg = getStatVal('avgpointsfor');
                        const oppPpg = getStatVal('avgpointsagainst');
                        const margin = ppg - oppPpg;
                        const apRank = Number(entry.team.rank) || 999;
                        const ratingScore = (apRank <= 25 ? (30 - apRank) * 2.5 : 0) + (winPct * 25) + (margin * 0.6);
                        const sorScore = (wins * 12) - (losses * 8) + (winPct * 35) + (vsApWins * 15) + (margin * 0.35);
                        allEntries.push({
                            id: String(entry.team.id),
                            ratingScore,
                            sorScore,
                            margin
                        });
                    });
                });

                const bySor = [...allEntries].sort((a, b) => b.sorScore - a.sorScore);
                const sorRankById = {};
                bySor.forEach((item, idx) => {
                    sorRankById[item.id] = `#${idx + 1}`;
                });

                allEntries.sort((a, b) => b.ratingScore - a.ratingScore);
                allEntries.forEach((item, idx) => {
                    const r = idx + 1;
                    map[item.id] = {
                        rank: r,
                        rankDisplay: `#${r}`,
                        bpi: item.margin >= 0 ? `+${item.margin.toFixed(1)}` : item.margin.toFixed(1),
                        offRank: '-',
                        defRank: '-',
                        remSosRank: '-',
                        sorRank: sorRankById[item.id] || `#${r}`,
                        sosRank: '-',
                        nonConfSosRank: '-',
                        projW: null,
                        projL: null,
                        source: 'PWR'
                    };
                });
            }
        } catch (fallbackErr) {
            console.warn('Fallback standings power rank failed:', fallbackErr);
        }
    }

    if (Object.keys(map).length > 0) {
        _bpiMapMemoryCache[sPath] = map;
        const sample = Object.values(map)[0];
        if (sPath !== 'mens-college-basketball' || sample?.source === 'BPI') {
            try {
                sessionStorage.setItem(storageKey, JSON.stringify({ ts: Date.now(), map }));
            } catch (e) {}
        }
    }

    return map;
}

function calculateScheduleSosSummary(events, teamId, bpiMap) {
    if (!Array.isArray(events) || !bpiMap) {
        return { sosRank: '-', remSosRank: '-', avgOppRank: null };
    }

    const totalTeams = Object.keys(bpiMap).length || 363;
    const playedEffRanks = [];
    const remEffRanks = [];
    const allRawRanks = [];

    events.forEach(event => {
        const game = event?.competitions?.[0];
        if (!game) return;
        const myTeam = (game.competitors || []).find(c => String(c.team?.id) === String(teamId));
        const opponent = (game.competitors || []).find(c => String(c.team?.id) !== String(teamId));
        if (!myTeam || !opponent?.team?.id) return;

        const oppBpi = bpiMap[String(opponent.team.id)];
        if (!oppBpi || !oppBpi.rank) return;

        const isNeutral = Boolean(game.neutralSite);
        const isHome = !isNeutral && myTeam.homeAway === 'home';
        const locWeight = isNeutral ? 1.0 : (isHome ? 1.12 : 0.88);
        const effRank = oppBpi.rank * locWeight;

        allRawRanks.push(oppBpi.rank);
        if (game.status?.type?.state === 'post' || game.status?.type?.completed) {
            playedEffRanks.push(effRank);
        } else {
            remEffRanks.push(effRank);
        }
    });

    const toNationalSosRank = (effRanks) => {
        if (!effRanks || effRanks.length === 0) return '-';
        const avgEff = effRanks.reduce((a, b) => a + b, 0) / effRanks.length;
        // Map average opponent rank (~55 toughest to ~285 easiest across D1 schedules) onto 1..totalTeams
        const normalized = (avgEff - 55) / (285 - 55);
        const estRank = Math.max(1, Math.min(totalTeams, Math.round(normalized * (totalTeams - 1) + 1)));
        return `#${estRank}`;
    };

    const primaryRanks = playedEffRanks.length > 0 ? playedEffRanks : remEffRanks;
    const avgOppRank = allRawRanks.length > 0
        ? Math.round(allRawRanks.reduce((a, b) => a + b, 0) / allRawRanks.length)
        : null;

    return {
        sosRank: toNationalSosRank(primaryRanks),
        remSosRank: toNationalSosRank(remEffRanks),
        avgOppRank
    };
}

function getGameQuadrant(oppRank, isHome, isNeutral) {
    const rank = Number(oppRank);
    if (!rank || isNaN(rank) || rank <= 0) return null;

    let quad = 4;
    let locationLabel = 'Home';
    let rangeLabel = '161+';

    if (isNeutral) {
        locationLabel = 'Neutral';
        if (rank <= 50) { quad = 1; rangeLabel = '1–50'; }
        else if (rank <= 100) { quad = 2; rangeLabel = '51–100'; }
        else if (rank <= 200) { quad = 3; rangeLabel = '101–200'; }
        else { quad = 4; rangeLabel = '201+'; }
    } else if (isHome) {
        locationLabel = 'Home';
        if (rank <= 30) { quad = 1; rangeLabel = '1–30'; }
        else if (rank <= 75) { quad = 2; rangeLabel = '31–75'; }
        else if (rank <= 160) { quad = 3; rangeLabel = '76–160'; }
        else { quad = 4; rangeLabel = '161+'; }
    } else {
        locationLabel = 'Away';
        if (rank <= 75) { quad = 1; rangeLabel = '1–75'; }
        else if (rank <= 135) { quad = 2; rangeLabel = '76–135'; }
        else if (rank <= 240) { quad = 3; rangeLabel = '136–240'; }
        else { quad = 4; rangeLabel = '241+'; }
    }

    return {
        quad,
        label: `Q${quad}`,
        className: `quad-pill-q${quad}`,
        oppRank: rank,
        locationLabel,
        rangeLabel,
        tooltip: `Quad ${quad} (${locationLabel} vs #${rank} BPI · Q${quad} cutoff: ${locationLabel} ${rangeLabel})`
    };
}

function calculateScheduleQuadSummary(events, teamId, bpiMap) {
    const summary = {
        1: { w: 0, l: 0, rem: 0, pct: null, games: [] },
        2: { w: 0, l: 0, rem: 0, pct: null, games: [] },
        3: { w: 0, l: 0, rem: 0, pct: null, games: [] },
        4: { w: 0, l: 0, rem: 0, pct: null, games: [] }
    };

    if (!Array.isArray(events) || !bpiMap) return summary;

    events.forEach(event => {
        const game = event?.competitions?.[0];
        if (!game) return;
        const myTeam = (game.competitors || []).find(c => String(c.team?.id) === String(teamId));
        const opponent = (game.competitors || []).find(c => String(c.team?.id) !== String(teamId));
        if (!myTeam || !opponent?.team?.id) return;

        const oppBpi = bpiMap[String(opponent.team.id)];
        if (!oppBpi || !oppBpi.rank) return;

        const isNeutral = Boolean(game.neutralSite);
        const isHome = !isNeutral && myTeam.homeAway === 'home';
        const qInfo = getGameQuadrant(oppBpi.rank, isHome, isNeutral);
        if (!qInfo) return;

        const resolved = resolveScheduleGameStatus(event, event._liveSummary || null, teamId);
        const completed = Boolean(game.status?.type?.state === 'post' || game.status?.type?.completed || resolved.completed);
        const winner = completed ? Boolean(myTeam.winner ?? resolved.isWin) : false;
        const myScore = extractCompetitorScore(myTeam) ?? resolved.myScore;
        const oppScore = extractCompetitorScore(opponent) ?? resolved.oppScore;
        const score = (myScore !== null && oppScore !== null && myScore !== '' && oppScore !== '')
            ? `${myScore}-${oppScore}`
            : '';

        const bucket = summary[qInfo.quad];
        if (completed) {
            if (winner) {
                bucket.w++;
            } else {
                bucket.l++;
            }
        } else {
            bucket.rem++;
        }

        bucket.games.push({
            id: String(game.id || event.id || ''),
            opponentName: opponent.team?.shortDisplayName || opponent.team?.displayName || opponent.team?.name || 'Opponent',
            locationLabel: qInfo.locationLabel,
            oppRank: qInfo.oppRank,
            completed,
            winner,
            score,
            date: event.date || game.date || ''
        });
    });

    [1, 2, 3, 4].forEach(q => {
        const total = summary[q].w + summary[q].l;
        summary[q].pct = total > 0 ? Math.round((summary[q].w / total) * 100) : null;
    });

    return summary;
}

async function fetchTeamSeasonStats(sportPath, teamId) {
    const sPath = sportPath || getSportPath();
    const tId = String(teamId || getFavoriteTeamId());
    const cacheKey = `${sPath}_${tId}`;

    if (_teamStatsMemoryCache[cacheKey]) {
        return _teamStatsMemoryCache[cacheKey];
    }

    try {
        const url = `https://site.api.espn.com/apis/site/v2/sports/basketball/${encodeURIComponent(sPath)}/teams/${encodeURIComponent(tId)}/statistics`;
        const res = await fetch(url);
        if (!res.ok) return null;
        const data = await res.json();
        const categories = data?.results?.stats?.categories || data?.stats?.categories || [];
        const statMap = {};
        categories.forEach(cat => {
            (cat.stats || []).forEach(st => {
                if (st && st.name) {
                    statMap[st.name] = st.displayValue ?? st.value;
                }
            });
        });

        const parsed = {
            gp: statMap.gamesPlayed ?? '-',
            ppg: statMap.avgPoints ?? '-',
            fgPct: statMap.fieldGoalPct ? `${statMap.fieldGoalPct}%` : '-',
            threePtPct: statMap.threePointFieldGoalPct ? `${statMap.threePointFieldGoalPct}%` : '-',
            threePm: statMap.avgThreePointFieldGoalsMade ?? '-',
            ftPct: statMap.freeThrowPct ? `${statMap.freeThrowPct}%` : '-',
            reb: statMap.avgRebounds ?? '-',
            orb: statMap.avgOffensiveRebounds ?? '-',
            drb: statMap.avgDefensiveRebounds ?? '-',
            ast: statMap.avgAssists ?? '-',
            stl: statMap.avgSteals ?? '-',
            blk: statMap.avgBlocks ?? '-',
            to: statMap.avgTurnovers ?? '-',
            astToRatio: statMap.assistTurnoverRatio ?? '-'
        };

        _teamStatsMemoryCache[cacheKey] = parsed;
        return parsed;
    } catch (err) {
        console.warn(`Error fetching team season stats for ${tId}:`, err);
        return null;
    }
}
