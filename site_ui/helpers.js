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

function renderValBreakdownHtml(details, playerName, teamInfo) {
    if (!details) return '';
    const { pts, fg, threePt, ft, reb, ast, stl, blk, tov, total } = details;

    const netShooting = pts + threePt.m - fg.a + (fg.m * 2) - ft.a + ft.m;
    const fgPct = fg.a > 0 ? Math.round((fg.m / fg.a) * 100) : 0;
    const ftPct = ft.a > 0 ? Math.round((ft.m / ft.a) * 100) : 0;

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

    const scorePillClass = total > 0 ? 'val-positive' : (total < 0 ? 'val-negative' : 'val-neutral');
    const scorePillSign = total > 0 ? '+' : '';

    const mathString = `VAL = ${pts} (PTS) + ${threePt.m} (3PM) - ${fg.a} (FGA) + ${fg.m * 2} (2×FGM) - ${ft.a} (FTA) + ${ft.m} (FTM) + ${reb} (REB) + ${ast * 2} (2×AST) + ${stl * 4} (4×STL) + ${blk * 4} (4×BLK) - ${tov * 2} (2×TO) = ${total}`;

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

        <div class="val-formula-math-box">
            <code>${escapeHtml(mathString)}</code>
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
                        return regData;
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
                        return data;
                    }
                }
            } catch (regErr) {
                console.warn('Error fetching regular season schedule fallback:', regErr);
            }
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
