#  This source file is part of the Avogadro project.
#  This source code is released under the 3-Clause BSD License, (see "LICENSE").

"""Generate Psi4 cubeprop input, run Psi4, and return the cube file."""

import glob
import os
import shutil
import subprocess
import tempfile

from avogadro_psi4_cubeprop.elements import element_symbols

# Map UI analysis names to Psi4 cubeprop task strings
TASK_MAP = {
    "ELF": "ELF",
    "LOL": "LOL",
    "Dual Descriptor": "DUAL_DESCRIPTOR",
}

INPUT_TEMPLATE = """\
molecule mol {{
{charge} {multiplicity}
{xyz_block}
no_reorient
no_com
}}

set basis {basis}
set scf_type df
set freeze_core True
set cubeprop_tasks ['{task}']
E, wfn = energy('{method}', return_wfn=True)
cubeprop(wfn)
"""


def cjson_to_xyz_block(cjson):
    """Convert CJSON atom data to an XYZ coordinate block."""
    numbers = cjson["atoms"]["elements"]["number"]
    coords = cjson["atoms"]["coords"]["3d"]
    lines = []
    for i, n in enumerate(numbers):
        x = coords[3 * i]
        y = coords[3 * i + 1]
        z = coords[3 * i + 2]
        symbol = element_symbols.get(n, "X")
        lines.append(f"  {symbol}  {x: .8f}  {y: .8f}  {z: .8f}")
    return "\n".join(lines)


def generate_input(cjson, options):
    """Build a Psi4 input file string from CJSON and user options."""
    analysis = options.get("analysis", "ELF")
    basis = options.get("basis", "cc-pVDZ")
    method = options.get("method", "B3LYP")

    task = TASK_MAP.get(analysis, "ELF")

    charge = cjson.get("properties", {}).get("totalCharge", 0)
    multiplicity = cjson.get("properties", {}).get("totalSpinMultiplicity", 1)
    xyz_block = cjson_to_xyz_block(cjson)

    return INPUT_TEMPLATE.format(
        charge=int(charge),
        multiplicity=int(multiplicity),
        xyz_block=xyz_block,
        basis=basis,
        task=task,
        method=method,
    )


def run(avo_input):
    """Run Psi4 cubeprop and return the resulting cube data."""
    cjson = avo_input.get("cjson", {})
    options = avo_input.get("options", {})

    if "atoms" not in cjson:
        return {"warning": "No molecule found. Please open a molecule or create one first."}

    # Check for psi4
    psi4_path = shutil.which("psi4")
    if psi4_path is None:
        return {"error": "Psi4 not found on PATH. Please install Psi4."}

    # Generate input
    input_text = generate_input(cjson, options)

    # Run in a temp directory
    work_dir = tempfile.mkdtemp(prefix="avogadro_psi4_")
    input_file = os.path.join(work_dir, "input.dat")
    output_file = os.path.join(work_dir, "output.dat")

    with open(input_file, "w") as f:
        f.write(input_text)

    try:
        result = subprocess.run(
            [psi4_path, input_file, "-o", output_file],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        if result.returncode != 0:
            # Try to extract a useful error from Psi4 output
            err_msg = result.stderr.strip() if result.stderr else ""
            if not err_msg and os.path.exists(output_file):
                with open(output_file) as f:
                    lines = f.readlines()
                # Look for error lines near the end
                for line in reversed(lines):
                    if "error" in line.lower() or "exception" in line.lower():
                        err_msg = line.strip()
                        break
            return {
                "warning": f"Psi4 calculation failed.\n{err_msg}",
            }

        # Find the cube file(s)
        cube_files = glob.glob(os.path.join(work_dir, "*.cube"))
        if not cube_files:
            return {"message": "Psi4 completed but no cube file was generated."}

        # Read the first cube file
        cube_file = cube_files[0]
        with open(cube_file) as f:
            cube_contents = f.read()

        analysis = options.get("analysis", "ELF")
        return {
            "readProperties": True,
            "moleculeFormat": "cube",
            "cube": cube_contents,
            "message": f"{analysis} calculation complete.",
        }

    except subprocess.TimeoutExpired:
        return {"warning": f"Psi4 calculation timed out (10 min limit).\n"
                           f"Files in: {work_dir}"}
