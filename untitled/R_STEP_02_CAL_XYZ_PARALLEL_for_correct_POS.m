%% batch_process_l2_coordinates.m
% 批量处理脚本：从L1 H5文件读取数据，计算本体坐标，保存为L2 H5文件

clear; close all; clc;

%% ==================== 配置参数 ====================
% 设置路径
srcPathName = 'E:\work\2026\海大造浪池实验\L1-TIME_ANGE_DIST_DATA\';  % L1文件所在目录
dstPathName = fullfile(fileparts(srcPathName), 'L2-COORDINATES');  % L2输出目录

% 创建输出目录（如果不存在）
if ~exist(dstPathName, 'dir')
    mkdir(dstPathName);
    fprintf('创建输出目录: %s\n', dstPathName);
end

% 加载标定系数
load calib_coeffs.mat; 
load COEFFS_20260106.mat;

% 获取文件列表
filePattern = fullfile(srcPathName, 'L1_*.h5');
fileList = dir(filePattern);

if isempty(fileList)
    error('没有找到L1_*.h5文件');
end

fprintf('找到 %d 个L1文件待处理\n', length(fileList));
fprintf('输出目录: %s\n', dstPathName);

%% ==================== 批量处理 ====================
success_count = 0;
fail_count = 0;

for i = 1:length(fileList)
    srcFile = fullfile(srcPathName, fileList(i).name);
    
    % 生成输出文件名（L1_ 替换为 L2_）
    [~, basename, ~] = fileparts(fileList(i).name);
    dstFilename = strrep(basename, 'L1_', 'L2_');
    dstFile = fullfile(dstPathName, [dstFilename '.h5']);
    
    % 检查输出文件是否已存在
    if exist(dstFile, 'file')
        fprintf('[%d/%d] 跳过已存在的文件: %s\n', i, length(fileList), dstFilename);
        continue;
    end
    
    fprintf('[%d/%d] 处理文件: %s\n', i, length(fileList), fileList(i).name);
    
    try
        % 处理单个文件
        process_single_l2_file(srcFile, dstFile, fitresult_alpha, fitresult_beta, calib_data);
        success_count = success_count + 1;
        fprintf('  ✓ 成功保存: %s\n', dstFilename);
    catch ME
        fail_count = fail_count + 1;
        fprintf('  ✗ 处理失败: %s\n', ME.message);
        fprintf('    错误详情: %s\n', ME.getReport);
    end
end

%% ==================== 处理结果汇总 ====================
fprintf('\n========================================\n');
fprintf('批量处理完成！\n');
fprintf('  成功: %d\n', success_count);
fprintf('  失败: %d\n', fail_count);
fprintf('  总数: %d\n', length(fileList));
fprintf('========================================\n');

%% ==================== 单个文件处理函数 ====================
function process_single_l2_file(srcFile, dstFile, fitresult_alpha, fitresult_beta, calib_data)
% 处理单个L1文件，计算坐标并保存为L2文件

% 读取所有需要的数据集
fprintf('  读取L1数据...\n');

% 获取文件中的所有数据集
info = h5info(srcFile);
datasets = {info.Datasets.Name};

% 预先分配存储
ch_data = cell(4,1);
ch_coder = cell(4,1);
ch_pulse_idx = cell(4,1);
ch_circle = cell(4,1);
ch_start_count = cell(4,1);
ch_gnss_sec = cell(4,1);

% 读取各通道数据
for ch = 1:4
    % 读取距离数据
    dist_path = sprintf('/Photon_CH%d_DIST', ch);
    if any(strcmp(datasets, dist_path(2:end)))
        ch_data{ch} = double(h5read(srcFile, dist_path));
    else
        ch_data{ch} = [];
    end
    
    % 读取编码器数据
    coder_path = sprintf('/Photon_CH%d_CODER', ch);
    if any(strcmp(datasets, coder_path(2:end)))
        ch_coder{ch} = double(h5read(srcFile, coder_path));
    else
        ch_coder{ch} = [];
    end
    
    % 读取脉冲索引
    idx_path = sprintf('/PULSE_INDEX_CH%d', ch);
    if any(strcmp(datasets, idx_path(2:end)))
        ch_pulse_idx{ch} = double(h5read(srcFile, idx_path));
    else
        ch_pulse_idx{ch} = [];
    end
    
    % 读取圈数
    circle_path = sprintf('/PULSE_CIRCLE_CH%d', ch);
    if any(strcmp(datasets, circle_path(2:end)))
        ch_circle{ch} = double(h5read(srcFile, circle_path));
    else
        ch_circle{ch} = [];
    end
    
    % 读取起始计数
    start_path = sprintf('/Photon_Start_Count_CH%d', ch);
    if any(strcmp(datasets, start_path(2:end)))
        ch_start_count{ch} = double(h5read(srcFile, start_path));
    else
        ch_start_count{ch} = [];
    end
    
    % 读取GNSS时间
    gnss_path = sprintf('/GNSS_SEC_CH%d', ch);
    if any(strcmp(datasets, gnss_path(2:end)))
        ch_gnss_sec{ch} = double(h5read(srcFile, gnss_path));
    else
        ch_gnss_sec{ch} = [];
    end
end

