# Stage 01 AOI Decision Log

## Decision

The initial Parcel A boundary is reconstructed from the seven vertices in the coordinate table of the final characterization report. The resulting polygon is stored as a `candidate` and is not treated as the approved project boundary until it is confirmed by the project owner or survey team.

## Evidence

- Source: final report titled *Caractérisation de la Parcelle A de Dir 1*
- Coordinate reference shown on the report map: `WGS 84 Zone 33N`
- Number of vertices: `7`
- Reported area: `5128.69 ha`
- Area calculated from the UTM polygon: `5127.480571516418 ha`
- Absolute difference: `1.209428483582 ha`
- Relative difference: approximately `0.02358%`

## Quality-gate rule

Quality gate `G0` changes to `PASS` only when:

1. The geometry is topologically valid and has no self-intersection.
2. The coordinate reference system is independently confirmed.
3. The polygon shape is matched against an official survey map or vector file.
4. The responsible project representative approves the boundary.

Until then, the candidate AOI can be used for location mapping, workflow design, and code testing, but not as the definitive basis for cultivated-area statistics, investment decisions, or block-level reporting.
