var firebaseConfig = {
    apiKey: "FIREBASE_API_KEY_PLACEHOLDER",
    authDomain: "FIREBASE_AUTH_DOMAIN_PLACEHOLDER",
    projectId: "FIREBASE_PROJECT_ID_PLACEHOLDER",
    storageBucket: "FIREBASE_STORAGE_BUCKET_PLACEHOLDER",
    messagingSenderId: "FIREBASE_MESSAGING_SENDER_ID_PLACEHOLDER",
    appId: "FIREBASE_APP_ID_PLACEHOLDER",
    measurementId: "FIREBASE_MEASUREMENT_ID_PLACEHOLDER"
};

var db, auth;

if (typeof firebase !== 'undefined') {
    if (!firebase.apps.length) {
        firebase.initializeApp(firebaseConfig);
    }
    db = firebase.firestore();
    auth = firebase.auth();
}

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
