# Stage 7D 汇报提纲：00111 从 L1 到 L2/L3/最终坐标

## 1. 汇报主线

本次汇报建议按下面这条链讲：

```text
L1 原始数据
  -> L2 机体系/FRD 激光坐标
  -> L3 POS 匹配 + NED 偏移
  -> 最终 UTM/经纬度坐标
```

其中 00111 用来展示中间过程图，`00050-00150` 的 95 个文件作为可展示候选成果。

## 2. L1 原始数据是什么

L1 是原始 H5 中 CH1 的逐点观测量，还没有形成空间点云。

00111 文件：

```text
D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\0510_f3\L1-TIME_ANGE_DIST_DATA\L1_cap_00111_20260510190957.h5
```

主要字段：

- `GNSS_SEC_CH1`：原始激光点时间。
- `Photon_CH1_DIST`：原始距离计数。
- `Photon_CH1_CODER`：扫描编码器值。
- `PULSE_INDEX_CH1` / `PULSE_CIRCLE_CH1`：脉冲索引信息。
- `Photon_Start_Count_CH1`：光子起始计数。

工程处理：

```text
gps_time = GNSS_SEC_CH1 + 18 s
range_before_m = Photon_CH1_DIST * 2e-9 / 256 * 3e8 / 2
raw_scan_angle = Photon_CH1_CODER * 360 / 65536
```

这一阶段的图主要展示：

- 原始距离随时间变化。
- 编码器扫描相位随时间变化。
- 原始距离分布。
- 脉冲索引连续性。

## 3. L1 到 L2：生成机体系/FRD 激光坐标

L2 的目标是把 L1 中的“距离 + 扫描编码器”转换成传感器/机体系下的三维激光向量。

本项目的 Stage 7A 中，L2 字段保存在：

```text
C:\proj_denoising_f3_2.0\h5\stage7a_00111_ch1_ladm2_full_points.h5
dataset: /STAGE7A/CH1/full_points
```

主要 L2 字段：

- `range_before_m`
- `range_m`
- `coder`
- `scan_angle_deg`
- `frd_x_m`
- `frd_y_m`
- `frd_z_m`

这里的 `frd_x_m/frd_y_m/frd_z_m` 是机体系/FRD 坐标下的激光点方向与距离结果。

## 4. 这里用了曹彬才论文的什么内容

用到的是：

```text
《遥感测深数据处理方法研究_曹彬才.pdf》
第 4.4.2 节 LADM-II 扫描几何
公式 4-7 到 4-14
```

具体用法：

- 使用论文中 LADM-II 反射镜扫描几何思想。
- 从反射镜法线、入射光方向、反射光方向建立激光出射方向。
- 使用反射镜倾角，论文中典型值为约 `7.5°`。
- 使用坐标系旋转关系，论文中涉及约 `45°` 的坐标变换。
- 由扫描编码器角度推导激光方向，而不是简单把扫描角当成圆形 `sin/cos` 扫描。

本项目 Stage 6I/6K/7A 的最终候选参数为：

- `mirror_tilt_deg = 7.75`
- `frame_rotation_deg = -45.0`
- `angle_direction = 360-angle`
- `angle_offset_deg = 298.9`
- `axis_mapping = F=+Y, R=-X, D=-Z`
- `boresight roll/pitch/yaw = 0.0, -2.0, 2.0 deg`
- `lever x/y/z = 0.011067, -0.164929, 0.033791 m`

这些参数不是直接照抄论文给定常数，而是在论文 LADM-II 几何形式基础上，用 00111 参考 L3 exact-time 验证搜索得到的项目候选参数。

需要特别说明：

本项目没有声称完整逐项复现论文第 4.4 节全部直接地理定位公式。当前主要采用了第 4.4.2 节的 LADM-II 扫描几何来替换旧的经验 `f_body_frame_xyz()`。POS 到导航系、UTM 最终坐标部分使用项目已有 POS 插值、姿态旋转和 pyproj/UTM 流程。

## 5. L2 到 L3：POS 匹配

L3 的目标是把 L2 的机体系激光向量和飞机 POS 轨迹匹配起来。

Stage 7A H5 中保存的 POS 匹配字段：

- `pos_time_sec`
- `pos_easting`
- `pos_northing`
- `pos_height`
- `pos_roll`
- `pos_pitch`
- `pos_heading`
- `pos_interp_dt`
- `pos_quality_flag`

处理逻辑：

```text
1. 用 L1 点的 gps_time 找到相邻 POS 时刻。
2. 对 POS 的 easting/northing/height/roll/pitch 做线性插值。
3. 对 heading 做角度展开后的插值，避免 0/360 度跳变。
4. 计算 pos_interp_dt，检查激光点和最近 POS 时间的距离。
5. 标记 pos_quality_flag。
```

Stage 7B 结果：

- 95 个候选文件 POS success rate 为 `100%`。
- `pos_interp_dt` 的 p99 最大值约 `0.002475 s`。

## 6. L3 到最终坐标

L3 中还保存了机体系向导航系旋转后的 NED 偏移：

- `north_offset_m`
- `east_offset_m`
- `down_offset_m`

最终坐标计算关系为：

```text
final_easting  = pos_easting  + east_offset_m
final_northing = pos_northing + north_offset_m
final_height   = pos_height   - down_offset_m
```

最终结果字段：

- `easting_m`
- `northing_m`
- `height_m`
- `lon`
- `lat`

本次 MATLAB 脚本不再画最终结果，因为 Stage 7A/7D 已经导出 LAZ/TXT 并在 CloudCompare 中检查过。

## 7. 当前可展示成果结论

Stage 7D 最终判定：

```text
DISPLAY_CANDIDATE_APPROVED_WITH_NOTES
```

含义：

- `00050-00150` 中 95 个 Stage 7A 文件可作为展示候选成果。
- 6 个坏时间文件排除：`00054`, `00073`, `00093`, `00113`, `00132`, `00133`。
- `00144-00145` 有 `0.12666 s` 时间间隔，但 CloudCompare 目视未见明显水平错位、高程错层或条带断裂，因此作为注意事项记录，不判定为几何失败。

## 8. MATLAB 图件脚本

脚本位置：

```text
D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\scripts\matlab\stage7d_00111_l1_l2_l3_demo.m
```

运行后输出：

```text
C:\proj_denoising_f3_2.0\stage7d_teacher_package\matlab_figures\stage7d_00111_L1_raw.png
C:\proj_denoising_f3_2.0\stage7d_teacher_package\matlab_figures\stage7d_00111_L2_FRD.png
C:\proj_denoising_f3_2.0\stage7d_teacher_package\matlab_figures\stage7d_00111_L3_POS_NED.png
```

三张图分别对应：

- L1 原始距离/扫描编码器/脉冲连续性。
- L2 LADM-II 后的 FRD/body 点云。
- L3 POS 匹配后的轨迹、NED 偏移、POS 插值时间误差和姿态角。
