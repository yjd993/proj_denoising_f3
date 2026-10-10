from __future__ import annotations

import contextlib
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import laspy
import numpy as np
from scipy.io import savemat


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import doctor


def make_inputs(root):
    l1 = root / "0510_f3/L1-TIME_ANGE_DIST_DATA/L1_cap_00111_20000101000000.h5"
    l1.parent.mkdir(parents=True)
    count = 128
    with h5py.File(l1, "w") as h5:
        h5["GNSS_SEC_CH1"] = np.linspace(82.1, 82.9, count)
        h5["Photon_CH1_DIST"] = np.full(count, 120000, dtype="u4")
        h5["Photon_CH1_CODER"] = np.full(count, 1000.0)
        h5["PULSE_INDEX_CH1"] = np.arange(count, dtype="u4")
        h5["PULSE_CIRCLE_CH1"] = np.zeros(count, dtype="u4")
        h5["Photon_Start_Count_CH1"] = np.arange(count, dtype=float)
    savemat(root / "0510_f3/0510f3_processed.mat", {
        "TIME": np.linspace(100, 102, 201),
        "EASTING": np.full(201, 394010.0),
        "NORTHING": np.full(201, 3417005.0),
        "HEIGHT": np.full(201, 150.0),
        "ROLL": np.zeros(201), "PITCH": np.zeros(201), "HEADING": np.zeros(201),
    })
    (root / "untitled").mkdir()
    savemat(root / "untitled/calib_coeffs.mat", {
        "calib_data": {"ch1": {"slope": 1.0, "intercept": 0.0}},
    })
    candidate = {
        "angle_direction": "angle", "angle_offset_deg": 0.0,
        "mirror_tilt_deg": 7.75, "frame_rotation_deg": 0.0,
        "axis_mapping": "F=+X,R=+Y,D=+Z", "axis_perm": [0, 1, 2],
        "axis_signs": [1, 1, 1], "boresight_roll_deg": 0.0,
        "boresight_pitch_deg": 0.0, "boresight_yaw_deg": 0.0,
        "lever_x_m": 0.0, "lever_y_m": 0.0, "lever_z_m": 0.0,
    }
    path = root / "outputs/qc/stage6i_ladm2_scan_geometry_diagnostic/best_candidate.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(candidate), encoding="utf-8")
    (root / "metadata").mkdir()
    with (root / "metadata/l1_manifest_stage5_time_quality.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file", "seq", "status"])
        writer.writeheader()
        writer.writerow({"file": l1.relative_to(root).as_posix(), "seq": 111, "status": "OK"})
    return l1


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "external inputs"
        self.output = self.root / "new results"
        self.l1 = make_inputs(self.data)

    def preflight(self, *extra):
        args = [
            "--data-root", str(self.data), "--stage-root", str(self.output),
            "--start-seq", "111", "--end-seq", "111", *extra,
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = doctor.main(args)
        return code, output.getvalue()

    def test_valid_data_preflight_is_readonly(self):
        before = {p: p.read_bytes() for p in self.data.rglob("*") if p.is_file()}
        code, output = self.preflight()
        self.assertEqual(code, 0, output)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, {p: p.read_bytes() for p in self.data.rglob("*") if p.is_file()})

    def test_missing_data_reports_actionable_paths(self):
        code, output = self.preflight("--data-root", str(self.root / "absent"))
        self.assertEqual(code, 2)
        for name in ("calib_coeffs.mat", "best_candidate.json", "0510f3_processed.mat", "l1_manifest"):
            self.assertIn(name, output)
        self.assertFalse(self.output.exists())

    def test_l1_shape_and_time_coverage_are_checked(self):
        with h5py.File(self.l1, "a") as h5:
            del h5["PULSE_CIRCLE_CH1"]
            h5["PULSE_CIRCLE_CH1"] = np.zeros(2)
        code, output = self.preflight()
        self.assertEqual(code, 2)
        self.assertIn("PULSE_CIRCLE_CH1", output)
        with h5py.File(self.l1, "a") as h5:
            del h5["PULSE_CIRCLE_CH1"]
            h5["PULSE_CIRCLE_CH1"] = np.zeros(128)
            h5["GNSS_SEC_CH1"][:] = 1.0
        code, output = self.preflight()
        self.assertEqual(code, 2)
        self.assertIn("outside POS coverage", output)

    def test_malformed_candidate_fails(self):
        path = self.data / "outputs/qc/stage6i_ladm2_scan_geometry_diagnostic/best_candidate.json"
        path.write_text('{"angle_direction": "invalid"}', encoding="utf-8")
        code, output = self.preflight()
        self.assertEqual(code, 2)
        self.assertIn("Geometry candidate", output)

    def test_nonportable_manifest_and_duplicate_sequences_fail(self):
        manifest = self.data / "metadata/l1_manifest_stage5_time_quality.csv"
        manifest.write_text("file,seq,status\nC:/old/L1.h5,111,OK\n", encoding="utf-8")
        code, output = self.preflight()
        self.assertEqual(code, 2)
        self.assertIn("relative to the data root", output)
        name = self.l1.relative_to(self.data).as_posix()
        manifest.write_text(f"file,seq,status\n{name},111,OK\n{name},111,OK\n", encoding="utf-8")
        code, output = self.preflight()
        self.assertEqual(code, 2)
        self.assertIn("duplicate sequence", output)

    def test_8d_missing_explicit_exclusions_fails(self):
        code, output = self.preflight(
            "--pipeline", "8d", "--exclude-manifest", str(self.root / "absent.csv"))
        self.assertEqual(code, 2)
        self.assertIn("absent.csv", output)

    def test_result_file_is_rejected(self):
        self.output.write_bytes(b"keep")
        code, output = self.preflight()
        self.assertEqual(code, 2)
        self.assertIn("Result root is a file", output)
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_bootstrap_refuses_unrelated_existing_directory(self):
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts/bootstrap.py"), "--venv", str(self.data)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-venv directory", result.stderr)
        self.assertTrue(self.l1.exists())

    def test_raw_l1_to_geometry_denoise_laz_and_exports_via_cli(self):
        env = os.environ.copy()
        env["AIRBORNE_LIDAR_PROJECT_DATA_ROOT"] = str(self.data)
        env["AIRBORNE_LIDAR_STAGE_ROOT"] = str(self.output)
        env.pop("AIRBORNE_LIDAR_EXCLUDE_MANIFEST", None)

        def run(name, *args):
            result = subprocess.run(
                [sys.executable, str(REPO / "scripts/processing" / name), *args],
                env=env, cwd=self.root, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        result = subprocess.run(
            [sys.executable, str(REPO / "scripts/run_sample.py"),
             "--data-root", str(self.data), "--output-root", str(self.output)],
            env=env, cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run("stage8d_ch1_l2p_missing_from_l1.py", "--start-seq", "111", "--end-seq", "111",
            "--output-root", str(self.root / "separate l2p"), "--stop-on-error")
        clouds = list(self.output.rglob("*.laz"))
        self.assertEqual(len(clouds), 2)
        for path in clouds:
            cloud = laspy.read(path)
            self.assertTrue(cloud.header.are_points_compressed)
            self.assertGreater(len(cloud), 0)
            self.assertTrue(np.isfinite(cloud.xyz).all())
        c_txt = next((self.output / "stage8c_l2p_intermediate/txt").glob("*.txt"))
        d_txt = next((self.root / "separate l2p/stage8c_l2p_intermediate/txt").glob("*.txt"))
        np.testing.assert_allclose(np.loadtxt(c_txt, skiprows=1), np.loadtxt(d_txt, skiprows=1))

    def test_sample_rejects_existing_output_and_stops_before_writes_on_missing_data(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_bytes(b"archive")
        command = [sys.executable, str(REPO / "scripts/run_sample.py"),
                   "--data-root", str(self.root / "missing"), "--output-root", str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(marker.read_bytes(), b"archive")
        command[-1] = str(self.root / "fresh")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Sample stopped", result.stderr)
        self.assertFalse((self.root / "fresh").exists())


if __name__ == "__main__":
    unittest.main()
