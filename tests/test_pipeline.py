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
from unittest import mock

import h5py
import laspy
import numpy as np


REPO = Path(__file__).resolve().parents[1]
PROCESSING = REPO / "scripts" / "processing"
sys.path.insert(0, str(PROCESSING))

import stage5_full_ch1 as stage5
import stage7a_ch1_ladm2_candidate_batch as stage7a
import stage8a_ch1_ladm2_light_denoise_batch as stage8a
import stage8b_ch1_export_local_coords as stage8b
import stage8c_00111_l2p_intermediate_export as stage8c
import stage8d_ch1_l2p_missing_from_l1 as stage8d


def snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def file_info(seq: int, status: str = "OK") -> stage5.FileInfo:
    return stage5.FileInfo(
        seq, Path(f"L1_cap_{seq:05d}_20000101000000.h5"),
        status, "" if status == "OK" else "bad timestamps",
        1.0, 2.0, 4, 1.0, 4.0, 4.0,
    )


def points(count: int = 32) -> np.ndarray:
    floats = [
        "easting_m", "northing_m", "height_m", "gps_time", "range_m",
        "scan_angle_deg", "north_offset_m", "east_offset_m", "down_offset_m",
        "frd_x_m", "frd_y_m", "frd_z_m",
    ]
    dtype = [(name, "f8") for name in floats] + stage7a.POS_EXTRA_DTYPE + [
        ("source_seq", "u2"), ("point_index", "u4"), ("pos_quality_flag", "u2"),
    ]
    data = np.zeros(count, dtype=dtype)
    data["easting_m"] = 394012.0
    data["northing_m"] = 3417008.0
    data["height_m"] = 50.0
    data["pos_easting"] = 394010.0
    data["pos_northing"] = 3417005.0
    data["pos_height"] = 55.0
    data["east_offset_m"] = 2.0
    data["north_offset_m"] = 3.0
    data["down_offset_m"] = 5.0
    data["range_m"] = 100.0
    data["gps_time"] = np.arange(count) + 1.0
    data["point_index"] = np.arange(count)
    data["source_seq"] = 111
    return data


class TempTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def quiet_run(self, function, args) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            function(args)
        return output.getvalue()


class Stage7SafetyTests(TempTest):
    def run_without_geometry(self, args, files):
        with (
            mock.patch.object(stage7a, "processing_rows_for_scope", return_value=files),
            mock.patch.object(stage7a.stage6k, "load_json", side_effect=AssertionError("candidate loaded")),
            mock.patch.object(stage7a.pipe, "load_channel_calibration", side_effect=AssertionError("calibration loaded")),
            mock.patch.object(stage7a.stage5, "load_pos", side_effect=AssertionError("POS loaded")),
        ):
            return self.quiet_run(stage7a.run, args)

    def test_dry_run_does_not_create_output_root(self):
        output_root = self.root / "absent"
        args = stage7a.build_parser().parse_args(["--output-root", str(output_root), "--dry-run"])
        output = self.run_without_geometry(args, [file_info(50)])
        self.assertIn("DRY_RUN 00050", output)
        self.assertFalse(output_root.exists())

    def test_dry_run_preserves_archive_and_selection(self):
        for relative in [
            "manifest/stage7a_ch1_ladm2_00050_00150_manifest.csv",
            "reports/stage7a_ch1_ladm2_candidate_batch_report.json",
            "h5/stage7a_00050_ch1_ladm2_full_points.h5",
        ]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"archive must remain unchanged")
        before = snapshot(self.root)
        args = stage7a.build_parser().parse_args(["--output-root", str(self.root), "--dry-run"])
        output = self.run_without_geometry(args, [file_info(50), file_info(54, "BAD_TIME"), file_info(55)])
        self.assertIn("SKIPPED_EXISTS 00050", output)
        self.assertIn("SKIPPED_BAD_TIME 00054", output)
        self.assertIn("DRY_RUN 00055", output)
        self.assertEqual(before, snapshot(self.root))

    def test_dry_run_respects_limit_and_overrides(self):
        args = stage7a.build_parser().parse_args([
            "--output-root", str(self.root), "--dry-run", "--overwrite",
            "--include-non-ok", "--limit", "1",
        ])
        output = self.run_without_geometry(args, [file_info(54, "BAD_TIME"), file_info(55)])
        self.assertIn("DRY_RUN 00054", output)
        self.assertNotIn("00055", output)
        self.assertEqual({}, snapshot(self.root))

    def test_real_noop_preserves_prior_summary(self):
        marker = self.root / "prior.csv"
        marker.write_bytes(b"prior summary")
        args = stage7a.build_parser().parse_args(["--output-root", str(self.root)])
        before = snapshot(self.root)
        self.run_without_geometry(args, [file_info(54, "BAD_TIME")])
        self.assertEqual(before, snapshot(self.root))

    def test_manifest_output_paths_are_absolute(self):
        row = stage7a.row_from_skip(file_info(50), "SKIPPED", "", stage7a.output_paths(Path("relative"), 50))
        for name in ("h5_path", "laz_path", "txt_path"):
            self.assertTrue(Path(row[name]).is_absolute())

    def test_stage5_accepts_portable_and_windows_relative_paths(self):
        path = self.root / "manifest.csv"
        for value in ("0510_f3/L1/file.h5", r"0510_f3\L1\file.h5"):
            with self.subTest(value=value):
                write_csv(path, [{"file": value, "seq": "50", "status": "OK"}])
                with mock.patch.object(stage5, "ROOT", self.root):
                    result = stage5.read_manifest(path)
                self.assertEqual(result[0].path, self.root / "0510_f3" / "L1" / "file.h5")


