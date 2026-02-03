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