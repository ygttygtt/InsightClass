#!/bin/bash
# ============================================================
# InsightClass 服务器训练启动脚本
# 用法:
#   bash scripts/server_train.sh              # 默认 yolo11n, 前台运行
#   bash scripts/server_train.sh yolo26n      # 使用 yolo26n
#   bash scripts/server_train.sh yolo11n bg   # 后台运行 (nohup)
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ---- 参数解析 ----
MODEL="${1:-yolo11n}"
MODE="${2:-}"

# 根据模型名选择配置文件
case "$MODEL" in
    yolo11n)
        CONFIG="configs/training_v2_ultralytics.yaml"
        ;;
    yolo26n)
        CONFIG="configs/training_v2_ultralytics_yolo26n.yaml"
        ;;
    *)
        echo "[错误] 未知模型: $MODEL"
        echo "支持的模型: yolo11n, yolo26n"
        exit 1
        ;;
esac

# 检查配置文件
if [ ! -f "$CONFIG" ]; then
    echo "[错误] 配置文件不存在: $CONFIG"
    exit 1
fi

# 检查模型权重
WEIGHTS_FILE="${MODEL}.pt"
if [ ! -f "$WEIGHTS_FILE" ]; then
    echo "[错误] 模型权重不存在: $WEIGHTS_FILE"
    echo "请确保 yolo11n.pt 和 yolo26n.pt 在项目根目录"
    exit 1
fi

# 激活 venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "[错误] venv 不存在，请先运行: bash scripts/server_setup.sh"
    exit 1
fi

# 读取配置中的 run_name
RUN_NAME=$(grep "^run_name:" "$CONFIG" | awk '{print $2}')

echo "=========================================="
echo " InsightClass 训练启动"
echo " 模型:     $MODEL"
echo " 配置:     $CONFIG"
echo " 实验名:   $RUN_NAME"
echo " GPU:      $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
echo "=========================================="

# ---- 后台模式 ----
if [ "$MODE" = "bg" ]; then
    LOGFILE="train_${MODEL}_$(date +%Y%m%d_%H%M%S).log"
    echo "后台运行，日志: $LOGFILE"
    nohup python -m insightclass train --config "$CONFIG" > "$LOGFILE" 2>&1 &
    PID=$!
    echo "PID: $PID"
    echo ""
    echo "查看日志:  tail -f $LOGFILE"
    echo "查看 GPU:  watch -n 1 nvidia-smi"
    echo "停止训练:  kill $PID"
else
    echo "前台运行 (Ctrl+C 可中断，加 bg 参数可后台运行)"
    echo ""
    python -m insightclass train --config "$CONFIG"
fi
