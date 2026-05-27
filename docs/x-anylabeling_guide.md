# X-AnyLabeling 操作手册 — 课堂行为检测标注指南

> 本手册针对 InsightClass 项目的三个标签：`phone_use`（玩手机）、`talking`（交谈）、`sleeping`（打瞌睡）

---

## 1. 安装与启动

### 1.1 安装（推荐 Git 克隆方式）

```bash
git clone https://github.com/CVHub520/X-AnyLabeling.git
cd X-AnyLabeling

# 安装 uv（如果没有）
pip install -U uv

# CPU 版本
uv pip install -e ".[cpu]"

# 或 GPU 版本（CUDA 12.x）
uv pip install -e ".[gpu]"
```

### 1.2 启动

```bash
xanylabeling
```

### 1.3 预定义标签配置

启动后，先在用户目录的 `.xanylabelingrc` 文件中配置你的标签：

```yaml
labels:
- phone_use
- talking
- sleeping
```

或者通过菜单栏 `Upload` -> `Upload Label Classes File` 上传一个 `classes.txt` 文件：
```
phone_use
talking
sleeping
```

---

## 2. 核心功能一览

X-AnyLabeling 有三大 AI 辅助窗口，加上主窗口的自动标注功能：

| 功能 | 快捷键 | 用途 | 对你的帮助 |
|------|--------|------|-----------|
| **主窗口** | - | 矩形框标注 + 自动标注 | 日常画框标注 |
| **聊天机器人** | `Ctrl+1` | 与 LLM 对话，图片问答 | 辅助判断、生成描述 |
| **视觉问答 (VQA)** | `Ctrl+2` | 结构化问答标注 | 生成训练数据 |
| **图像分类器** | `Ctrl+3` | 图像级分类 | 快速筛选/分类图片 |
| **视频分类器** | `Ctrl+5` | 视频片段分类 | 视频行为切分 |

---

## 3. 主窗口：矩形框标注（你的主要工作区）

### 3.1 导入图片

1. 菜单栏 `文件` -> `打开目录`（或 `Ctrl+U`）
2. 选择你的截帧图片目录（如 `data/annotation_batch_01/`）
3. 图片会加载到左侧面板

### 3.2 基本画框操作

| 操作 | 方法 |
|------|------|
| 画矩形框 | 按 `R` 键，或点击左侧工具栏矩形图标，然后在图片上拖拽 |
| 切换到编辑模式 | 按 `Ctrl+E`，或按 `Ctrl+J` 在绘制/编辑模式间切换 |
| 删除选中对象 | 选中后按 `Delete` |
| 撤销 | `Ctrl+Z` |
| 复制/粘贴对象 | `Ctrl+C` / `Ctrl+V` |
| 切换上/下一张图 | `A` / `D` |

### 3.3 标注流程

1. 按 `R` 进入矩形绘制模式
2. 在图片中某个学生身上拖拽画框
3. 弹出标签输入框，输入 `phone_use` / `talking` / `sleeping`
4. 画完后按 `Ctrl+J` 切回编辑模式
5. 按 `D` 切到下一张继续

**提示**：勾选 `Ctrl+Y`（自动使用上一个标签）可以省去重复输入标签名的步骤。如果连续标注同一类行为，这个功能非常有用。

### 3.4 使用数字快捷键加速

通过菜单栏 `工具` -> `数字快捷键管理器`（`Alt+D`），配置：

| 数字键 | 绘制模式 | 标签 |
|--------|----------|------|
| 1 | rectangle | phone_use |
| 2 | rectangle | talking |
| 3 | rectangle | sleeping |

配置后，按 `1` 直接进入画框模式并自动设为 `phone_use`，极大提速。

### 3.5 自动标注（AI 辅助画框）

这是 X-AnyLabeling 最强大的功能之一。操作步骤：

1. 点击左侧工具栏的模型图标，或按 `Ctrl+A` 打开自动标注
2. 选择一个目标检测模型，推荐：
   - **YOLOv8s / YOLO11s**（通用目标检测，检测 "person"）
   - **YOLOv8s-Pose**（姿态估计，可以辅助判断打瞌睡）
3. 模型会自动在当前图片上生成检测框
4. 你只需**修改标签名**（从 `person` 改为 `phone_use` / `talking` / `sleeping`）并**修正框的位置**
5. 对于模型漏检的目标，手动补画

