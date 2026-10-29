"""Sid the sloth - slothNtidy's pixel mascot, drawn as an SVG from a character grid.

Each letter in a grid row is one pixel. Three moods: sleeping (before sorting),
working (while sorting) and happy (when results are ready).
"""

PALETTE = {
    "B": "#7A4E33",  # fur
    "b": "#5E3A25",  # fur shadow
    "L": "#E8CBA2",  # face
    "D": "#3D2A1F",  # eye patches
    "K": "#16110E",  # eyes / mouth
    "W": "#FFFFFF",  # eye shine
    "P": "#E0675E",  # cheeks (deck coral)
    "T": "#C9463A",  # tongue
}

_TOP = [
    "....bbBBBBbb....",
    "..bBBBBBBBBBBb..",
    ".bBBBLLLLLLBBBb.",
    ".BBLLLLLLLLLLBB.",
]
_BOTTOM_ROWS = {
    "sleeping": [
        "BBLLDDDLLDDDLLBB",
        "BLLDDDDLLDDDDLLB",
        "BLLDKKDLLDKKDLLB",
        "BLLLLLLKKLLLLLLB",
        "BLPPLLLLLLLLPPLB",
        "BLLLLLLLLLLLLLLB",
        ".BLLLLKKKKLLLLB.",
    ],
    "working": [
        "BBLLDDDLLDDDLLBB",
        "BLLDKWDLLDKWDLLB",
        "BLLDKKDLLDKKDLLB",
        "BLLLLLLKKLLLLLLB",
        "BLPPLLLLLLLLPPLB",
        "BLLLLLKKKKLLLLLB",
        ".BLLLLLKKLLLLLB.",
    ],
    "happy": [
        "BBLLDDDLLDDDLLBB",
        "BLLDKKDLLDKKDLLB",
        "BLLKDDKLLKDDKLLB",
        "BLLLLLLKKLLLLLLB",
        "BLPPLKLLLLKLPPLB",
        "BLLLLKKKKKKLLLLB",
        ".BLLLLKTTKLLLLB.",
    ],
}
_CHIN = [
    ".BBLLLLLLLLLLBB.",
    "..bBBLLLLLLBBb..",
    "....bbBBBBbb....",
]


def sloth_svg(mood: str = "happy", px: int = 6) -> str:
    rows = _TOP + _BOTTOM_ROWS.get(mood, _BOTTOM_ROWS["happy"]) + _CHIN
    w, h = len(rows[0]), len(rows)
    rects = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in PALETTE:
                rects.append(f'<rect x="{x}" y="{y}" width="1.02" height="1.02" fill="{PALETTE[ch]}"/>')
    return (f'<svg class="sloth sloth-{mood}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w * px}" height="{h * px}" shape-rendering="crispEdges" role="img" '
            f'aria-label="Sid the sloth, {mood}">{"".join(rects)}</svg>')


def sloth_with_bubble(mood: str, message: str, px: int = 6, dark: bool = False) -> str:
    """The mascot with a dashed speech bubble next to it."""
    zz = '<span class="zz">z<b>z</b><i>z</i></span>' if mood == "sleeping" else ""
    cls = "bubble dark" if dark else "bubble"
    return (f'<div class="mascot">{zz}{sloth_svg(mood, px)}'
            f'<div class="{cls}">{message}</div></div>')
