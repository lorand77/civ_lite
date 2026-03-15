import math

HEX_SIZE = 72  # center-to-corner, pointy-top


def hex_to_pixel(q, r, offset_x=0, offset_y=0, hex_size=HEX_SIZE):
    """Convert axial hex coords to pixel center (x, y)."""
    x = hex_size * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
    y = hex_size * (3 / 2 * r)
    return (x + offset_x, y + offset_y)


def pixel_to_hex(px, py, offset_x=0, offset_y=0, hex_size=HEX_SIZE):
    """Convert pixel position to nearest axial hex coords."""
    px -= offset_x
    py -= offset_y
    q = (math.sqrt(3) / 3 * px - 1 / 3 * py) / hex_size
    r = (2 / 3 * py) / hex_size
    return axial_round(q, r)


def axial_round(q, r):
    """Round fractional axial coords to nearest hex."""
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return (rq, rr)


# 6 neighbors in axial coords (pointy-top)
HEX_DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def hex_neighbors(q, r):
    return [(q + dq, r + dr) for dq, dr in HEX_DIRECTIONS]


def hex_distance(q1, r1, q2, r2):
    return (abs(q1 - q2) + abs(q1 + r1 - q2 - r2) + abs(r1 - r2)) // 2


def hex_ring(q, r, radius):
    """All hex coords exactly `radius` steps from (q, r)."""
    results = []
    dq, dr = HEX_DIRECTIONS[4]
    hq, hr = q + dq * radius, r + dr * radius
    for i in range(6):
        for _ in range(radius):
            results.append((hq, hr))
            ddq, ddr = HEX_DIRECTIONS[i]
            hq += ddq
            hr += ddr
    return results


def hexes_in_range(q, r, n):
    """All hex coords within distance n (including center)."""
    results = []
    for dq in range(-n, n + 1):
        for dr in range(max(-n, -dq - n), min(n, -dq + n) + 1):
            results.append((q + dq, r + dr))
    return results


def hex_corners(cx, cy, hex_size=HEX_SIZE):
    """6 corner pixel positions for a pointy-top hex centered at (cx, cy)."""
    corners = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        corners.append((
            cx + hex_size * math.cos(angle),
            cy + hex_size * math.sin(angle),
        ))
    return corners


def offset_to_axial(col, row):
    q = col - (row - (row & 1)) // 2
    r = row
    return q, r
