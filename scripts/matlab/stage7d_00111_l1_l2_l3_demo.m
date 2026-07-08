%% Stage 7D demo plots for CH1 file 00111
% This script visualizes the processing chain for a teacher presentation.
% Figure titles, axis labels, and legends are written in Chinese.
%
%   L1 raw data
%       -> L2 body/FRD coordinates from LADM-II scan geometry
%       -> L3 POS-matched navigation offsets
%       -> final UTM coordinates (not plotted here; already exported before)
%
% Inputs:
%   1) Original L1 H5 for file 00111
%   2) Stage 7A candidate H5 for file 00111
%
% Outputs:
%   PNG figures under E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0\stage7d_teacher_package\matlab_figures

clear; clc;
set(groot, 'defaultAxesFontName', 'Microsoft YaHei');
set(groot, 'defaultTextFontName', 'Microsoft YaHei');
set(groot, 'defaultLegendFontName', 'Microsoft YaHei');

repoRoot = getenv('AIRBORNE_LIDAR_PROJECT_DATA_ROOT');
if isempty(repoRoot)
    repoRoot = 'E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3';
end
outputRoot = getenv('AIRBORNE_LIDAR_STAGE_ROOT');
if isempty(outputRoot)
    outputRoot = 'E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0';
end

l1Path = fullfile(repoRoot, '0510_f3', 'L1-TIME_ANGE_DIST_DATA', 'L1_cap_00111_20260510190957.h5');
stage7aPath = fullfile(outputRoot, 'h5', 'stage7a_00111_ch1_ladm2_full_points.h5');
figDir = fullfile(outputRoot, 'stage7d_teacher_package', 'matlab_figures');

if ~exist(figDir, 'dir')
    mkdir(figDir);
end
assert(exist(l1Path, 'file') == 2, 'L1 file not found: %s', l1Path);
assert(exist(stage7aPath, 'file') == 2, 'Stage 7A H5 not found: %s', stage7aPath);

maxPlotPoints = 200000;
distFactor = 2e-9 / 256.0 * 3e8 / 2.0; % raw Photon_DIST tick -> one-way distance in meters
timeOffsetSec = 18.0;                    % project convention: L1 GNSS_SEC_CH1 + 18

fprintf('Reading L1 raw file...\n');
l1TimeRaw = double(h5read(l1Path, '/GNSS_SEC_CH1'));
l1GpsTime = l1TimeRaw + timeOffsetSec;
l1RawDist = double(h5read(l1Path, '/Photon_CH1_DIST'));
l1Coder = double(h5read(l1Path, '/Photon_CH1_CODER'));
l1PulseIndex = double(h5read(l1Path, '/PULSE_INDEX_CH1'));

fprintf('Reading Stage 7A full-chain H5...\n');
p = h5read(stage7aPath, '/STAGE7A/CH1/full_points');

n = numel(l1GpsTime);
idx = sampleIndices(n, maxPlotPoints);

rawRangeM = l1RawDist * distFactor;
rawScanAngleDeg = mod(l1Coder * 360.0 / 65536.0, 360.0);

rangeM = getFieldVector(p, 'range_m');
scanAngleDeg = getFieldVector(p, 'scan_angle_deg');
frdX = getFieldVector(p, 'frd_x_m');
frdY = getFieldVector(p, 'frd_y_m');
frdZ = getFieldVector(p, 'frd_z_m');
northOffset = getFieldVector(p, 'north_offset_m');
eastOffset = getFieldVector(p, 'east_offset_m');
downOffset = getFieldVector(p, 'down_offset_m');
posEasting = getFieldVector(p, 'pos_easting');
posNorthing = getFieldVector(p, 'pos_northing');
posHeight = getFieldVector(p, 'pos_height');
posRoll = getFieldVector(p, 'pos_roll');
posPitch = getFieldVector(p, 'pos_pitch');
posHeading = getFieldVector(p, 'pos_heading');
posInterpDt = getFieldVector(p, 'pos_interp_dt');
posQualityFlag = getFieldVector(p, 'pos_quality_flag');

validRange = isfinite(rangeM) & rangeM > 30;
validPos = posQualityFlag == 0 & isfinite(posInterpDt);
validForL2 = validRange;
validForL3 = validRange & validPos;

idxL2 = idx(validForL2(idx));
idxL3 = idx(validForL3(idx));

