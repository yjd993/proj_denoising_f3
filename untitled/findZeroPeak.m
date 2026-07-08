function zero_peak = findZeroPeak(data, peak_range, bin_width, fit_range)
    % 简化的零位峰值查找函数
    % 输入：
    %   data - 原始距离数据矩阵
    %   peak_range - 零位峰值范围 [min, max]
    %   bin_width - 直方图bin宽度
    %   fit_range - 拟合范围
    % 输出：
    %   zero_peak - 零位峰值中心（米）
    %   all_ranges - 所有有效距离数据
    
    % 拉直矩阵，并去掉0
    all_ranges = data(:);
    all_ranges = all_ranges(all_ranges > 0);
    
    if isempty(all_ranges)
        zero_peak = NaN;
        return;
    end
    
    % 提取峰值范围内的数据
    range_min = peak_range(1);
    range_max = peak_range(2);
    range_data = all_ranges(all_ranges >= range_min & all_ranges <= range_max);
    
    if isempty(range_data)
        zero_peak = NaN;
        return;
    end
    
    % 计算直方图找峰值（初始猜测）
    edges_peak = range_min:bin_width:range_max;
    [counts_peak, ~] = histcounts(range_data, edges_peak);
    
    % 找到最大值的位置
    [~, max_idx] = max(counts_peak);
    peak_center_initial = edges_peak(max_idx) + bin_width/2;
    
    % 在峰值位置±fit_range米范围内进行高斯拟合
    fit_min = max(0, peak_center_initial - fit_range);
    fit_max = peak_center_initial + fit_range;
    
    % 提取拟合范围内的数据
    fit_data = all_ranges(all_ranges >= fit_min & all_ranges <= fit_max);
    
    if length(fit_data) < 10
        zero_peak = peak_center_initial;  % 使用初始估计
        return;
    end
    
    % 计算拟合范围的直方图
    edges_fit = fit_min:bin_width:fit_max;
    [counts_fit, bin_centers_fit] = histcounts(fit_data, edges_fit);
    bin_centers_fit = bin_centers_fit(1:end-1) + bin_width/2;
    
    % 高斯拟合
    gauss_func = @(p, x) p(1) * exp(-(x - p(2)).^2 / (2 * p(3)^2));
    initial_guess = [max(counts_fit), peak_center_initial, std(fit_data)];
    
    options = optimset('Display', 'off');
    try
        params = lsqcurvefit(gauss_func, initial_guess, bin_centers_fit, counts_fit, [], [], options);
        zero_peak = params(2);  % 使用高斯拟合的峰值中心
    catch
        zero_peak = peak_center_initial;  % 拟合失败，使用初始估计
    end
end