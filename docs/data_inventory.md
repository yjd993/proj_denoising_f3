# 0510_f3 Data Inventory

Checked on 2026-06-24.

## L1 Source Products

- Directory: `0510_f3/L1-TIME_ANGE_DIST_DATA/`
- File type: HDF5 (`L1_cap_*.h5`)
- Count: 447 files
- Total size: about 106.64 GiB
- Sequence range: `00002` to `00449`
- Missing sequence: `000308`
- Time range by filename: `2026-05-10 19:04:25` to `2026-05-10 19:27:03`

Typical L1 datasets:

- `GNSS_SEC_CH1` to `GNSS_SEC_CH4`
- `Photon_CH1_DIST` to `Photon_CH4_DIST`
- `Photon_CH1_CODER` to `Photon_CH4_CODER`
- `PULSE_INDEX_CH1` to `PULSE_INDEX_CH4`
- `PULSE_CIRCLE_CH1` to `PULSE_CIRCLE_CH4`
- `STATUS/HasGNSS`
- `STATUS/HasPPS`

## MATLAB Conversion Code

- Directory: `untitled/`
- Main scripts:
  - `R_STEP_01_RESAVE_DATA_PARALLEL_SCRIPT.m`: PCAP to L1 HDF5
  - `R_STEP_02_CAL_XYZ_PARALLEL_for_correct_POS.m`: L1 to body-frame XYZ
- Helper functions:
  - `F_BodyFrame_XYZ.m`
  - `calibrate_range.m`
  - `findZeroPeak.m`
- Calibration files:
  - `calib_coeffs.mat`
  - `COEFFS_20260106.mat`

MATLAB static checks did not report syntax errors. The scripts still contain hard-coded original paths and should be parameterized before batch reprocessing.

## POS Data

- Directory: `0510_f3/POS_DATA/`
- POSPac project files are present.
- Raw GNSS/base files are present, including `.T04`, RINEX `.26O/.26P`, and precise orbit/navigation support files.
- SBET trajectory file is present:
  - `0510_f3/POS_DATA/0510f3prj/Mission 1/Proc/sbet_Mission 1.out`
  - Size: 46,361,856 bytes
  - Records: 340,896, assuming 17 little-endian doubles per record
  - Time coverage: second-of-day `39629.001` to `41333.476`

## Existing Georeferenced Preview Product

- File: `0510_f3/L3_DATA/L2_cap_00111_20260510190957.h5`
- Point count: 1,490,688
- Contains:
  - `POINT_X`, `POINT_Y`, `POINT_Z`
  - `LIDAR_X`, `LIDAR_Y`, `LIDAR_Z`
  - `LIDAR_LAT`, `LIDAR_LON`
  - `GNSS_SEC`
- Approximate location:
  - Longitude: `121.89742092426468`
  - Latitude: `30.88590409811461`
- Point height range: about `14.35 m` to `19.45 m`

This L3 file is sufficient for an immediate 3D geographic point-cloud preview.