%% Figure 1: L1 raw data
fig1 = figure('Color', 'w', 'Name', 'Stage7D_00111_L1原始数据', 'Position', [100, 80, 1300, 850]);
tiledlayout(2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
plot(l1GpsTime(idx), rawRangeM(idx), '.', 'MarkerSize', 2);
grid on;
xlabel('GPS 时间（秒）');
ylabel('零位/标定前原始距离（米）');
title('L1：Photon\_CH1\_DIST 转换得到的原始距离');

nexttile;
plot(l1GpsTime(idx), rawScanAngleDeg(idx), '.', 'MarkerSize', 2);
grid on;
xlabel('GPS 时间（秒）');
ylabel('编码器原始扫描角（度）');
title('L1：Photon\_CH1\_CODER 对应的扫描相位');

nexttile;
histogram(rawRangeM(idx), 120);
grid on;
xlabel('零位/标定前原始距离（米）');
ylabel('点数');
title('L1 原始距离分布');

nexttile;
plot(l1GpsTime(idx), l1PulseIndex(idx), '.', 'MarkerSize', 2);
grid on;
xlabel('GPS 时间（秒）');
ylabel('脉冲索引 PULSE\_INDEX\_CH1');
title('L1 脉冲索引连续性');

saveFigure(fig1, fullfile(figDir, 'stage7d_00111_L1_raw.png'));

%% Figure 2: L2 body/FRD coordinates
% L2 here means the laser points after range calibration and LADM-II scan
% geometry, but before POS trajectory is applied.
fig2 = figure('Color', 'w', 'Name', 'Stage7D_00111_L2机体系FRD坐标', 'Position', [120, 100, 1350, 850]);
tiledlayout(2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
scatter(frdY(idxL2), frdX(idxL2), 2, rangeM(idxL2), 'filled');
axis equal; grid on; colorbar;
xlabel('FRD 右向 Y（米）');
ylabel('FRD 前向 X（米）');
title('L2：机体系/FRD 水平投影（颜色表示距离）');

nexttile;
scatter(frdY(idxL2), -frdZ(idxL2), 2, scanAngleDeg(idxL2), 'filled');
axis equal; grid on; colorbar;
xlabel('FRD 右向 Y（米）');
ylabel('-FRD 下向 Z，近似向上（米）');
title('L2：扫描几何剖面（颜色表示扫描角）');

nexttile;
scatter3(frdX(idxL2), frdY(idxL2), frdZ(idxL2), 2, scanAngleDeg(idxL2), 'filled');
axis equal; grid on; colorbar;
xlabel('FRD X（米）');
ylabel('FRD Y（米）');
zlabel('FRD Z（米）');
title('L2：机体系/FRD 三维点云');
view(35, 20);

nexttile;
histogram(scanAngleDeg(idxL2), 120);
grid on;
xlabel('Stage 7A 扫描角（度）');
ylabel('点数');
title('L2：LADM-II 模型后的扫描角分布');

saveFigure(fig2, fullfile(figDir, 'stage7d_00111_L2_FRD.png'));

%% Figure 3: L3 POS-matched navigation offsets
% L3 here means the intermediate result after POS interpolation and
% FRD->NED rotation. The final UTM coordinates are:
%   Easting  = pos_easting  + east_offset_m
%   Northing = pos_northing + north_offset_m
%   Height   = pos_height   - down_offset_m
% Those final coordinates are not plotted in this script.
fig3 = figure('Color', 'w', 'Name', 'Stage7D_00111_L3_POS匹配_NED偏移', 'Position', [140, 120, 1350, 900]);
tiledlayout(2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
plot(posEasting(idxL3), posNorthing(idxL3), '.', 'MarkerSize', 2);
axis equal; grid on;
xlabel('POS 东坐标 Easting（米）');
ylabel('POS 北坐标 Northing（米）');
title('L3：匹配到的 POS 轨迹采样点');

nexttile;
scatter(eastOffset(idxL3), northOffset(idxL3), 2, -downOffset(idxL3), 'filled');
axis equal; grid on; colorbar;
xlabel('相对 POS 的东向偏移（米）');
ylabel('相对 POS 的北向偏移（米）');
title('L3：NED 水平偏移（颜色表示高程方向偏移）');

nexttile;
plot(l1GpsTime(idxL3), posInterpDt(idxL3), '.', 'MarkerSize', 2);
grid on;
xlabel('GPS 时间（秒）');
ylabel('最近 POS 时间差绝对值（秒）');
title('L3：POS 插值时间误差');

nexttile;
plot(l1GpsTime(idxL3), posRoll(idxL3), '.', 'MarkerSize', 2); hold on;
plot(l1GpsTime(idxL3), posPitch(idxL3), '.', 'MarkerSize', 2);
plot(l1GpsTime(idxL3), posHeading(idxL3), '.', 'MarkerSize', 2);
grid on;
xlabel('GPS 时间（秒）');
ylabel('姿态角（度）');
legend({'横滚 roll', '俯仰 pitch', '航向 heading'}, 'Location', 'best');
title('L3：插值得到的 POS 姿态角');

saveFigure(fig3, fullfile(figDir, 'stage7d_00111_L3_POS_NED.png'));

fprintf('\nDone. Figures written to:\n%s\n', figDir);

%% Local helper functions
function idx = sampleIndices(n, maxPlotPoints)
    if n <= maxPlotPoints
        idx = (1:n)';
    else
        idx = unique(round(linspace(1, n, maxPlotPoints)))';
    end
end

function v = getFieldVector(s, fieldName)
    assert(isfield(s, fieldName), 'Missing H5 compound field: %s', fieldName);
    if numel(s) > 1
        v = double([s.(fieldName)]);
    else
        v = double(s.(fieldName));
    end
    v = v(:);
end

function saveFigure(fig, outPath)
    [folder, ~, ~] = fileparts(outPath);
    if ~exist(folder, 'dir')
        mkdir(folder);
    end
    try
        exportgraphics(fig, outPath, 'Resolution', 200);
    catch
        saveas(fig, outPath);
    end
    fprintf('Saved %s\n', outPath);
end
