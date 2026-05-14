---
name: project-env-setup
description: Environment setup status for robotics simulation on this machine
metadata: 
  node_type: memory
  type: project
  originSessionId: f66f4c94-6efa-465a-838e-a723b751d534
---

新电脑环境安装完成（2026-05-13）。

**Why:** 新机器需要从零安装仿真所需依赖，VLM 部分不在此机器上。

**已安装内容：**
- ROS2 Humble：`/opt/ros/humble/`，已加入 `~/.bashrc`
- Conda：`~/.holosoma_deps/miniconda3/`
- `hsinference` conda env：holosoma_inference 包，unitree_sdk2_python，pinocchio
- `hsmujoco` conda env：mujoco 3.8.1（--no-warp，CPU-only）
- 系统包：terminator, wmctrl, xdotool, pillow（已系统预装）
- `~/robotics/holosoma` → `~/robotics/nav_holosoma` 软链接
- ufw sudo 免密：`/etc/sudoers.d/stf3-ufw-status`
- sudo 全免密：`/etc/sudoers.d/stf3-nopasswd`

**How to apply:** 运行仿真前确认 hsinference env 和 ROS2 已 source。
