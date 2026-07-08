function [corrected_ranges, zero_peak] = calibrate_range(file_data, channel_num, peak_range, coeffs)
    % 处理单个文件的函数
    
    % 加载校正系数（一次性）
    


    % 参数设置
    
    bin_width = 0.01875;
    fit_range = 0.5;
    
    % 查找零位峰
    zero_peak = findZeroPeak(file_data, peak_range, bin_width, fit_range);
    
    if isnan(zero_peak)
        corrected_ranges = all_ranges;  % 如果找不到零位峰，返回原值
        return;
    end
    ch = fieldnames(coeffs);
    % 应用校正
    ch_name = ch{channel_num};
    zero_offset = coeffs.(ch_name).zero_offset;
    slope = coeffs.(ch_name).slope;
    intercept = coeffs.(ch_name).intercept;
    
    % 校正公式：先减当前零位，再用保存的参数校正
    corrected_ranges = (file_data - zero_peak - intercept) / slope;
    
    fprintf('通道%d: 零位峰=%.3f m, 平均距离=%.3f m\n', ...
            channel_num, zero_peak, mean(corrected_ranges));
end