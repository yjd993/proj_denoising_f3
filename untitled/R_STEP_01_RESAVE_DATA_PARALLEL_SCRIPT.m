%% R_STEP_01_RESAVE_DATA_PARALLEL_SCRIPT.m
% 批量处理脚本：读取pcap文件并保存为H5格式
% 使用说明：只需修改下面的"用户配置区域"的路径即可运行

clear; close all; clc;

%% ==================== 用户配置区域 ====================
% 在这里修改您的原始数据路径和保存路径

% 原始pcap文件所在目录
PathName = 'E:\work\2026\海大造浪池实验\ORG\';  % 请修改为您的pcap文件路径

% 输出H5文件保存目录
dstPathName = 'E:\work\2026\海大造浪池实验\L1-TIME_ANGE_DIST_DATA\';  % 请修改为您的输出路径

% 并行处理设置
USE_PARALLEL = true;        % true:启用并行, false:串行
PARALLEL_WORKERS = 4;       % 并行工作进程数（仅在USE_PARALLEL=true时有效）

% 文件处理范围（如需处理所有文件，保持为空即可）
% 例如只处理第1-10个文件: start_file = 1; end_file = 10;
start_file = [];  % 开始文件索引，为空则从第1个开始
end_file = [];    % 结束文件索引，为空则到最后一个结束

%% ==================== 参数设置 ====================
p_start_merge_num = 7;  % 一个UDP包中所含脉冲数

%% ==================== 获取文件列表 ====================
fprintf('========================================\n');
fprintf('批量处理脚本启动\n');
fprintf('========================================\n');

% 创建输出目录（如果不存在）
if ~exist(dstPathName, 'dir')
    mkdir(dstPathName);
    fprintf('创建输出目录: %s\n', dstPathName);
end

% 获取文件列表
filePattern = fullfile(PathName, '*.pcap');
FileList = dir(filePattern);

if isempty(FileList)
    error('在 %s 目录下未找到pcap文件', PathName);
end

fprintf('找到 %d 个pcap文件\n', length(FileList));

% 确定文件处理范围
if isempty(start_file) || start_file < 1
    start_file = 1;
end
if isempty(end_file) || end_file > length(FileList)
    end_file = length(FileList);
end

fileIndices = start_file:end_file;
fprintf('处理文件范围: %d 到 %d (共 %d 个文件)\n', start_file, end_file, length(fileIndices));

%% ==================== 设置并行池 ====================
if USE_PARALLEL
    poolobj = gcp('nocreate');
    if isempty(poolobj)
        parpool(PARALLEL_WORKERS);
        fprintf('启动并行池，工作进程数: %d\n', PARALLEL_WORKERS);
    elseif poolobj.NumWorkers ~= PARALLEL_WORKERS
        delete(poolobj);
        parpool(PARALLEL_WORKERS);
        fprintf('重新配置并行池，工作进程数: %d\n', PARALLEL_WORKERS);
    else
        fprintf('使用现有并行池，工作进程数: %d\n', poolobj.NumWorkers);
    end
end

%% ==================== 主处理循环 ====================
fprintf('========================================\n');
fprintf('开始处理 %d 个文件...\n', length(fileIndices));

success_count = 0;
fail_count = 0;

if USE_PARALLEL
    % 并行处理
    fprintf('使用并行处理模式\n');
    parfor i = 1:length(fileIndices)
        FileIndex = fileIndices(i);
        [success, msg] = process_single_pcap_file(FileIndex, FileList, PathName, dstPathName, p_start_merge_num);
        
        % 在parfor中不能直接输出，所以需要特殊处理
        if success
            fprintf('文件 %d/%d 处理成功: %s\n', i, length(fileIndices), msg);
        else
            fprintf('文件 %d/%d 处理失败: %s\n', i, length(fileIndices), msg);
        end
    end
else
    % 串行处理
    fprintf('使用串行处理模式\n');
    for i = 1:length(fileIndices)
        FileIndex = fileIndices(i);
        fprintf('处理文件 %d/%d...\n', i, length(fileIndices));
        
        [success, msg] = process_single_pcap_file(FileIndex, FileList, PathName, dstPathName, p_start_merge_num);
        
        if success
            success_count = success_count + 1;
            fprintf('  ✓ %s\n', msg);
        else
            fail_count = fail_count + 1;
            fprintf('  ✗ %s\n', msg);
        end
    end
end

