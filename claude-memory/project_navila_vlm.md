---
name: project-navila-vlm
description: NaVILA 闭环系统配置、VLM 后端（Qwen 主用 / Gemini 备用）、当前默认参数
metadata: 
  node_type: memory
  type: project
  originSessionId: f66f4c94-6efa-465a-838e-a723b751d534
---

NaVILA 闭环仿真导航系统（最近更新：2026-05-14）。

**Why:** 机器人导航任务。VLM 后端从原版 NaVILA LLaVA → Gemini → **Qwen3.6-flash**（当前主用）。

## 系统架构
- 本地机器：MuJoCo 仿真 + Holosoma 策略 + navila_stream_client + bridge gate + 手动控制台
- VLM server：本地 `vlm_server_qwen.py`（调用阿里云 DashScope）
- 启动 server：`DASHSCOPE_API_KEY=<key> python3 others/vlm_server_qwen.py --port 54321`
- 启动闭环：`NAVILA_NO_VLM=0 VLM_HOST=localhost VLM_PORT=54321 bash test/launch_navila_closed_loop.sh`

## VLM 后端历史
1. **NaVILA 原版 LLaVA**（100.110.59.37:54321）：免费但导航能力弱，几乎只输出 `move forward 75cm`，距离感差
2. **Gemini**（vlm_server_gemini.py）：模型强但**国内代理不稳定**（key 间歇丢失 / 限地区免费配额），现已弃用
3. **Qwen3.6-flash**（vlm_server_qwen.py）：**当前主用**，国内 API 直连，效果好，免费额度 100 万 token / 模型 / 180 天

## 当前默认参数（2026-05-14）
| 项 | 值 | 来源 |
|---|---|---|
| 场景 | `indoor_red_shoebox` | `mujoco.py` 的 `NAVILA_SCENE` |
| Prompt | `prompt_red_shoebox.json` | `launch_navila_closed_loop.sh` 的 `PROMPT_JSON` |
| VLM 模型 | `qwen3.6-flash` | `vlm_server_qwen.py --model` |
| thinking 模式 | **关闭**（instant）| Qwen3.6 默认开，需显式传 `enable_thinking=False`（脚本默认）|
| 帧数 | 4 | `NAVILA_KEEP_LAST` |
| 相机间隔 | 0.667 s | `NAVILA_MUJOCO_FRAME_INTERVAL` → 4 帧跨度恰好 2 秒 |
| 终端 filter | 0（关闭）| `NAVILA_TERMINAL_FILTER` |
| 客户端请求间隔 | 0.2 s | `NAVILA_CLIENT_INTERVAL_SEC`（用户曾要求过 3.0 s）|

## MuJoCo 场景系统
`scene_manager.py` 提供三种场景，由 `NAVILA_SCENE` env var 选择：
- `table_black_bag`（原版）：橙桌 + 黑色袋状物
- `red_shoebox`：空地上的红鞋盒在 80cm 高黑大盒子上
- `indoor_red_shoebox`（**默认**）：4 面墙室内 + 红鞋盒目标 + 办公室杂物（纸箱、桌椅、显示器、PC 主机）

目标在 (3.5, 0)，黑大盒子高 80cm（人形手部高度）。

## 已修复的 Bug
1. `set -o pipefail` + log rotation 在无日志时退出 → 加 `|| true`
2. `python` → `python3`（Ubuntu 22.04）
3. tee/awk 管道块缓冲导致终端显示延迟 → 加 `stdbuf -oL`
4. `sample_to_8_frames` 写死 8 帧 → 改成 `sample_to_n_frames(n)` 用 `--keep-last` 控制

## 关键调试经验
- **代理问题**：Gemini 在国内代理（Clash/Mihomo）下，节点不稳定会让 key 间歇丢失（错误为 `API Key not found`，不是 `invalid`）。需指定固定的美/日/新加坡节点。Hong Kong 不支持。
- **Qwen3.6 默认开 thinking** → 推理 17-32s。必须传 `enable_thinking=False` 才能进 instant 模式（几秒）。Qwen3-VL 系列默认就关。
- **VLM 距离判断不准**：模型容易把"大件黑色物体"当成"近"，需要在 prompt 里强调"以红鞋盒判距离，不要看黑盒子"
- **3s 推理 + 2s 窗口的盲区问题**：连续请求之间有 1s 的盲时段，窗口跨度建议 >= 推理时间

## VLM 输出格式（prompt 强制）
```
Reason: <approximate distance to RED shoe box in meters>, <direction>
<action>
```
direction 标签：front-left / front-right / left / right / center / lost-was-left / lost-was-right / never-seen

## 代理状态（2026-05-14）
**已关闭**（`~/.bashrc` 中代理 export 已注释）。要恢复用 Gemini 需重新启用：取消 `~/.bashrc` line 118-123 的注释。

## How to apply
- 默认配置无需任何 env var，直接 `bash test/launch_navila_closed_loop.sh` 即可
- 切换场景：`NAVILA_SCENE=red_shoebox` 或 `NAVILA_SCENE=table_black_bag`
- 切换 VLM 模型：`python3 others/vlm_server_qwen.py --model qwen3-vl-flash`
