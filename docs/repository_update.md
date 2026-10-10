# Repository Update

Update dated 2026-10-10, prepared on branch `chore/stage8-repository-update`.

The Git checkout is `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3`.
On 2026-10-10 the supported pipeline, documentation, and tests were also
synchronized to `E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3`.
The E-drive folder contains code and data but has no `.git` directory.
Run Git review/publish commands in the D-drive checkout. Runtime metadata
and local build products in the E-drive copy are retained on disk.

## Included

- Previously untracked Stage 8B/8C/8D and Stage 7A TXT merge entry points.
- Shared external-data/result path configuration for Stage 5 input loading
  and the supported Stage 7/8 entry points.
- Read-only Stage 7A dry run and no-op preservation of existing summaries.
- Stage 8D exclusion handling and safe empty selection.
- Stage 7/8 reports no longer mirrored into the input project's metadata.
- Explicit LAZ compression when writing through temporary files.
- Mixed-success/failure CSV writing in Stage 8B.
- Dependency baseline, setup/data documentation, and synthetic regressions.
- PowerShell path setup for combined code/data folders with sibling results.
- Ignore the E-drive copy's `时间修复_L1/` data directory as well.
- Locked core/transitive dependencies and a cross-platform Python bootstrap.
- Read-only external-data preflight and a single-sequence sample runner.
- Windows/Ubuntu CI using a clean install and synthetic pipeline tests.
- Deployment documentation for manually downloaded data.

## Excluded From Git

Point clouds, H5/MAT inputs and outputs, runtime manifests/reports, and
Visual Studio caches/build products are not part of the source update.
Existing tracked copies are removed from the **Git index only**, not disk.
C++ source, solution/project files, MATLAB source, and reference documentation
are retained, including the historical Stage 7D presentation notes.

This does not remove large files from previous commits or shrink existing
Git history. No history rewrite or force push is part of this update.
Old clones will still carry old blobs unless a separate migration is planned.
When another clone applies the deletion commit, Git may remove clean formerly
tracked copies there: back up/copy calibration and metadata to the external
data package before updating that clone.

## Verification

Verified locally on 2026-10-09 using Python 3.13.6:

- All 26 synthetic regression tests passed, including compressed LAZ
  round trips, export coordinates, exclusions, and read-only dry runs.
- Real Stage 7A dry run: 101 files in scope, 95 existing outputs, 6 bad-time
  exclusions, and 0 selected files.
- Real Stage 8D dry run: 447 L1 files, 417 existing TXT files, 30 exclusions,
  and 0 selected files.
- SHA-256 checks of 278 metadata, manifest, and report files were unchanged
  before and after the real dry runs.
- Recomputed all geometry fields for the first 10,000 points of sequence
  00111; every field exactly matched the archived Stage 7A array.
- Applied the default denoising mask to the complete archived 00111 array:
  2,326,241 source points and 1,513,060 retained points. Retained point
  indexes exactly matched the archived Stage 8A output.

The real-data checks were read-only. They are not a full mission rerun or a
new scientific validation of the geometry model. Legacy MATLAB/C++ projects
were not built. A clean clone still needs the separately copied data package.

On 2026-10-10, all 26 tests also passed when run from the synchronized
E-drive code folder. Its Stage 7A/8D dry runs reproduced the selection counts
above using `scripts/use-local-data.ps1`. Across synchronization and testing,
2,487 data/result files retained their sizes and modification timestamps;
SHA-256 checks of 370 metadata files also matched. The nine replaced E-drive
files were backed up under the sibling `_source_backups/` directory before
copying. Four unrelated legacy scripts retain their original E-drive paths.

## Deployment Checks

The deployment entry point is `python scripts/bootstrap.py` with 64-bit
Python 3.13. It installs in `.venv`, runs `pip check`, verifies the locked
dependencies/LAZ backend, and runs all synthetic tests. It never downloads
mission data. See `deployment.md` for setup and manual data installation.

`scripts/doctor.py` checks external inputs without creating result files.
`scripts/run_sample.py` runs 7A -> 8A -> 8B -> 8C in a new result directory,
stopping on failure. The deployment tests exercise raw synthetic L1/POS/MAT
inputs through all these stages and compare the independent 8D export.

On 2026-10-10, an export containing only the proposed Git source tree was
installed into a fresh Python 3.13.6 virtual environment on Windows x64.
The dependency check, software doctor, and all 36 tests passed. The input
doctor also passed for the 95 status=OK files in scope 00050-00150.

Using that clean installation and the external inputs, `run_sample.py`
completed the full real sequence 00111 in a new validation directory:

- Stage 7A H5: 2,326,241 points; LAZ/TXT export: 1,924,609 points.
- Stage 8A denoised H5/LAZ: 1,513,060 points.
- Stage 8B local-coordinate TXT: all 1,513,060 retained points.
- Stage 8C intermediate H5: 2,326,241 points; filtered TXT: 1,540,533 points.

This verifies a complete single-file deployment run, not a full mission
rerun or final scientific acceptance. The archived results remain separate.
The GitHub workflow repeats clean installation and synthetic tests on
Windows/Ubuntu; check the workflow result for the commit being deployed.

## Repository Maintenance

From the actual Git checkout, not the external result directory:

```powershell
git status --short
git diff --cached --stat
git diff --cached --check
python -m unittest discover -s tests -v
```

Publish source updates to the default `main` branch after verification.
Do not force-push or add ignored data with `git add -f`. Data is always
downloaded/copied manually outside Git. Keep the external dataset backup
when updating an existing clone that previously tracked runtime inputs.