%% ==================== 处理结果汇总 ====================
fprintf('========================================\n');
fprintf('批量处理完成！\n');
fprintf('  成功: %d\n', success_count);
fprintf('  失败: %d\n', fail_count);
fprintf('  总数: %d\n', length(fileIndices));
fprintf('========================================\n');


%% ==================== 单个PCAP文件处理函数 ====================
function [success, msg] = process_single_pcap_file(FileIndex, FileList, PathName, dstPathName, p_start_merge_num)
    success = false;
    msg = '';
    
    try
        filename = FileList(FileIndex).name;
        filepath = fullfile(PathName, filename);
        
        [~, basename, ~] = fileparts(filename);
        dstFileName = fullfile(dstPathName, ['L1_' basename '.h5']);
        
        if exist(dstFileName, 'file')
            msg = sprintf('跳过已存在的文件: %s', dstFileName);
            success = true;  % 跳过也算成功
            return;
        end
        
        % 调用核心处理函数
        process_pcap_file_core(filepath, dstFileName, p_start_merge_num);
        
        msg = sprintf('成功保存: %s', dstFileName);
        success = true;
        
    catch ME
        msg = sprintf('处理 %s 时出错: %s', filename, ME.message);
    end
end

function process_pcap_file_core(filepath, dstFileName, p_start_merge_num)
%% UDP解包
disp('UDP解包');
tic;
fprintf('正在处理文件: %s\n', filepath);

% 读取pcap文件
t_pcap = pcapReader(filepath);
t_pcap_data = readAll(t_pcap);

% 计算数据包大小
l_udp_row = t_pcap_data(1).PacketLength - 34;
l_udp_col = t_pcap.PacketsRead;
l_lader_num = t_pcap.PacketsRead * p_start_merge_num;

% 读udp数据
t_udp_data = zeros(l_udp_row, l_udp_col);
for i = 1:l_udp_col
    t_udp_data(:, i) = t_pcap_data(i).Packet.eth.Payload(21:end);
end

% 分割udp包头
d_udp_header = t_udp_data(1:8, :);
d_udp_data = t_udp_data(9:end, :);

fprintf('  读取到udp共%d包，单个udp包长度为%d字节\n', l_udp_col, l_udp_row);
toc;

%% 数据分割
disp('数据分割');
tic;
% 分割 start 参数 与数据
d_parameter = d_udp_data(9:32*p_start_merge_num+8,:);
d_data      = d_udp_data(32*p_start_merge_num+9:end,:);
clear d_udp_data;

d_start = d_parameter(15:32:end,:);

% start 2start
d_start2start = (d_parameter(17:32:end,:)-192)*256*256*256 + ...
                d_parameter(18:32:end,:)*256*256 + ...
                d_parameter(19:32:end,:)*256 + ...
                d_parameter(20:32:end,:);
d_start2start = d_start2start(:)/128/1000;

% pps 2 start 单位是ms - 添加错误处理

d_pps2start = (d_parameter(21:32:end,:)-176)*256*256*256 + ...
              d_parameter(22:32:end,:)*256*256 + ...
              d_parameter(23:32:end,:)*256 + ...
              d_parameter(24:32:end,:);

if mean(d_pps2start) > 0
    d_pps2start = d_pps2start(:) * 4e-9;
    has_pps = true;
else
    warning('PPS数据读取失败，使用默认值0');
    d_pps2start = zeros(size(d_parameter,1)/32, 1);
    has_pps = false;
end

% 处理电机
d_motor1_encoder = d_parameter(30:32:end,:)*256*256 + ...
                   d_parameter(31:32:end,:)*256 + ...
                   d_parameter(32:32:end,:);
d_motor1_circle = d_parameter(29:32:end,:)-144;

%处理电机
d_motor2_encoder = d_parameter(26:32:end,:)*256*256 + ...
                   d_parameter(27:32:end,:)*256 + ...
                   d_parameter(28:32:end,:);
d_motor2_circle =  d_parameter(25:32:end,:)-160;

% 转换为1维向量
d_start = d_start(:);
d_motor1_encoder = d_motor1_encoder(:);
d_motor1_circle = d_motor1_circle(:);

%%
%% 计算每个脉冲对应的电机圈数
tic;
disp('计算电机圈数对应关系');

% d_motor1_encoder 已经是每个脉冲的编码器值 (长度 = l_lader_num)
% 计算编码器值的变化
encoder_diff = [0; diff(d_motor1_encoder)];  % 第一个脉冲的diff设为0

