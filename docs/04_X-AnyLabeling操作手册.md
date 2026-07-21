# X-AnyLabeling 操作手册

> 用于为 InsightClass 四类行为创建 YOLO 检测框。X-AnyLabeling 不同版本的菜单
> 名称和快捷键可能变化，以安装版本的帮助页面为准。

## 1. 标签与顺序

标签顺序必须和 `configs/classes.yaml` 完全一致：

```text
phone_use
talking
sleeping
standing
```

对应 YOLO 类别编号：

| class_id | 标签 | 中文 |
|---:|---|---|
| 0 | `phone_use` | 玩手机 |
| 1 | `talking` | 交谈 |
| 2 | `sleeping` | 打瞌睡 |
| 3 | `standing` | 站立 |

调整顺序会让已有标注和模型含义错位。不要为同一数据集使用不同版本的
`classes.txt`。

## 2. 安装与启动

建议根据 X-AnyLabeling 官方仓库的当前版本安装：

```bash
git clone https://github.com/CVHub520/X-AnyLabeling.git
cd X-AnyLabeling
python -m pip install -U uv
uv pip install -e ".[cpu]"
xanylabeling
```

GPU 版本、CUDA 兼容矩阵和模型下载方式以其官方说明为准。标注环境和
InsightClass 训练环境可以分开，避免 Qt、CUDA 或模型依赖冲突。

## 3. 准备标签

创建 `classes.txt`：

```text
phone_use
talking
sleeping
standing
```

在 X-AnyLabeling 中导入预定义标签，或在用户配置中设置同样的顺序。建议为常用
类别设置数字快捷键：

| 按键 | 标签 |
|---:|---|
| 1 | `phone_use` |
| 2 | `talking` |
| 3 | `sleeping` |
| 4 | `standing` |

## 4. 标注流程

1. 打开 `data/processed/<dataset>/images/train/`。
2. 使用矩形框圈出发生目标行为的学生主体。
3. 选择四个稳定标签之一，不使用中文标签名。
4. 检查框、类别和遗漏目标后保存。
5. 对 `val/` 和 `test/` 使用相同规范，但不要根据模型结果降低人工检查标准。

常用操作通常包括：

| 操作 | 常见快捷键 |
|---|---|
| 矩形框 | `R` |
| 上一张/下一张 | `A` / `D` |
| 删除选中框 | `Delete` |
| 撤销 | `Ctrl+Z` |
| 保存 | `Ctrl+S` |

快捷键可能随系统和版本变化，应在工具内确认后再制定团队速查表。

## 5. AI 辅助标注

通用 person 检测模型可先生成学生框，再由标注者修改为行为标签。它不能可靠替代
行为判断：

- 自动框必须逐个确认位置和主体归属。
- `talking` 与普通转头、`sleeping` 与低头写字需要人工结合上下文判断。
- `standing` 需要确认是学生主体且姿态满足规范。
- 模型漏检、误检和类别偏见应记录为难例。

文本提示检测可使用 `student using phone`、`student sleeping`、
`standing student` 等描述，但最终标签仍以 [标注规范](05_标注规范.md) 为准。

## 6. 大模型辅助

支持视觉输入的大模型可以辅助复核模糊样本，但不得直接批量写入最终标签。示例
提示词：

```text
请只根据画面证据判断被框选学生是否属于以下一种行为：
phone_use、talking、sleeping、standing。
如果证据不足，请回答 uncertain，并说明缺少的视觉证据。
```

注意：

- 纯文本模型不能理解图片。
- 云端多模态 API 会接收图片数据，上传前必须确认数据授权和服务条款。
- API Key 只保存在本地工具配置中，不进入项目、截图或标注导出文件。
- 大模型结论是复核线索，不是标签真值。

## 7. 导出 YOLO 标签

导出时选择 YOLO 检测格式并加载上述 `classes.txt`。每张图片对应同名 `.txt`：

```text
<class_id> <x_center> <y_center> <width> <height>
```

坐标应归一化到 `0..1`。没有目标行为的有效负样本可以保留空标签文件；损坏、
无关或无法判断的图片应移出数据集，而不是一律当作负样本。

建议目录结构：

```text
data/processed/<dataset>/
|-- images/
|   |-- train/
|   |-- val/
|   `-- test/
`-- labels/
    |-- train/
    |-- val/
    `-- test/
```

## 8. 导出后质检

在项目根目录运行：

```powershell
insightclass inspect-yolo `
  --dataset-root data/processed/<dataset> `
  --class-config configs/classes.yaml `
  --output reports/dataset_inspection.json

insightclass write-yolo-yaml `
  --dataset-root data/processed/<dataset> `
  --class-config configs/classes.yaml `
  --output data/processed/<dataset>/yolo_dataset.yaml
```

还应人工抽查：

- 四类是否都有样本，类别编号是否正确
- 框是否越界、过松、过紧或覆盖邻座主体
- 同源相邻帧是否跨 train/val/test
- 难例在不同标注者之间是否口径一致
- 负样本是否真实无目标，而不是漏标

## 9. 团队协作

- 先共同标注一小批校准集，讨论分歧后再分工。
- 每轮至少交叉抽查 5%，低频类和难例提高抽查比例。
- 不在文件名、标签或提交记录中写真实姓名、学号或摄像头凭据。
- 数据集版本冻结后保存类别表、Manifest、质检报告和标注工具版本。
