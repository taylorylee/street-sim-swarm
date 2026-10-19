"""Gatherground palette, matched to the warm-paper reference render."""

PALETTE = {
    "ground":     "#EFECE4",  # warm paper
    "street":     "#E4DFD3",  # slightly darker paper for road beds
    "building":   "#FBFAF6",  # off-white tops
    "wall_light": "#EEEAE1",  # lit wall
    "wall_dark":  "#CFC8BA",  # shaded wall
    "park":       "#DCE6B4",  # soft olive-lime
    "tree":       "#B9C97A",  # tree dots
    "tree_dark":  "#5E6B2A",  # canopy / markers
    "accent":     "#4A4A10",  # deep olive (UI button)
    "marker":     "#7E5A86",  # muted plum pin
    "outline":    "#D2CCBF",
}


def rgba(hex_color: str, alpha: int = 255) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [alpha]


def rgb01(hex_color: str) -> tuple[float, float, float]:
    r, g, b, _ = rgba(hex_color)
    return (r / 255, g / 255, b / 255)
