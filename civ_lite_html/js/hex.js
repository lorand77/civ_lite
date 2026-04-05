// ============================================================
// hex.js — Hex grid math + canvas renderer
// Pointy-top axial coordinate system, matching civ_lite_py.
// ============================================================

const HEX_SIZE = 48; // center-to-corner in pixels

// --- Axial math ---

function axialRound(q, r) {
    const s = -q - r;
    let rq = Math.round(q), rr = Math.round(r), rs = Math.round(s);
    const dq = Math.abs(rq - q), dr = Math.abs(rr - r), ds = Math.abs(rs - s);
    if (dq > dr && dq > ds)      rq = -rr - rs;
    else if (dr > ds)            rr = -rq - rs;
    return [rq, rr];
}

function hexToPixel(q, r, hexSize = HEX_SIZE) {
    const x = hexSize * (Math.sqrt(3) * q + Math.sqrt(3) / 2 * r);
    const y = hexSize * (3 / 2 * r);
    return [x, y];
}

function pixelToHex(px, py, hexSize = HEX_SIZE) {
    const q = (Math.sqrt(3) / 3 * px - 1 / 3 * py) / hexSize;
    const r = (2 / 3 * py) / hexSize;
    return axialRound(q, r);
}

const HEX_DIRECTIONS = [[1,0],[1,-1],[0,-1],[-1,0],[-1,1],[0,1]];

function hexNeighbors(q, r) {
    return HEX_DIRECTIONS.map(([dq, dr]) => [q + dq, r + dr]);
}

function hexDistance(q1, r1, q2, r2) {
    return (Math.abs(q1 - q2) + Math.abs(q1 + r1 - q2 - r2) + Math.abs(r1 - r2)) / 2;
}

function hexCorners(cx, cy, hexSize = HEX_SIZE) {
    const corners = [];
    for (let i = 0; i < 6; i++) {
        const angle = Math.PI / 180 * (60 * i - 30);
        corners.push([cx + hexSize * Math.cos(angle), cy + hexSize * Math.sin(angle)]);
    }
    return corners;
}

// --- Terrain colors (matching Python TERRAIN_COLORS) ---

const TERRAIN_COLORS = {
    grassland: '#6aa84f',
    plains:    '#b6d7a8',
    hills:     '#996633',
    forest:    '#274f13',
    ocean:     '#1e5ab4',
};

const TERRAIN_STROKE = {
    grassland: '#4a8a33',
    plains:    '#90ba88',
    hills:     '#7a4f22',
    forest:    '#1a380d',
    ocean:     '#163f8a',
};

// Resource dot colors (matches Python RESOURCE_COLORS)
const RESOURCE_COLORS = {
    iron:     '#a0a0a0',
    horses:   '#c8a064',
    gold:     '#ffd700',
    silver:   '#c0c0c0',
    diamonds: '#b4e6ff',
};

// --- Demo map generation (placeholder until mapgen.js) ---
// Generates a small hex-ring map with pseudo-random terrain.

function makeDemoMap(radius = 12) {
    const tiles = new Map();
    const terrains = ['grassland', 'grassland', 'plains', 'plains', 'hills', 'forest', 'ocean'];

    // Simple seeded-ish noise using position
    function terrainAt(q, r) {
        const v = Math.sin(q * 1.7 + r * 3.1) * 0.5 + Math.cos(q * 2.3 - r * 1.9) * 0.5;
        const n = (v + 1) / 2; // 0..1
        if (n < 0.12) return 'ocean';
        if (n < 0.30) return 'plains';
        if (n < 0.50) return 'grassland';
        if (n < 0.68) return 'hills';
        if (n < 0.82) return 'forest';
        return 'grassland';
    }

    for (let dq = -radius; dq <= radius; dq++) {
        for (let dr = Math.max(-radius, -dq - radius); dr <= Math.min(radius, -dq + radius); dr++) {
            tiles.set(`${dq},${dr}`, { q: dq, r: dr, terrain: terrainAt(dq, dr) });
        }
    }
    return tiles;
}

// --- Renderer ---

class HexRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');

        // Viewport state
        this.offsetX = 0;
        this.offsetY = 0;
        this.scale = 1.0;

        // Pan state
        this._dragging = false;
        this._dragStartX = 0;
        this._dragStartY = 0;
        this._dragOriginX = 0;
        this._dragOriginY = 0;

        this.tiles = new Map();

        this._bindEvents();
        this._centerView();
    }

    loadTiles(tiles) {
        this.tiles = tiles;
        this._centerView();
        this.draw();
    }

    _centerView() {
        // Center the grid (q=0,r=0) in the canvas
        this.offsetX = this.canvas.width / 2;
        this.offsetY = this.canvas.height / 2;
    }

    // Convert world hex coords → screen pixel
    _worldToScreen(wx, wy) {
        return [wx * this.scale + this.offsetX, wy * this.scale + this.offsetY];
    }

    // Convert screen pixel → world pixel
    _screenToWorld(sx, sy) {
        return [(sx - this.offsetX) / this.scale, (sy - this.offsetY) / this.scale];
    }

    draw() {
        const ctx = this.ctx;
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Background
        ctx.fillStyle = '#0a0a1a';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        const hexSize = HEX_SIZE * this.scale;

        for (const tile of this.tiles.values()) {
            const [wx, wy] = hexToPixel(tile.q, tile.r, HEX_SIZE);
            const [sx, sy] = this._worldToScreen(wx, wy);

            // Cull tiles fully off-screen
            if (sx < -hexSize * 2 || sx > this.canvas.width + hexSize * 2) continue;
            if (sy < -hexSize * 2 || sy > this.canvas.height + hexSize * 2) continue;

            this._drawHex(sx, sy, hexSize, tile);
        }
    }

    _drawHex(cx, cy, hexSize, tile) {
        const ctx = this.ctx;
        const { terrain, resource } = tile;
        const corners = hexCorners(cx, cy, hexSize);

        ctx.beginPath();
        ctx.moveTo(corners[0][0], corners[0][1]);
        for (let i = 1; i < 6; i++) ctx.lineTo(corners[i][0], corners[i][1]);
        ctx.closePath();

        ctx.fillStyle = TERRAIN_COLORS[terrain] ?? '#888';
        ctx.fill();

        ctx.strokeStyle = TERRAIN_STROKE[terrain] ?? '#555';
        ctx.lineWidth = Math.max(0.5, hexSize * 0.03);
        ctx.stroke();

        // Resource dot
        if (resource && RESOURCE_COLORS[resource]) {
            const dotR = Math.max(3, hexSize * 0.14);
            ctx.beginPath();
            ctx.arc(cx, cy, dotR, 0, Math.PI * 2);
            ctx.fillStyle = RESOURCE_COLORS[resource];
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,0,0,0.5)';
            ctx.lineWidth = Math.max(0.5, dotR * 0.25);
            ctx.stroke();
        }
    }

    // --- Events ---

    _bindEvents() {
        const canvas = this.canvas;

        canvas.addEventListener('mousedown', e => {
            if (e.button !== 0) return;
            this._dragging = true;
            this._dragStartX = e.clientX;
            this._dragStartY = e.clientY;
            this._dragOriginX = this.offsetX;
            this._dragOriginY = this.offsetY;
            canvas.style.cursor = 'grabbing';
        });

        canvas.addEventListener('mousemove', e => {
            if (!this._dragging) return;
            this.offsetX = this._dragOriginX + (e.clientX - this._dragStartX);
            this.offsetY = this._dragOriginY + (e.clientY - this._dragStartY);
            this.draw();
        });

        canvas.addEventListener('mouseup', () => {
            this._dragging = false;
            canvas.style.cursor = 'grab';
        });

        canvas.addEventListener('mouseleave', () => {
            this._dragging = false;
            canvas.style.cursor = 'grab';
        });

        // Zoom toward cursor
        canvas.addEventListener('wheel', e => {
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
            const newScale = Math.min(3.0, Math.max(0.2, this.scale * zoomFactor));

            // Adjust offset so zoom is centered on cursor position
            this.offsetX = mx - (mx - this.offsetX) * (newScale / this.scale);
            this.offsetY = my - (my - this.offsetY) * (newScale / this.scale);
            this.scale = newScale;

            this.draw();
        }, { passive: false });

        // Resize canvas to fill window
        window.addEventListener('resize', () => this._onResize());
    }

    _onResize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.draw();
    }

    // Returns the hex tile the screen point (sx, sy) falls on, or null
    hexAtScreen(sx, sy) {
        const [wx, wy] = this._screenToWorld(sx, sy);
        const [q, r] = pixelToHex(wx, wy, HEX_SIZE);
        return this.tiles.get(`${q},${r}`) ?? null;
    }
}