**GroundingDINO（文本提示检测）**：如果你安装了 GroundingDINO 模型，可以用自然语言描述来检测：
- 输入文本提示：`"person using phone"` 或 `"student sleeping"`
- 模型会自动找到匹配的目标并画框

**GroundingSAM（检测+分割联合）**：结合 GroundingDINO 和 SAM，先检测再精确分割。

---

## 4. 聊天机器人（Ctrl+1）— LLM 对话助手

### 4.1 这是什么？

聊天机器人是一个集成在标注工具里的 AI 对话窗口，支持接入多种大语言模型（LLM）。你可以：
- 用自然语言和 AI 对话
- 发送当前图片给 AI 分析（用 `@image` 命令）
- 批量处理多张图片
- 导出对话数据用于模型微调

### 4.2 配置 LLM

1. 按 `Ctrl+1` 打开聊天机器人
2. 在**左侧面板**选择模型提供商：

| 提供商 | 说明 | 获取 API Key |
|--------|------|-------------|
| **Qwen（通义千问）** | 国内推荐，阿里云百炼 | [百炼控制台](https://bailian.console.aliyun.com/) |
| **DeepSeek** | 国内推荐，性价比高 | [DeepSeek 平台](https://platform.deepseek.com/) |
| **OpenAI** | GPT-4o 等 | [OpenAI 平台](https://platform.openai.com/api-keys) |
| **Anthropic** | Claude 系列 | [Anthropic 控制台](https://console.anthropic.com/) |
| **Google AI** | Gemini 系列 | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| **Ollama** | 本地模型，无需联网 | 本地部署 Ollama 后无需 Key |
| **Custom** | 任何兼容 OpenAI API 的端点 | 自定义 |

3. 填入 API Key，选择模型（如 `qwen-vl-max`、`gpt-4o` 等）
4. 在右侧面板配置 API 端点（如果需要）

**推荐配置（国内用户）**：
- 提供商：Qwen
- 模型：`qwen-vl-max`（支持图片理解）
- API Key：从阿里云百炼获取

### 4.3 在标注中使用聊天机器人

**场景 1：辅助判断行为**

导入一张图片后，在聊天窗口输入：
```
@image 这张图片中的学生在做什么？请判断是否有以下行为：玩手机、交谈、打瞌睡。请用中文回答。
```

AI 会分析图片并告诉你判断结果，帮助你快速确认标注。

**场景 2：批量分析**

1. 加载一个图片目录
2. 点击"运行所有图片"按钮
3. 输入提示词：
```
@image 请判断这张课堂图片中的学生是否有以下行为之一：玩手机(phone_use)、交谈(talking)、打瞌睡(sleeping)。如果有，请指出是哪种行为。如果没有这三种行为，请回答"无"。
```
4. 设置并发数（建议 50-80% CPU 核心数）
5. AI 会批量处理所有图片并给出判断

**场景 3：生成描述**

```
@image 请用一段话描述这张课堂场景图片中学生的状态和行为。
```

### 4.4 配置文件位置

聊天机器人的配置保存在：
```
~/.xanylabeling_data/chatbot/
├── models.json      # 模型偏好设置
└── providers.json   # API 提供商设置
```

---

## 5. 视觉问答 VQA（Ctrl+2）— 结构化问答标注

### 5.1 这是什么？

VQA 工具是专门为多模态图像问答数据集设计的标注系统。它**不是**用来画框的，而是用来给每张图片附加结构化的问答对（Question-Answer pairs）。

### 5.2 对你的项目有什么用？

虽然你的主要任务是目标检测标注（画框），但 VQA 可以用来：
- 为每张图片生成行为描述（用于数据集文档或模型训练的 caption 数据）
- 结合 AI 自动生成问答标注，节省人工
- 导出 Sharegpt 格式数据，用于微调多模态大模型

### 5.3 使用方法

1. 先在主窗口加载图片目录
2. 按 `Ctrl+2` 打开 VQA 窗口
3. 右侧面板可以添加标注组件：
   - **文本输入框 (QLineEdit)**：用于开放式问答
   - **单选按钮组 (QRadioButton)**：用于单选（如：图片中是否有玩手机行为？是/否）
   - **复选框组 (QCheckBox)**：用于多选（如：图片中存在哪些行为？）
   - **下拉菜单 (QComboBox)**：选项较多时使用

4. **AI 辅助**：点击文本输入框旁的魔法棒图标，输入：
   ```
   @image 请描述这张课堂图片中学生的行为状态。
   ```
   AI 会自动填入回答。

5. 标注完成后点击 `Export Labels` 导出为 JSONL 格式。

### 5.4 变量引用

VQA 支持强大的变量引用系统：
- `@image`：引用当前图片
- `@text`：引用当前文本框已有内容
- `@widget.组件名`：引用其他组件的值
- `@label.shapes`：引用当前图片的所有标注框信息

---

## 6. 图像分类器（Ctrl+3）— 图像级分类

### 6.1 这是什么？

图像分类器用于**整张图片**的分类标注（不是画框），支持 MultiClass（单标签）和 MultiLabel（多标签）两种模式。

### 6.2 对你的项目有什么用？

**场景：快速筛选**
- 如果你的截帧图片中，有些图片根本没有学生、或者不包含任何目标行为，可以用分类器快速标记"有效/无效"
- 或者标记图片的场景类型（如：自习课、讲课、讨论课）

### 6.3 使用方法

1. 在主窗口加载图片目录
2. 按 `Ctrl+3` 打开分类器
3. 添加标签（如 `valid` / `invalid`，或 `phone_use` / `talking` / `sleeping` / `none`）
4. 逐张查看图片，点击对应标签
5. 快捷键 `A`/`D` 切换图片，`Ctrl+A`/`Ctrl+D` 跳转到未标注图片

### 6.4 AI 自动分类

点击魔法棒图标，AI 会根据内置的提示词模板自动分类。你可以自定义提示词：

```
@image
You are an expert image classifier. Your task is to perform multi-class classification.

Task Definition: Analyze the given classroom image and classify the student behavior.

Available Categories: ["phone_use", "talking", "sleeping", "none"]

Instructions:
1. Carefully examine the image and identify student behaviors
2. "phone_use" = student looking at or holding a phone
3. "talking" = students talking to each other
4. "sleeping" = student with head down or eyes closed
5. "none" = none of the above behaviors visible

Return your result in strict JSON format:
{"phone_use": false, "talking": false, "sleeping": false, "none": false}

Set exactly ONE category to 'true' that best matches the image.
```

---

## 7. 视频分类器（Ctrl+5）— 视频行为切分

### 7.1 对你的项目有什么用？

如果你有完整的课堂视频（不只是截帧），可以用视频分类器：
1. 加载课堂视频
2. 在时间轴上标记"玩手机"、"交谈"、"打瞌睡"行为的时间段
3. AI 可以自动分析视频内容并建议切分点
4. 导出为按类别整理的视频片段或抽帧数据

### 7.2 使用方法

1. 按 `Ctrl+5` 打开视频分类器
2. 拖入视频文件或点击打开
3. 在右侧面板添加标签：`phone_use`、`talking`、`sleeping`
4. 在时间轴上右键拖动创建片段
5. 为每个片段分配标签
6. 点击 Export 导出

---

## 8. 大模型联动原理

### 8.1 X-AnyLabeling 如何与大模型联动？

X-AnyLabeling 通过以下方式与大模型集成：

```
┌─────────────────────────────────────────────────────┐
│                  X-AnyLabeling                       │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Chatbot  │  │   VQA    │  │ Image Classifier │  │
│  │ Ctrl+1   │  │ Ctrl+2   │  │     Ctrl+3       │  │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│       │              │                 │            │
│       └──────────────┼─────────────────┘            │
│                      │                              │
│              ┌───────▼────────┐                     │
│              │  API 调用层     │                     │
│              │  (OpenAI 格式)  │                     │
│              └───────┬────────┘                     │
│                      │                              │
└──────────────────────┼──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │ Qwen    │   │ OpenAI  │   │ Ollama  │
   │(阿里云) │   │ (GPT)   │   │(本地)   │
   └─────────┘   └─────────┘   └─────────┘
```

**关键点**：
1. 所有 LLM 功能共用同一套 API 配置（在 Chatbot 中设置一次即可）
2. 支持**纯文本模型**（如 DeepSeek-Chat）和**多模态模型**（如 GPT-4o、Qwen-VL）
3. 多模态模型可以理解图片内容，实现视觉问答
4. 纯文本模型只能处理文字，不能分析图片

### 8.2 @image 命令的工作原理

当你在聊天/VQA 中使用 `@image` 时：
1. X-AnyLabeling 将当前图片编码为 base64
2. 与你的文字提示一起发送给 LLM 的 API
3. LLM（需要支持视觉）分析图片并返回回答
4. 回答显示在界面上或自动填入标注字段

### 8.3 本地模型（Ollama）

如果你不想用云端 API，可以用 Ollama 运行本地模型：

```bash
# 安装 Ollama
# 下载支持视觉的模型
ollama pull llava          # 支持图片理解
ollama pull llama3.1       # 纯文本

# Ollama 默认运行在 http://localhost:11434
```

在 X-AnyLabeling 中选择 Ollama 提供商，端点填 `http://localhost:11434`。

---

## 9. 推荐工作流程

### 9.1 针对你的项目的完整流程

```
步骤 1: 准备
├── 安装 X-AnyLabeling
├── 配置预定义标签 (phone_use, talking, sleeping)
└── 配置 LLM API（推荐 Qwen-VL 或 DeepSeek）

步骤 2: 快速筛选（可选）
├── Ctrl+3 打开图像分类器
├── 用 AI 批量分类：有效/无效
└── 过滤掉无效图片

步骤 3: AI 辅助标注
├── Ctrl+A 打开自动标注
├── 选择 YOLOv8s 或 YOLO11s 模型
├── 模型自动检测 person 并画框
└── 你修改标签名为 phone_use/talking/sleeping

步骤 4: 人工精修
├── 逐张检查 AI 标注结果
├── 修正框的位置和大小
├── 补画漏检的目标
└── 删除误检的框

步骤 5: LLM 辅助校验（可选）
├── Ctrl+1 打开聊天机器人
├── @image 让 AI 判断行为类型
├── 对比 AI 判断和你的标注
└── 修正不一致的地方

步骤 6: 导出
├── 菜单栏 -> 导出 -> 导出 YOLO 标签
├── 上传 classes.txt (phone_use/talking/sleeping)
└── 生成 labels/ 目录下的 *.txt 文件
```

### 9.2 效率技巧

1. **数字快捷键**：配置 1=phone_use, 2=talking, 3=sleeping，一键画框
2. **自动使用上一个标签**：`Ctrl+Y` 开启，连续标注同一类时省去输入
3. **批量自动标注**：`Ctrl+B` 可以对整个目录批量运行模型
4. **悬浮高亮**：`Settings > Auto Highlight Shape` 开启，鼠标悬停即高亮对象
5. **保留先前缩放**：`视图` -> `保留先前的缩放比例`，放大后切换图片保持缩放

---

## 10. 导出 YOLO 标签

### 10.1 准备 classes.txt

```
phone_use
talking
sleeping
```

### 10.2 导出步骤

1. 菜单栏 -> `导出` -> `导出 YOLO 标签`
2. 上传 `classes.txt`
3. 勾选需要的选项
4. 点击确定
5. 标签文件保存在图片目录同级的 `labels/` 文件夹中

### 10.3 导出格式

每个图片对应一个同名的 `.txt` 文件，格式为：
```
<class_id> <x_center> <y_center> <width> <height>
```

例如：
```
0 0.45 0.62 0.12 0.25
1 0.78 0.34 0.08 0.15
```

其中：0=phone_use, 1=talking, 2=sleeping

---

## 11. 快捷键速查表

| 快捷键 | 功能 |
|--------|------|
| `R` | 画矩形框 |
| `Ctrl+E` | 切换编辑模式 |
| `Ctrl+J` | 切换绘制/编辑模式 |
| `A` / `D` | 上一张/下一张图片 |
| `Delete` | 删除选中对象 |
| `Ctrl+Z` | 撤销 |
| `Ctrl+C` / `Ctrl+V` | 复制/粘贴 |
| `Ctrl+Y` | 自动使用上一个标签 |
| `Ctrl+A` | 启用自动标注 |
| `Ctrl+B` | 批量标注 |
| `Ctrl+S` | 保存 |
| `Ctrl+1` | 聊天机器人 |
| `Ctrl+2` | VQA 窗口 |
| `Ctrl+3` | 图像分类器 |
| `Ctrl+5` | 视频分类器 |
| `Alt+D` | 数字快捷键管理器 |
| `Alt+L` | 标签管理器 |
| `Ctrl+0` | Settings |
| `Ctrl+L` | 显示/隐藏标签名 |
| `Ctrl+T` | 显示/隐藏描述 |