class Stage8ExclusionTests(TempTest):
    def setUp(self):
        super().setUp()
        self.l1 = self.root / "l1"
        self.l1.mkdir()
        for seq in (1, 2, 3):
            (self.l1 / f"L1_cap_{seq:05d}_20000101000000.h5").touch()
        self.output = self.root / "results"
        self.exclusions = stage8d.exclusion_manifest_path(self.output)
        write_csv(self.exclusions, [{"seq": "00001", "action": "MOVED_FROM_MAIN_TXT"}])

    def args(self, *extra):
        return stage8d.build_parser().parse_args([
            "--l1-dir", str(self.l1), "--output-root", str(self.output), *extra,
        ])

    def run_without_geometry(self, args):
        with (
            mock.patch.object(stage8d, "load_stage6i_candidate", side_effect=AssertionError("candidate loaded")),
            mock.patch.object(stage8d.stage5, "load_pos", side_effect=AssertionError("POS loaded")),
            mock.patch.object(stage8d, "process_one", side_effect=AssertionError("processing called")),
        ):
            return self.quiet_run(stage8d.run, args)

    def test_default_exclusions_before_limit(self):
        before = snapshot(self.root)
        output = self.run_without_geometry(self.args("--dry-run", "--limit", "1"))
        self.assertIn("EXCLUDED 00001: MOVED_FROM_MAIN_TXT", output)
        self.assertIn("DRY-RUN 00002:", output)
        self.assertNotIn("DRY-RUN 00001:", output)
        self.assertNotIn("DRY-RUN 00003:", output)
        self.assertEqual(before, snapshot(self.root))

    def test_overwrite_and_no_only_missing_keep_exclusions(self):
        for options in (("--overwrite",), ("--no-only-missing",), ("--overwrite", "--no-only-missing")):
            with self.subTest(options=options):
                output = self.run_without_geometry(self.args("--dry-run", *options))
                self.assertIn("Files selected for this run: 2", output)
                self.assertNotIn("DRY-RUN 00001:", output)

    def test_empty_selection_does_not_replace_manifest(self):
        for seq in (2, 3):
            path = stage8d.txt_path(self.output, seq)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"prior TXT")
        manifest = stage8d.manifest_path(self.output)
        manifest.write_bytes(b"prior manifest")
        before = snapshot(self.root)
        output = self.run_without_geometry(self.args())
        self.assertIn("Files selected for this run: 0", output)
        self.assertEqual(before, snapshot(self.root))

    def test_explicit_missing_manifest_fails(self):
        with self.assertRaises(FileNotFoundError):
            self.run_without_geometry(self.args("--dry-run", "--exclude-manifest", str(self.root / "missing.csv")))

    def test_quarantine_without_default_manifest_fails(self):
        self.exclusions.unlink()
        (self.output / "stage8c_l2p_intermediate" / "txt_pos_match_failed_excluded").mkdir()
        with self.assertRaisesRegex(FileNotFoundError, "Quarantine"):
            self.run_without_geometry(self.args("--dry-run"))

    def test_fresh_dataset_dry_run_creates_nothing(self):
        fresh = self.root / "fresh"
        args = self.args("--output-root", str(fresh), "--dry-run")
        output = self.run_without_geometry(args)
        self.assertIn("Files selected for this run: 3", output)
        self.assertFalse(fresh.exists())

    def test_malformed_exclusions_fail(self):
        for content in ("wrong\n1\n", "seq\nabc\n", "seq\n1.5\n", "seq\n0\n", "seq\n\n,\n", "seq\n1\n00001\n"):
            with self.subTest(content=content):
                self.exclusions.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    stage8d.load_exclusions(self.exclusions)

    def test_missing_l1_directory_fails(self):
        with self.assertRaises(FileNotFoundError):
            self.run_without_geometry(self.args("--l1-dir", str(self.root / "missing"), "--dry-run"))

    def test_environment_exclusion_path_is_parsed_as_path(self):
        with mock.patch.dict(os.environ, {"AIRBORNE_LIDAR_EXCLUDE_MANIFEST": str(self.exclusions)}):
            self.assertEqual(self.args().exclude_manifest, self.exclusions)

    def test_real_selection_never_processes_excluded_file(self):
        args = self.args("--limit", "1", "--overwrite")
        before = self.exclusions.read_bytes()
        with (
            mock.patch.object(stage8d, "load_stage6i_candidate", return_value={}),
            mock.patch.object(stage8d.pipe, "load_channel_calibration", return_value={}),
            mock.patch.object(stage8d.stage5, "load_pos", return_value=(np.array([1, 2]), {}, 0)),
            mock.patch.object(stage8d, "process_one", return_value={"seq": 2, "status": "PROCESSED"}) as process,
        ):
            self.quiet_run(stage8d.run, args)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.args[0], 2)
        self.assertEqual(before, self.exclusions.read_bytes())
        payload = json.loads(stage8d.report_paths(self.output)["json"].read_text(encoding="utf-8-sig"))
        self.assertEqual(payload["summary"]["excluded"], 1)


