function checkAuth() {
    if (localStorage.getItem('isLoggedIn') !== 'true') {
        window.location.href = '/College-Basketball-Stats/login';
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
    const logoLight = team.logos?.[0]?.href || team.logo;
    const logoDark = team.logos?.[1]?.href || logoLight;
    return `<img src="${logoLight}" class="team-logo logo-light" alt=""><img src="${logoDark}" class="team-logo logo-dark" alt="">`;
}