% 判断圈数变化（编码器值回绕）
% 假设编码器是递增的，当检测到大幅度减小表示进入下一圈
% 阈值可以根据编码器范围设定，这里假设编码器是32位，最大值为2^32-1
encoder_wrap_threshold = 2^31;  % 如果减少超过这个值，认为是圈数变化

% 方法1：通过检测大幅度负跳变判断圈数变化
circle_change = encoder_diff < -encoder_wrap_threshold;  % 检测回绕
cum_circles = cumsum(circle_change);  % 累积圈数

% 或者方法2：如果编码器值本身已经包含圈数信息（如d_motor1_circle）
% 如果 d_motor1_circle 可靠，可以直接使用
if exist('d_motor1_circle', 'var') && ~isempty(d_motor1_circle)
    pulse_circle = d_motor1_circle + 1;  % 转换为从1开始
    fprintf('  使用d_motor1_circle计算圈数\n');
else
    % 否则通过编码器回绕判断
    pulse_circle = cum_circles + 1;  % 圈数从1开始
    fprintf('  通过编码器回绕计算圈数\n');
end

% 验证圈数计算的合理性
fprintf('  总脉冲数: %d, 总圈数: %d\n', l_lader_num, max(pulse_circle));

% 扩展到8个回波（和之前的时间矩阵一样）
pulse_circle_8 = repmat(pulse_circle, 1, 8);

toc;
%%
disp('主波细计数矫正');
% 主波细计数矫正
d_start = (d_start -25)*1.55;
d_start(d_start < 0) = 0;
d_start(d_start > 255) = 255;
d_start = round(d_start);

% GNSS时间处理 - 添加错误处理

GNSS_SEC = (d_parameter(10:32:end,:)) * 3600 + ...
           d_parameter(11:32:end,:) * 60 + ...
           d_parameter(12:32:end,:);
HH = mean(d_parameter(10:32:end,:));
MM = mean(d_parameter(11:32:end,:));
SS = mean(d_parameter(12:32:end,:));

if mean(GNSS_SEC) > 0 & HH > 0 & HH < 24 & MM > 0 & MM < 60 & SS > 0 & SS < 60
    GNSS_SEC_RESHAPE = reshape(GNSS_SEC,[l_lader_num,1]);
    has_gnss = true;
else
    warning('GNSS时间读取失败，使用脉冲序号代替');
    GNSS_SEC_RESHAPE = (1:l_lader_num)';  % 使用脉冲序号作为时间
    HH = 0;
    MM = 0;
    SS = 0;
    has_gnss = false;
end

%% 惯导时间校正 - 只有在有GNSS数据时才执行
if has_gnss && has_pps
 
    tic;
    disp('惯导时间校正');
    GNSS_SEC_RESHAPE = GNSS_SEC_RESHAPE + d_pps2start;
    
    GNSS_SEC_RESHAPE_C = GNSS_SEC_RESHAPE;
    
    % 时间序列校正
    DIFF_SEC = diff(GNSS_SEC_RESHAPE);
    INDEX_ABS_PLUS = find(DIFF_SEC>0.1);
    INDEX_ABS_MINUS = find(DIFF_SEC<-0.1);
    
    GNSS_SEC_RESHAPE = GNSS_SEC_RESHAPE_C;
    
    DIFF_SEC = diff(GNSS_SEC_RESHAPE);
    
    INDEX_ABS_PLUS = find(DIFF_SEC>0.1);
    INDEX_ABS_MINUS = find(DIFF_SEC<-0.1);
    
    if INDEX_ABS_PLUS(1)<INDEX_ABS_MINUS(1)
        % 第一段时间校正+1
        GNSS_SEC_RESHAPE_C(1:INDEX_ABS_PLUS(1)) = GNSS_SEC_RESHAPE_C(1:INDEX_ABS_PLUS(1)) + 1;
        % 后续时间段+1
        for I = 1:length(INDEX_ABS_MINUS)
            if length(INDEX_ABS_PLUS)>=I+1 % 还有后续时间段
                GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:INDEX_ABS_PLUS(I+1)) = ...
                    GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:INDEX_ABS_PLUS(I+1)) + 1;
            else
                % 最后时间段
                GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:end) = ...
                    GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:end) + 1;
            end
        end
    else
        % 第一段不需要校正，直接后续时间段+1
        for I = 1:length(INDEX_ABS_MINUS)
            if length(INDEX_ABS_PLUS)>=I % 还有后续时间段
                GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:INDEX_ABS_PLUS(I)) = ...
                    GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:INDEX_ABS_PLUS(I)) + 1;
            else
                % 最后时间段
                GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:end) = ...
                    GNSS_SEC_RESHAPE_C(INDEX_ABS_MINUS(I)+1:1:end) + 1;
            end
        end
    end
    GNSS_SEC_RESHAPE = GNSS_SEC_RESHAPE_C;
    
    toc;