class ExportTests(TempTest):
    def test_laz_files_are_really_compressed_and_readable(self):
        data = points()
        for name in ("7a", "8a"):
            with self.subTest(stage=name):
                path = self.root / f"{name}.laz"
                if name == "7a":
                    count = stage7a.write_laz(path, data, 0, True, 0, False)
                else:
                    count = stage8a.write_laz(path, data, False)
                loaded = laspy.read(path)
                self.assertTrue(loaded.header.are_points_compressed)
                self.assertEqual(count, len(data))
                np.testing.assert_allclose(loaded.x, data["easting_m"], atol=0.001)
                np.testing.assert_array_equal(loaded.point_index, data["point_index"])

    def test_denoising_is_deterministic_and_rejects_invalid_points(self):
        data = points(36)
        data["range_m"][32] = 0
        data["pos_quality_flag"][33] = 1
        data["height_m"][34] = np.nan
        data["easting_m"][35] += 1000
        args = stage8a.build_parser().parse_args([])
        keep, stats = stage8a.denoise_mask(data, args)
        other, _ = stage8a.denoise_mask(data, args)
        np.testing.assert_array_equal(keep, other)
        np.testing.assert_array_equal(keep, np.arange(36) < 32)
        self.assertEqual(stats["point_count_after"], 32)

    def test_stage8b_mixed_success_failure_csv(self):
        path = self.root / "mixed.csv"
        stage8b.write_csv(path, [
            {"seq": 1, "status": "PROCESSED"},
            {"seq": 2, "status": "FAILED", "reason": "missing H5"},
        ])
        rows = stage8b.read_csv(path)
        self.assertEqual(rows[1]["reason"], "missing H5")

    def test_synthetic_h5_denoise_and_local_export_chain(self):
        data = points()
        source = stage8c.source_h5_path(self.root, 111)
        source.parent.mkdir()
        with h5py.File(source, "w") as h5:
            h5.create_dataset("STAGE7A/CH1/full_points", data=data)
        manifest = self.root / "input.csv"
        write_csv(manifest, [{"seq": "111", "h5_path": str(source)}])
        args = stage8a.build_parser().parse_args([
            "--output-root", str(self.root), "--input-manifest", str(manifest),
            "--no-write-laz", "--no-write-sample-txt", "--stop-on-error",
        ])
        self.quiet_run(stage8a.run, args)
        dest = stage8a.output_paths(self.root, 111)["h5"]
        with h5py.File(dest, "r") as h5:
            np.testing.assert_array_equal(h5["STAGE8A/CH1/denoised_points"][:], data)
        export_args = stage8b.build_parser().parse_args([
            "--output-root", str(self.root), "--seq", "111", "--stop-on-error", "--chunk-size", "3",
        ])
        self.quiet_run(stage8b.run, export_args)
        txt = stage8b.output_paths(self.root, 111)["txt"]
        xyz = np.loadtxt(txt, skiprows=1)[:, :3]
        np.testing.assert_allclose(xyz, np.tile([12, 8, 50], (len(data), 1)))
        self.assertTrue((self.root / "reports" / "stage8a_ch1_ladm2_light_denoise_batch_report.json").exists())

    def test_l2p_h5_and_stage8c_8d_txt_coordinate_agreement(self):
        data = points(4)
        data["range_m"][1] = 30
        data["pos_quality_flag"][2] = 1
        source = self.root / "input.h5"
        with h5py.File(source, "w") as h5:
            h5.create_dataset("STAGE7A/CH1/full_points", data=data)
        dest = self.root / "l2p.h5"
        stats = stage8c.create_h5(source, dest, False)
        self.assertEqual(stats["point_count"], 4)
        with h5py.File(dest, "r") as h5:
            self.assertEqual(len(h5["L2P"]), 23)
            np.testing.assert_array_equal(h5["L2P/POINT_X"][:], data["northing_m"])
            np.testing.assert_array_equal(h5["L2P/POINT_Y"][:], data["easting_m"])
            np.testing.assert_array_equal(h5["L2P/POINT_Z"][:], data["height_m"])
        c_txt, d_txt = self.root / "c.txt", self.root / "d.txt"
        stage8c.write_txt(source, c_txt, 30, False, 2)
        stage8d.write_l2p_txt(d_txt, data, 30, False, 2)
        np.testing.assert_allclose(np.loadtxt(c_txt, skiprows=1), np.loadtxt(d_txt, skiprows=1))
        self.assertEqual(np.loadtxt(d_txt, skiprows=1).shape, (2, 13))

    def test_stage7a_real_writer_and_report_in_selected_root(self):
        data = points()
        info = file_info(111)
        stats = {
            "point_count_h5": len(data), "point_count_l1": len(data),
            "range_m_gt_30_count": len(data), "pos_success_rate": 1.0,
            "gps_time_sec": {"min": 1.0, "max": float(len(data))},
            "height_m": {"median": 50.0},
        }
        args = stage7a.build_parser().parse_args([
            "--output-root", str(self.root / "selected"), "--no-write-laz",
            "--no-write-txt", "--stop-on-error",
        ])
        with (
            mock.patch.object(stage7a, "processing_rows_for_scope", return_value=[info]),
            mock.patch.object(stage7a, "load_json", return_value={}),
            mock.patch.object(stage7a.stage6k, "load_json", return_value={}),
            mock.patch.object(stage7a.pipe, "load_channel_calibration", return_value={}),
            mock.patch.object(stage7a.stage5, "load_pos", return_value=(np.array([1, 2]), {}, 0)),
            mock.patch.object(stage7a.stage6k, "load_l1_full", return_value={"gnss": np.arange(len(data))}),
            mock.patch.object(stage7a.stage6k, "build_full_points", return_value=(data, stats)),
        ):
            self.quiet_run(stage7a.run, args)
        path = stage7a.output_paths(args.output_root, 111)["h5"]
        with h5py.File(path, "r") as h5:
            np.testing.assert_array_equal(h5["STAGE7A/CH1/full_points"][:], data)
        report = args.output_root / "reports" / "stage7a_ch1_ladm2_candidate_batch_report.json"
        self.assertTrue(report.exists())

    def test_merge_header_and_atomic_failure(self):
        import merge_stage7a_cloudcompare_txt as merge

        for seq in (1, 2):
            (self.root / f"stage7a_{seq:05d}_ch1_ladm2_cloudcompare.txt").write_bytes(b"X Y Z\n1 2 3\n")
        argv = ["merge", "--input-dir", str(self.root), "--output-name", "merged.txt"]
        with mock.patch.object(sys, "argv", argv):
            self.quiet_run(lambda _: merge.main(), None)
        dest = self.root / "merged.txt"
        self.assertEqual(dest.read_bytes(), b"X Y Z\n1 2 3\n1 2 3\n")
        (self.root / "stage7a_00002_ch1_ladm2_cloudcompare.txt").write_bytes(b"wrong header\n")
        with mock.patch.object(sys, "argv", [*argv, "--overwrite"]):
            with self.assertRaises(RuntimeError):
                self.quiet_run(lambda _: merge.main(), None)
        self.assertEqual(dest.read_bytes(), b"X Y Z\n1 2 3\n1 2 3\n")
        self.assertFalse((self.root / "merged.txt.partial").exists())


