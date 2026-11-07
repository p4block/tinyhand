"""Stable built-in style metadata, matching the macOS app."""

STYLES = {
    'lavender': ('Lavender toy', 0x8754F2),
    'glove': ('Cursor glove', 0x8754F2),
    'coral': ('Coral vinyl', 0xFF453A),
    'plush': ('Plush', 0x2F86F0),
    'robot': ('Robot', 0x16A87A),
    'pink': ('Bubblegum', 0xEE4F98),
    'blue': ('Sky', 0x2F86F0),
    'mint': ('Mint', 0x16A87A),
    'lemon': ('Lemon', 0xF2B705),
    'black': ('Midnight', 0x1D1D21),
    'chrome': ('Chrome', 0x6B7380),
    'holo': ('Holo', 0x8754F2),
    'fuzzy': ('Fuzzy', 0x8754F2),
    'wood': ('Wood', 0x9A5E2C),
    'marble': ('Marble', 0x6B7380),
    'terrazzo': ('Terrazzo', 0xF0561D),
    'glass': ('Glass', 0x1597E5),
    'jelly': ('Jelly', 0xA33FE6),
    'pastel': ('Pastel', 0xEE4F98),
    'pixel': ('Pixel', 0x1D1D21),
    'lowpoly': ('Low poly', 0x8754F2),
    'knit': ('Knit', 0x8754F2),
    'skeleton': ('Skeleton', 0x9A5E2C),
    'astro': ('Astronaut', 0x2F86F0),
    'space': ('Space', 0xFF453A),
    'monster': ('Monster', 0x3E9E2E),
    'water': ('Water', 0x1597E5),
    'lava': ('Lava', 0xF0561D),
    'grass': ('Grass', 0x3E9E2E),
    'cactus': ('Cactus', 0x3E9E2E),
    'choco': ('Chocolate', 0x9A5E2C),
    'cloud': ('Cloud', 0x2F86F0),
    'mech': ('Mech', 0xF0561D),
    'neon': ('Neon', 0xE0309A),
    'leaf': ('Leaf', 0x3E9E2E),
    'cookie': ('Gingerbread', 0x9A5E2C),
    'laser': ('Laser dot', 0xFF453A),
}


def ink_color(style):
    color = STYLES[style][1]
    return tuple(((color >> shift) & 255) / 255 for shift in (16, 8, 0))