else
    fprintf('跳过时间校正（无GNSS/PPS数据）\n');
    % 创建脉冲索引数组（1到总脉冲数）
    PULSE_INDEX = (1:l_lader_num)';
end
%%
tic;
disp('lidar回波数据处理及统计');
d_ladar = zeros([4 8 l_lader_num]);
d_ladar_photon_num = zeros([4 l_lader_num],"uint8");

% 初始化统计数组
N_STOP_ALL = zeros(l_udp_col, p_start_merge_num, 4);  % N×7×4
pulse_ch_stats = zeros(p_start_merge_num, 4);  % 7×4 脉冲-通道统计

% 记录每个光子的脉冲索引 - 使用矩阵，但保持完整大小
max_photons_per_ch = l_lader_num * 8;  % 最坏情况：每个脉冲8个回波
photon_pulse_indices = zeros(4, max_photons_per_ch);  % 4行，每行存储对应通道的脉冲索引
photon_counts = zeros(4, 1);  % 记录每个通道当前的光子计数

for i_col = 1:l_udp_col
    for i_row = 1:p_start_merge_num * 8     % 最多7个脉冲8个回波 
        i_ch = floor(d_data(i_row*4-3,i_col)/16);
        i_start_num = mod(d_data(i_row*4-3,i_col),16);
        f_data_zero = d_data(i_row*4-3,i_col) + d_data(i_row*4-2,i_col) + d_data(i_row*4-1,i_col)+d_data(i_row*4,i_col);
        
        if(f_data_zero)
            % 计算全局脉冲索引
            global_pulse_idx = (i_col-1)*p_start_merge_num + i_start_num + 1;
            
            % 记录脉冲索引（使用矩阵存储）
            ch_idx = i_ch + 1;  % 转换为1-4
            photon_counts(ch_idx) = photon_counts(ch_idx) + 1;
            photon_pulse_indices(ch_idx, photon_counts(ch_idx)) = global_pulse_idx;
            
            % 统计回波数
            d_ladar_photon_num(i_ch+1, global_pulse_idx) = d_ladar_photon_num(i_ch+1, global_pulse_idx) + 1;            
            
            % === 实时统计 ===
            current_count = d_ladar_photon_num(i_ch+1, global_pulse_idx);
            
            % 更新N_STOP_ALL（当前数据包的统计）
            if current_count <= 8
                N_STOP_ALL(i_col, i_start_num+1, i_ch+1) = current_count;
            end
            
            % 更新脉冲-通道统计
            if current_count <= 8
                pulse_ch_stats(i_start_num+1, i_ch+1) = pulse_ch_stats(i_start_num+1, i_ch+1) + 1;
            end
            
            % 解析数据
            if(current_count < 9)  % 现在有bug，数据可能会出现多余8个回波 
                % 细计数校准
                if(d_data(i_row*4,i_col)<26)
                    d_data(i_row*4,i_col) = 0;
                else
                    d_data(i_row*4,i_col) = round((d_data(i_row*4,i_col)-26)*1.584);
                end
                
                d_ladar(i_ch+1, current_count, global_pulse_idx) = ...
                    d_data(i_row*4-2,i_col)*256*256 + d_data(i_row*4-1,i_col)*256 + d_data(i_row*4,i_col);           
            end
        end
    end
end

% 不需要删除多余空间，保存时只取前photon_counts个

d_data_ch1 = (d_ladar(1,:,:)); 
d_data_ch1 = reshape(d_data_ch1,8,l_lader_num)';
d_data_ch2 = (d_ladar(2,:,:)); 
d_data_ch2 = reshape(d_data_ch2,8,l_lader_num)';
d_data_ch3 = (d_ladar(3,:,:)); 
d_data_ch3 = reshape(d_data_ch3,8,l_lader_num)';
d_data_ch4 = (d_ladar(4,:,:)); 
d_data_ch4 = reshape(d_data_ch4,8,l_lader_num)';

d_data_ch1 = d_data_ch1 - d_start;
d_data_ch2 = d_data_ch2 - d_start;
d_data_ch3 = d_data_ch3 - d_start;
d_data_ch4 = d_data_ch4 - d_start;

