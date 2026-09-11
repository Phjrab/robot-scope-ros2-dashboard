# Grouped Route Planner order sheets

The editor now separates an order sheet from a menu line:

- One batch contains 1–5 order sheets.
- Each sheet has one destination and 1–5 restaurant/menu/quantity lines.
- Different restaurants can appear in the same sheet.
- Each line quantity remains an integer from 1 through 5.
- A batch can therefore hold 25 menu lines; line count is not quantity.

The new request field `orders` contains `{destination_id, lines}` sheets.
Each sheet's menu sequence is continuous from 1. Legacy `lines` input remains
supported with its previous validation and capacity rules. Mixed grouped and
legacy input is rejected. Catalog, same-zone exclusion and unknown-field
validation are unchanged.

Stored grouped orders retain the nested sheets and a bounded flattened line
projection for route consumers, including sheet/menu sequence provenance.
Revision hashing includes group boundaries. Update and explicit unlock preserve
all nested items. Existing saved flat orders remain readable by the editor.

## Capacity and recommendations

Input storage capacity is distinct from transport capacity. The existing
five-item carrying limit is not increased. A grouped batch exceeding five
units can be saved but single-trip recommendations fail with an explicit
split-delivery-required message. Automatic multi-trip delivery is not implemented.
Preparation times continue to follow the existing sequential 20-second-per-item
policy. No control, navigation, robot authority or execution endpoints were added.

## Validation

Tests cover 5x5 storage, group-aware revisions, continuous flattened preparation
times, empty/oversized/mixed requests, carrying-limit rejection, grouped update
and unlock, legacy contracts, and browser editing/saving of all 25 lines.
The existing browser route workflow assertions remain in place and request
assertions were updated for the new nested shape. Deployment is separate from
source publication; no robot service or active map was changed by this task.
