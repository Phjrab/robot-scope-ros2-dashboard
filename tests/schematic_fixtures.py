"""Synthetic, test-only geometry; contains no private reference-pack assets.

Coordinates exercise the production semantic corridors, not surveyed locations.
The application never imports this fixture or uses it as a FIELD fallback.
"""
import json


def install_test_templates(target):
    target.mkdir()
    coordinates = {"A": [160, 150], "B": [890, 150], "C": [890, 660], "D": [160, 660]}
    nodes = [dict(id=name, label=name, x_px=p[0], y_px=p[1], role="INTERSECTION") for name, p in coordinates.items()]
    edges = []

    def edge(identifier, source, destination, kind, enabled=True, polyline=None):
        edges.append(dict(id=identifier, **{"from": source, "to": destination}, type=kind, bidirectional=True, enabled=enabled, polyline_px=polyline or [coordinates[source], coordinates[destination]]))

    for source, destination in [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]:
        edge("CROSS_" + source + destination, source, destination, "CROSSWALK")
    venues = []
    bindings = []
    for name, corner, position in [
        ("COEX", "A", [80, 90]), ("DOMINO", "A", [110, 100]),
        ("WHIMOON", "B", [880, 90]), ("HANSOT", "B", [950, 100]),
        ("GANGNAM_POLICE", "C", [880, 730]), ("EDIYA", "C", [950, 720]),
        ("GTX_SITE", "D", [80, 730]),
    ]:
        coordinates[name] = position
        role = "RESTAURANT" if name in {"DOMINO", "HANSOT", "EDIYA"} else "DESTINATION"
        nodes.append(dict(id=name, label="TEST " + name, x_px=position[0], y_px=position[1], role=role, venue_id=name))
        edge("ACCESS_" + name, corner, name, "WALKWAY")
        venues.append(dict(id=name, demo_corner=corner))
        bindings.append(dict(venue_id=name, corner=None, approach_point_px=None, dock_point_px=None, dock_yaw_rad=None))
    edge("UNDERPASS_TEST", "B", "C", "UNDERPASS", False, [coordinates["B"], [1080, 150], [1080, 660], coordinates["C"]])
    raw = dict(nodes=nodes, edges=edges, venues=venues, demo_corner_zone_binding=dict(A="ZONE1", B="ZONE2", C="ZONE3", D="ZONE4"))
    (target / "schematic_template.json").write_text(json.dumps(raw))
    (target / "field_binding_template.json").write_text(json.dumps(dict(venue_bindings=bindings)))
    return target
