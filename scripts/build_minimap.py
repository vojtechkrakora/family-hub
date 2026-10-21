"""Render the fixed local OSM extract: python scripts/build_minimap.py extract.osm.

Input: https://api.openstreetmap.org/api/0.6/map?bbox=14.690,49.334,14.737,49.380
Geographic data © OpenStreetMap contributors, ODbL 1.0.
No tiles or external renderer are used. Bounds must match the HTML data attributes.
"""

import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WEST, SOUTH, EAST, NORTH = 14.690, 49.334, 14.737, 49.380
WIDTH, HEIGHT = 400, 600


def project(lat: float, lon: float) -> tuple[float, float]:
    return (lon - WEST) / (EAST - WEST) * WIDTH, (NORTH - lat) / (NORTH - SOUTH) * HEIGHT


def build(source: Path) -> str:
    root = ET.parse(source).getroot()
    nodes = {
        n.attrib["id"]: project(float(n.attrib["lat"]), float(n.attrib["lon"]))
        for n in root.findall("node")
    }
    layers: dict[str, list[str]] = {key: [] for key in ["land", "water", "street", "road", "rail"]}
    for way in root.findall("way"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        refs = [nd.attrib["ref"] for nd in way.findall("nd")]
        if not all(ref in nodes for ref in refs):
            continue
        points = " ".join(f"{nodes[ref][0]:.1f},{nodes[ref][1]:.1f}" for ref in refs)
        if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
            layers["water"].append(f'<polygon points="{points}" fill="#284e62"/>')
        elif tags.get("waterway") in {"river", "stream"}:
            layers["water"].append(
                f'<polyline points="{points}" fill="none" stroke="#386c83" stroke-width="5"/>'
            )
        elif tags.get("landuse") in {"forest", "meadow", "grass"} or tags.get("natural") == "wood":
            layers["land"].append(f'<polygon points="{points}" fill="#294737"/>')
        elif tags.get("railway") == "rail":
            layers["rail"].append(
                f'<polyline points="{points}" fill="none" stroke="#c7b69d" stroke-width="2" stroke-dasharray="5 4"/>'
            )
        elif tags.get("highway") in {
            "primary",
            "secondary",
            "tertiary",
            "residential",
            "unclassified",
            "service",
        }:
            main = tags["highway"] in {"primary", "secondary", "tertiary"}
            layer, color, width = ("road", "#9cae9c", 4) if main else ("street", "#536b5e", 1.5)
            layers[layer].append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{width}"/>'
            )
    output = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 600">',
        "<title>Planá nad Lužnicí – místní mapa</title>",
        "<desc>© OpenStreetMap contributors, ODbL. Extract 2026-10-20. North up.</desc>",
        '<rect width="400" height="600" fill="#20382f"/>',
    ]
    for paths in layers.values():
        output.extend(paths)
    output.append('<g font-family="Arial,sans-serif" font-size="19" fill="#dbe6db">')
    output.append('<text x="18" y="32">PLANÁ NAD LUŽNICÍ</text><text x="20" y="580">S ↑</text>')
    for lat, lon, name, icon in [
        (49.349325, 14.70819, "Přejezd", "crossing"),
        (49.340534, 14.721553, "Naše zastávka", "stop"),
    ]:
        x, y = project(lat, lon)
        symbol = Path(f"homeboard/static/icons/{icon}.svg").read_text()
        inner = symbol[symbol.index(">") + 1 : symbol.rindex("</svg>")]
        output.append(f'<g transform="translate({x - 24:.1f} {y - 24:.1f})">{inner}</g>')
        output.append(
            f'<text x="{x - 12:.1f}" y="{y + 43:.1f}" text-anchor="end" stroke="#20382f" stroke-width="4" paint-order="stroke">{name}</text>'
        )
    output.extend(["</g>", "</svg>"])
    return "\n".join(output)


if __name__ == "__main__":
    svg = build(Path(sys.argv[1]))
    Path("homeboard/static/minimap.svg").write_text(svg)
    version = hashlib.sha256(svg.encode()).hexdigest()[:12]
    index = Path("homeboard/static/index.html")
    index.write_text(
        re.sub(
            r"/static/minimap\.svg(?:\?v=[a-f0-9]+)?",
            f"/static/minimap.svg?v={version}",
            index.read_text(),
        )
    )
