"""OpenFOAM file header/footer utilities."""

from __future__ import annotations

from pathlib import Path

HEADER = """\
/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2512                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

FOOTER = "\n// ************************************************************************* //\n"

FIELD_CLASS: dict[str, str] = {
    "U": "volVectorField",
    "p": "volScalarField",
    "k": "volScalarField",
    "omega": "volScalarField",
    "nut": "volScalarField",
    "Phi": "surfaceScalarField",
}


def foam_header(obj: str) -> str:
    """Generate OpenFOAM file header for a given object name."""
    return HEADER.format(cls=FIELD_CLASS.get(obj, "dictionary"), obj=obj)


def write_foam_file(path: Path, obj: str, content: str) -> None:
    """Write a complete OpenFOAM file with header and footer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(foam_header(obj) + content + FOOTER)


def bool_str(val: bool) -> str:
    """Convert Python bool to OpenFOAM bool string."""
    return "true" if val else "false"
