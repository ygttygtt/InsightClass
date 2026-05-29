#!/bin/bash
# ============================================================
# InsightClass 服务器一键环境配置脚本
# 用法: bash scripts/server_setup.sh
# ============================================================
set -e

# 切到项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================="
echo " InsightClass 服务器环境配置"
echo " 项目根目录: $PROJECT_ROOT"
echo "=========================================="

# ---- 1. 检查 Python ----
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[错误] 未找到 Python，请先安装 Python 3.10+"
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo "[1/5] Python: $PY_VERSION ($PYTHON)"

# ---- 2. 创建 venv ----
VENV_DIR="$PROJECT_ROOT/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "[2/5] venv 已存在，跳过创建: $VENV_DIR"
else
    echo "[2/5] 创建 venv..."
    $PYTHON -m venv "$VENV_DIR"
    echo "      venv 创建完成"
fi

# 激活 venv
source "$VENV_DIR/bin/activate"
echo "      已激活 venv: $(which python)"

# ---- 3. 安装依赖 ----
echo "[3/5] 安装项目依赖..."
pip install --upgrade pip -q
pip install -e ".[ultralytics,dev]" -q
echo "      依赖安装完成"

# 验证关键包
python -c "
import torch
import ultralytics
print(f'      PyTorch {torch.__version__}  CUDA={torch.cuda.is_available()}')
print(f'      Ultralytics {ultralytics.__version__}')
"

# ---- 4. 生成数据集配置 ----
DATASET_ROOT="data/processed/classroom_behavior_v2"
DATASET_YAML="$DATASET_ROOT/dataset.yaml"

if [ -d "$DATASET_ROOT" ]; then
    echo "[4/5] 生成 dataset.yaml（适配 Linux 路径）..."
    python -m insightclass write-yolo-yaml \
        --dataset-root "$DATASET_ROOT" \
        --class-config configs/classes.yaml \
        --output "$DATASET_YAML"
    echo "      已生成: $DATASET_YAML"
else
    echo "[4/5] [跳过] 数据集目录不存在: $DATASET_ROOT"
    echo "      请先上传并解压数据集，然后重新运行此脚本"
fi

# ---- 5. 运行数据集检查 ----
if [ -d "$DATASET_ROOT" ]; then
    echo "[5/5] 运行数据集质量检查..."
    mkdir -p reports
    python -m insightclass inspect-yolo \
        --dataset-root "$DATASET_ROOT" \
        --class-config configs/classes.yaml \
        --output reports/v2_inspection.json
    echo "      检查报告: reports/v2_inspection.json"
else
    echo "[5/5] [跳过] 无数据集，跳过检查"
fi

# ---- 完成 ----
echo ""
echo "=========================================="
echo " 环境配置完成！"
echo ""
echo " 激活环境:  source .venv/bin/activate"
echo " 开始训练:  bash scripts/server_train.sh"
echo "=========================================="
