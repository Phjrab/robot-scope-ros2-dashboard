# Go2 EDU cargo plate prototype v1

Editable FreeCAD model, two interchangeable fabrication approaches (printed ribbed deck or acrylic flat deck), STEP/STL, 1:1 DXF/SVG cutting files, fit coupon, previews and geometric validation.

**Provisional prototype. Not physically printed, fitted, load tested or approved for robot motion.** Generic PC, router and battery shapes are placeholders. Unitree rail drawing dimensions support only the indicated rail dimensions; station locations, fasteners, equipment envelopes and clearance remain assumptions to confirm on the actual robot.

Start with [Korean fabrication and assembly notes](README_fabrication_ko.txt), then print the crossbar fit coupon and verify the actual rail nuts, plate dimensions, fasteners and equipment. STEP/STL contain the user-designed fabricated geometry; no vendor CAD or solver binaries are redistributed.

## File map
- `Go2CargoPlate_Provisional.FCStd`: editable parameters, feature history, assembly and generic equipment reference envelopes
- `01_*`: printed ribbed deck
- `02_*`: acrylic alternative, millimetre-scale DXF/SVG and STEP
- `03_*`: crossbar fit coupon
- `printed_deck_crossbar_assembly.step`: fabricated assembly
- `*.png`: design previews, not photographs of verified hardware
- `validation_report.json`, `external_cut_file_check.json`: geometric/export checks
- `*.FCMacro`: construction and verification sources; adjust their local output paths before running in FreeCAD
- `PUBLICATION_MANIFEST.json`: repository-relative byte counts and SHA-256/Git blob SHA-1 values

References and assumptions are preserved in the Korean notes. This folder is additive hardware documentation and does not change dashboard software or robot controls.