toc;
%% 编码值、时间、脉冲索引及h5文件写入
tic;
disp('编码值、时间、脉冲索引及h5文件写入');

% 准备时间数据
if has_gnss && has_pps
    d_time_8 = repmat(GNSS_SEC_RESHAPE,1,8);
else
    d_time_8 = repmat(PULSE_INDEX,1,8);  % 使用脉冲索引代替时间
end

d_motor1_encoder_8 = repmat(d_motor1_encoder,1,8);
d_start2start_8 = repmat(d_start2start,1,8);

% 写入N_STOP_ALL
hdf5write(dstFileName,'/N_STOP_ALL',uint8(N_STOP_ALL));



%% 保存到H5文件
for ch = 1:4
    % 根据通道选择正确的数据
    switch ch
        case 1
            d_data_ch = d_data_ch1;
        case 2
            d_data_ch = d_data_ch2;
        case 3
            d_data_ch = d_data_ch3;
        case 4
            d_data_ch = d_data_ch4;
    end
    
    % 创建掩码筛选有效数据
    mask = d_data_ch > 0;
    
    % 提取对应通道的数据
    d_time_ch = d_time_8(mask);
    d_start2start_ch = d_start2start_8(mask);
    d_motor1_encoder_ch = d_motor1_encoder_8(mask);
    ch_data_ch = d_data_ch(mask);
    pulse_circle_ch = pulse_circle_8(mask);
    
    % 从mask中获取该通道实际有回波的脉冲索引
    [rows, ~] = find(mask);  % rows就是该通道有回波的脉冲索引
    pulse_idx_ch = rows;  % 这是该通道特有的脉冲索引列表
    
    % 验证数据长度 - 现在应该全部一致
    data_lengths = [length(d_time_ch), length(pulse_idx_ch), ...
                    length(pulse_circle_ch), length(ch_data_ch)];
    
    if range(data_lengths) > 0
        error('通道%d数据严重不一致，终止处理', ch);
    end
    
    % 在没有GNSS的情况下，验证时间数据是否与脉冲索引对应
    if ~has_gnss
        % d_time_ch 应该是脉冲索引的副本，但可能因为数据源不同而不一致
        if ~isequal(d_time_ch, double(pulse_idx_ch))
            fprintf('  通道%d: 时间数据使用脉冲索引\n', ch);
            % 可以选择强制使用pulse_idx_ch作为时间
            d_time_ch = double(pulse_idx_ch);
        end
    end
    
    % 写入HDF5文件
    hdf5write(dstFileName, sprintf('/GNSS_SEC_CH%d', ch), d_time_ch, 'writemode', 'append');
    hdf5write(dstFileName, sprintf('/PULSE_INDEX_CH%d', ch), uint32(pulse_idx_ch), 'writemode', 'append');
    hdf5write(dstFileName, sprintf('/PULSE_CIRCLE_CH%d', ch), uint32(pulse_circle_ch), 'writemode', 'append');
    hdf5write(dstFileName, sprintf('/Photon_Start_Count_CH%d', ch), d_start2start_ch, 'writemode', 'append');
    hdf5write(dstFileName, sprintf('/Photon_CH%d_CODER', ch), d_motor1_encoder_ch, 'writemode', 'append');
    hdf5write(dstFileName, sprintf('/Photon_CH%d_DIST', ch), uint32(ch_data_ch), 'writemode', 'append');
    
    % 输出统计信息
    fprintf('  通道%d: %d个光子，分布在%d个不同脉冲上\n', ...
        ch, length(pulse_idx_ch), length(unique(pulse_idx_ch)));
end
%%
% 保存元数据
hdf5write(dstFileName, '/Hour', HH, 'writemode', 'append');
hdf5write(dstFileName, '/Minute', MM, 'writemode', 'append');
hdf5write(dstFileName, '/Second', SS, 'writemode', 'append');
hdf5write(dstFileName, '/TotalPulses', l_lader_num, 'writemode', 'append');
%% 写入状态信息（不使用结构体）
% 将logical转换为double或int
hdf5write(dstFileName, '/STATUS/HasGNSS', double(has_gnss), 'writemode', 'append');
hdf5write(dstFileName, '/STATUS/HasPPS', double(has_pps), 'writemode', 'append');

% 如果需要保存更多状态信息


fprintf('  点云数据维度: %d 脉冲 × %d 回波\n', size(d_data_ch1, 1), size(d_data_ch1, 2));
toc;
end