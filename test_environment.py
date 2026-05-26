import sys

def test_environment():
    print("=" * 60)
    print("Python 深度学习环境测试")
    print("=" * 60)

    print(f"\nPython 版本: {sys.version}")

    try:
        import torch
        print(f"\nPyTorch 版本: {torch.__version__}")
        print(f"CUDA 可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA 版本: {torch.version.cuda}")
            print(f"GPU 设备: {torch.cuda.get_device_name(0)}")
            print(f"GPU 数量: {torch.cuda.device_count()}")
            x = torch.rand(3, 3).cuda()
            print(f"GPU 张量计算测试: 通过")
        else:
            print("当前使用 CPU 模式")
            x = torch.rand(3, 3)
            print(f"CPU 张量计算测试: 通过")
    except ImportError:
        print("\nPyTorch: 未安装")

    try:
        import torchvision
        print(f"\nTorchvision 版本: {torchvision.__version__}")
    except ImportError:
        print("\nTorchvision: 未安装")

    try:
        import torchaudio
        print(f"Torchaudio 版本: {torchaudio.__version__}")
    except ImportError:
        print("Torchaudio: 未安装")

    try:
        import tensorflow as tf
        print(f"\nTensorFlow 版本: {tf.__version__}")
        gpus = tf.config.list_physical_devices("GPU")
        print(f"TensorFlow GPU 设备: {len(gpus)}")
    except ImportError:
        print("\nTensorFlow: 未安装")

    try:
        import numpy as np
        print(f"\nNumPy 版本: {np.__version__}")
    except ImportError:
        print("\nNumPy: 未安装")

    try:
        import pandas as pd
        print(f"Pandas 版本: {pd.__version__}")
    except ImportError:
        print("Pandas: 未安装")

    try:
        import cv2
        print(f"OpenCV 版本: {cv2.__version__}")
    except ImportError:
        print("OpenCV: 未安装")

    try:
        import matplotlib
        print(f"Matplotlib 版本: {matplotlib.__version__}")
    except ImportError:
        print("Matplotlib: 未安装")

    try:
        import sklearn
        print(f"Scikit-learn 版本: {sklearn.__version__}")
    except ImportError:
        print("Scikit-learn: 未安装")

    try:
        import timm
        print(f"timm 版本: {timm.__version__}")
    except ImportError:
        print("timm: 未安装")

    try:
        import ultralytics
        print(f"Ultralytics 版本: {ultralytics.__version__}")
    except ImportError:
        print("Ultralytics: 未安装")

    try:
        import onnx
        print(f"ONNX 版本: {onnx.__version__}")
    except ImportError:
        print("ONNX: 未安装")

    print("\n" + "=" * 60)
    print("环境测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_environment()
