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