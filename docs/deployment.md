# Deployment

## Supported Workflow

This is a command-line Python project, not a web service. The deployment
entry point covers the CH1 `0510_f3` Stage 7/8 pipeline. Use 64-bit Python
3.13; Windows x64 / Python 3.13.6 is the local verification baseline.
The repository CI tests fresh installations on Windows and Ubuntu with
Python 3.13. MATLAB, legacy C++, and older diagnostic scripts have separate
toolchain/path requirements and are not covered by the bootstrap.

## Install Without Data

In PowerShell, after installing Python 3.13 and Git:

```powershell
git clone --depth 1 https://github.com/yjd993/proj_denoising_f3.git
cd proj_denoising_f3
py -3.13 scripts/bootstrap.py
```

No virtual-environment activation or PowerShell policy change is needed.
The bootstrap installs only from binary wheels, checks all pinned core
dependencies, and runs synthetic tests. It returns a nonzero exit status
if installation or tests fail. Re-running it reuses `.venv`; it refuses
unrelated directories and environments with system site packages enabled.
Network access to the Python package index is required for installation.

On Linux, install Python 3.13 with `venv` support and run:

```bash
python3.13 scripts/bootstrap.py
.venv/bin/python scripts/doctor.py --software-only
```

The exact direct and transitive versions live in `requirements-lock.txt`.
`requirements.txt` includes that file. These pins are an installation
baseline, not a hash-verified package archive. For optional presentation
generation, use the venv's Python:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-reporting.txt -c constraints-tested.txt
```

## Download Data Manually

Mission data is supplied separately by the project owner and is manually
downloaded/copied by the user. There is no automatic dataset downloader or
data download URL embedded in this repository.

The minimum input package for Stage 7A includes:

```text
<data-root>/
  0510_f3/
    L1-TIME_ANGE_DIST_DATA/L1_cap_XXXXX_YYYYMMDDhhmmss.h5
    0510f3_processed.mat
  untitled/calib_coeffs.mat
  metadata/l1_manifest_stage5_time_quality.csv
  outputs/qc/stage6i_ladm2_scan_geometry_diagnostic/best_candidate.json
```

These are real, matching mission inputs. H5 files alone are insufficient.
Use [the external data contract](external_data.md) for schemas and archived
result/exclusion files. The repository's example CSVs contain fabricated
format examples, not replacement mission inputs. A first run can start
without downloading old Stage 7/8 results.

In each new PowerShell session:

```powershell
$env:AIRBORNE_LIDAR_PROJECT_DATA_ROOT = "E:\lidar-data\proj_denoising_f3"
$env:AIRBORNE_LIDAR_STAGE_ROOT = "E:\lidar-results\new-run"
.\.venv\Scripts\python.exe scripts/doctor.py --start-seq 111 --end-seq 111
```

Or use `--data-root` and `--stage-root` on the doctor directly. On Linux:

```bash
export AIRBORNE_LIDAR_PROJECT_DATA_ROOT=/mnt/lidar-data/proj_denoising_f3
export AIRBORNE_LIDAR_STAGE_ROOT=/mnt/lidar-results/new-run
.venv/bin/python scripts/doctor.py --start-seq 111 --end-seq 111
```

The doctor is read-only. It validates dependency imports, MAT calibration
and POS fields, selected geometry parameters, manifest paths, L1 dataset
shapes, and sampled timestamps against POS coverage. It reports available
disk space without a write probe. An exit code of 0 means the checked scope
passed; 2 means a missing input or failed check. It does not read every
point, certify scientific accuracy, or verify all output permissions.
The default scope is 00050-00150. Stage 7A selection keeps `status=OK` only.
For Stage 8D use `--pipeline 8d --start-seq 1 --end-seq 99999` and, when
using a fresh result root, `--exclude-manifest PATH` to the archive's list.

## Run A Sample

Use a new result path that does not yet exist:

```powershell
.\.venv\Scripts\python.exe scripts/run_sample.py --seq 111 --output-root "E:\lidar-results\sample-00111-new"
```

On Linux replace the interpreter with `.venv/bin/python` and use a Linux
output path. `--data-root PATH` can replace the input environment variable.
The runner checks inputs, then runs 7A -> 8A -> 8B -> 8C with failure stops.
It creates H5/LAZ, denoised local-coordinate TXT, L2P exports, and reports.
It processes an entire sequence file; RAM demand exceeds the input H5 size
because several full point arrays are held concurrently. Judge capacity
from a single-file run before scaling up.

Review the result before a full batch. Run individual stage scripts with
`--help` for options. Stage 7A/8A outputs remain candidates for review.
Stage 8C is derived from the original 7A cloud, not from denoised 8A points.
Read the coordinate conventions in `external_data.md` before comparison.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Python version/architecture check fails | Install 64-bit Python 3.13 and rerun with that interpreter. |
| No binary wheel available | Verify Python 3.13, CPU/OS architecture, and package-index availability; CI covers Windows/Ubuntu x64. |
| A module or pinned version is missing | Rerun the bootstrap and use `.venv`'s Python for processing. |
| Doctor reports missing MAT/JSON/CSV | Copy the full external input package, not just L1 H5 files. |
| Doctor finds no OK files | Check the requested sequence and original manifest; do not relabel bad-time data. |
| POS coverage/schema validation fails | Verify matching mission inputs and review timing; do not bypass checks to claim readiness. |
| A result directory already exists | Use a new directory for the sample; preserve the archive. |
| Archived CSV contains old drive letters | Follow archive migration in `external_data.md`, or generate fresh results. |
| Process stops during a sample | Read the first failing stage and retain partial results for diagnosis; rerun into another fresh root after fixing the cause. |

## Existing Clones

Before pulling this update into an old clone, copy its calibration and
runtime metadata into the separately managed data package. This update
stops tracking those files; Git can delete formerly tracked clean copies
when applying the change in another checkout. Local runtime/build data is
ignored going forward.

Old commits still contain historical binaries. Use `git clone --depth 1`
for a small deployment checkout; this update does not rewrite history.