class ConfigurationTests(TempTest):
    def test_environment_paths_across_supported_entry_points(self):
        modules = [
            "stage7a_ch1_ladm2_candidate_batch", "stage7b_ch1_ladm2_candidate_qc",
            "stage7c_ch1_ladm2_focused_seam_audit", "stage7d_ch1_ladm2_teacher_review_package",
            "stage8a_ch1_ladm2_light_denoise_batch", "stage8b_ch1_export_local_coords",
            "stage8c_00111_l2p_intermediate_export", "stage8d_ch1_l2p_missing_from_l1",
        ]
        code = (
            "import importlib, json, project_paths, stage5_full_ch1; "
            f"mods = [importlib.import_module(n) for n in {modules!r}]; "
            "assert all(m.DEFAULT_OUTPUT_ROOT == project_paths.STAGE_ROOT for m in mods); "
            "assert stage5_full_ch1.ROOT == project_paths.DATA_ROOT; "
            "print(json.dumps([str(project_paths.DATA_ROOT), str(project_paths.STAGE_ROOT)]))"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROCESSING)
        env["AIRBORNE_LIDAR_PROJECT_DATA_ROOT"] = str(self.root / "input")
        env["AIRBORNE_LIDAR_STAGE_ROOT"] = str(self.root / "output")
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [str(self.root / "input"), str(self.root / "output")])
        self.assertEqual({}, snapshot(self.root))

    def test_default_paths_are_repo_relative_and_readonly(self):
        names = ("AIRBORNE_LIDAR_PROJECT_DATA_ROOT", "AIRBORNE_LIDAR_STAGE_ROOT")
        env = {key: value for key, value in os.environ.items() if key not in names}
        env["PYTHONPATH"] = str(PROCESSING)
        code = (
            "import project_paths as p; "
            "assert p.DATA_ROOT == p.REPO_ROOT / 'data'; "
            "assert p.STAGE_ROOT == p.REPO_ROOT / 'outputs' / 'stages'"
        )
        subprocess.run([sys.executable, "-c", code], env=env, check=True)

    def test_all_supported_cli_help(self):
        env = os.environ.copy()
        env["AIRBORNE_LIDAR_PROJECT_DATA_ROOT"] = str(self.root / "missing-input")
        env["AIRBORNE_LIDAR_STAGE_ROOT"] = str(self.root / "missing-output")
        scripts = sorted(PROCESSING.glob("stage7*.py")) + sorted(PROCESSING.glob("stage8*.py"))
        scripts.append(PROCESSING / "merge_stage7a_cloudcompare_txt.py")
        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [sys.executable, str(script), "--help"], env=env,
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
        self.assertEqual({}, snapshot(self.root))


if __name__ == "__main__":
    unittest.main()