% 读取标量数据
TotalPulses = double(h5read(srcFile, '/TotalPulses'));
Hour = double(h5read(srcFile, '/Hour'));
Minute = double(h5read(srcFile, '/Minute'));
Second = double(h5read(srcFile, '/Second'));

% 读取状态信息
try
    HasGNSS = double(h5read(srcFile, '/STATUS/HasGNSS'));
    HasPPS = double(h5read(srcFile, '/STATUS/HasPPS'));
catch
    HasGNSS = 0;
    HasPPS = 0;
end

% 读取N_STOP_ALL
N_STOP_ALL = h5read(srcFile, '/N_STOP_ALL');

%% ==================== 计算各通道坐标 ====================
fprintf('  计算本体坐标...\n');

% 参数
c = 3e8;  % 光速
dist_factor = 2e-9/256 * c / 2;  % 距离转换因子
peak_range = [0, 20];  % 零位峰范围

% 初始化坐标和零位峰标记存储
ch_x = cell(4,1);
ch_y = cell(4,1);
ch_z = cell(4,1);
ch_zero_peak = cell(4,1);  % 记录零位峰标记

for ch = 1:4
    if isempty(ch_data{ch}) || isempty(ch_coder{ch})
        fprintf('  通道%d数据为空，跳过\n', ch);
        ch_x{ch} = [];
        ch_y{ch} = [];
        ch_z{ch} = [];
        ch_zero_peak{ch} = [];
        continue;
    end
    
    % 计算距离（米）
    LIDAR_DISTANCE = max(0, ch_data{ch} * dist_factor);
    % figure;
    % scatter(ch_gnss_sec{ch},LIDAR_DISTANCE,1,'filled');
    % 零位峰处理
    %% 计算距离并进行零位峰处理
    [LIDAR_DISTANCE, zero_peak] = calibrate_range(LIDAR_DISTANCE, ch, peak_range, calib_data);
    
    % 筛选：保留大于 zero_peak + 1 的索引
    valid_idx = LIDAR_DISTANCE < 30 & LIDAR_DISTANCE > 1;
    
    % 应用筛选到所有相关数据
    LIDAR_DISTANCE = LIDAR_DISTANCE(valid_idx);
    ch_gnss_sec{ch} = ch_gnss_sec{ch}(valid_idx);
    ch_coder{ch} = ch_coder{ch}(valid_idx);
    ch_pulse_idx{ch} = ch_pulse_idx{ch}(valid_idx);
    ch_circle{ch} = ch_circle{ch}(valid_idx);
    ch_start_count{ch} = ch_start_count{ch}(valid_idx);
    
    ch_zero_peak{ch} = zero_peak;  % 保存筛选后的零位峰标记
    
    fprintf('  通道%d: 筛选前 %d 个点，筛选后 %d 个点\n', ch, length(LIDAR_DISTANCE)+sum(~valid_idx), length(LIDAR_DISTANCE));
    
   
    % 计算角度（度）
    angle = ch_coder{ch} * 360 / 65536;
    
    % 调用坐标转换函数
    [X, Y, Z] = F_BodyFrame_XYZ(LIDAR_DISTANCE, 360-angle, fitresult_alpha, fitresult_beta);

    
    figure;
    pcshow([X,Y,-Z]);
    figure;
    scatter(ch_gnss_sec{ch},Z,1,'filled');
    set(gca, 'YDir', 'reverse');

    ch_x{ch} = X;
    ch_y{ch} = Y;
    ch_z{ch} = Z;
    
    % 统计零位峰数量
    zero_count = sum(zero_peak);
    fprintf('  通道%d: %d个点，其中零位峰%d个\n', ch, length(X), zero_count);
end

%% ==================== 保存为L2 H5文件 ====================
fprintf('  保存L2数据...\n');

% 复制所有原始数据集
for i = 1:length(datasets)
    dataset = datasets{i};
    data = h5read(srcFile, ['/' dataset]);
    
    % 直接写入（保持原样）
    h5create(dstFile, ['/' dataset], size(data), 'Datatype', class(data));
    h5write(dstFile, ['/' dataset], data);
end

% 添加坐标数据和零位峰标记
for ch = 1:4
    if ~isempty(ch_x{ch})
        % X坐标
        x_path = sprintf('/Photon_CH%d_X', ch);
        h5create(dstFile, x_path, length(ch_x{ch}), 'Datatype', 'double');
        h5write(dstFile, x_path, ch_x{ch});
        
        % Y坐标
        y_path = sprintf('/Photon_CH%d_Y', ch);
        h5create(dstFile, y_path, length(ch_y{ch}), 'Datatype', 'double');
        h5write(dstFile, y_path, ch_y{ch});
        
        % Z坐标
        z_path = sprintf('/Photon_CH%d_Z', ch);
        h5create(dstFile, z_path, length(ch_z{ch}), 'Datatype', 'double');
        h5write(dstFile, z_path, ch_z{ch});
        
        % 零位峰标记
        zero_path = sprintf('/Photon_CH%d_ZeroPeak', ch);
        h5create(dstFile, zero_path, length(ch_zero_peak{ch}), 'Datatype', 'uint8');
        h5write(dstFile, zero_path, uint8(ch_zero_peak{ch}));
    end
end



fprintf('  完成！\n');
end

