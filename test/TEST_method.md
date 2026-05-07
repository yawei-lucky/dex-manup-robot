# VLM 决策日志可视化

## 离线分析（跑完之后看）

```bash
cd ~/robotics/dex-manup-robot

log=$(ls -t runtime/logs/navila_client_*.log | head -1)
python3 test/analyze_vlm_log.py --oldest-first "$log"
xdg-open "${log%.log}.html"
```

## 实时分析（跑机器人时同时开）

```bash
cd ~/robotics/dex-manup-robot

# 终端 A：watch 模式（每 3 秒刷新）
log=$(ls -t runtime/logs/navila_client_*.log | head -1)
python3 test/analyze_vlm_log.py --watch "$log"

# 终端 B：打开浏览器（只需一次，之后自动刷新）
log=$(ls -t runtime/logs/navila_client_*.log | head -1)
xdg-open "${log%.log}.html"
```
