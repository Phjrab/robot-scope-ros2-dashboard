"""Opt-in local reference-pack installation; no network, robot or service calls."""
import argparse
import hashlib
import json
import shutil
import re
from pathlib import Path
from xml.etree import ElementTree


def install(pack: Path, target: Path) -> None:
    manifest = json.loads((pack / "data/asset_manifest.json").read_text())
    files = [manifest["map_asset"], *manifest["reference_assets"]]
    allowed = {"assets/maps/arena_schematic.svg", "assets/source/arena_p11_original.png", "assets/source/arena_p12_plan_original.png", "assets/source/arena_p13_top_original.png", "assets/source/arena_p14_underpass_original.png"}
    if {item["file"] for item in files} != allowed or len(files) != len(allowed):
        raise ValueError("only the five fixed reference assets are allowed")
    for item in files:
        path = pack / item["file"]
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("reference asset checksum mismatch")
        if path.suffix == ".svg":
            for node in ElementTree.fromstring(path.read_bytes()).iter():
                if node.tag.split("}")[-1] not in {"svg", "title", "desc", "defs", "pattern", "line", "rect", "path", "polygon", "g", "text", "circle"}:
                    raise ValueError("active SVG is prohibited")
                if any(k.lower().startswith("on") or "href" in k for k in node.attrib):
                    raise ValueError("SVG links are prohibited")
                if any(k in {"style", "{http://www.w3.org/XML/1998/namespace}base"} or ("url(" in v and not re.fullmatch(r"url\(#[A-Za-z0-9_-]+\)", v)) for k, v in node.attrib.items()):
                    raise ValueError("SVG external resources/styles are prohibited")
    target.mkdir(parents=True, exist_ok=True)
    for item in files:
        shutil.copyfile(pack / item["file"], target / Path(item["file"]).name)
    # Derived background omits static signal icons; the view owns exactly eight
    # toggleable UNKNOWN markers. Keep the original and its checksum untouched.
    tree = ElementTree.parse(target / "arena_schematic.svg")
    for parent in tree.iter():
        for node in list(parent):
            if node.get("id", "").startswith("signal-"):
                parent.remove(node)
    tree.write(target / "arena_background.svg", encoding="unicode")
    for name in ("asset_manifest.json", "schematic_template.json", "field_binding_template.json"):
        shutil.copyfile(pack / "data" / name, target / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    install(args.pack.resolve(), Path(__file__).resolve().parents[1] / "robot_dashboard/static/assets/competition/gangnam2026")
