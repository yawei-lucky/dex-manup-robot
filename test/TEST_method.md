# VLM 决策日志可视化

## 一键运行（推荐）

跑机器人时另开一个终端：

```bash
cd ~/robotics/dex-manup-robot
bash test/run_vlm_visualizer.sh
```

会自动找最新的 `runtime/logs/navila_client_*.log`，启动 watch（每 3s 重生成 HTML），然后打开浏览器自动刷新。Ctrl-C 退出。

### 可选参数

```bash
# 看历史 log（事后回放）
bash test/run_vlm_visualizer.sh runtime/logs/navila_client_YYYYMMDD_HHMMSS.log

# 改刷新频率（秒）
VLM_VIS_INTERVAL=1 bash test/run_vlm_visualizer.sh
```

## 手动模式（调试 analyze_vlm_log.py 时用）

```bash
cd ~/robotics/dex-manup-robot

# 事后看一次：
log=$(ls -t runtime/logs/navila_client_*.log | head -1)
python3 test/analyze_vlm_log.py --oldest-first "$log"
xdg-open "${log%.log}.html"

# 实时看：
log=$(ls -t runtime/logs/navila_client_*.log | head -1)
python3 test/analyze_vlm_log.py --watch --oldest-first "$log"   # 终端 A
xdg-open "${log%.log}.html"                                      # 终端 B
```
