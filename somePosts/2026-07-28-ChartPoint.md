# ChartPoint: Guiding MLLMs with Grounding Reflection for Chart Reasoning[^1]

_用“接地反思”引导多模态大模型进行图表推理,解决数值幻觉问题_

## 摘要：

### 背景：

MLLMs在图表理解中依赖OCR，但易受文本注释稀疏影响，导致数值幻觉。

### 现有方法局限：

现有方法侧重指令扩展，未能解决视觉感知的根本挑战。

### 关键观察：

MLLMS对图表元素和比例关系的“接地”能力薄弱，无法将推理步骤与视觉区域对应。

### 提出方法（PointCoT）：

将反思交互融入CoT，通过生成边界框（BBox）和重渲染图表，建立文本推理与视觉区域的联系。

### 贡献：

- 提出PointCoT，利用BBox验证推理与图表内容的一致性。
- 构建ChartPoint-SFT_62k数据集（含19.2k高质量样本，含CoT、BBox、重渲染）。
- 开发ChartPoint2/2.5模型，在多个基准上超越SOTA。

> 来解释下这的文本注释稀疏是什么意思。一张柱状图中直接标注的文字通常只有柱子下的label，但图中真正重要的信息（每个柱子的高度、柱子之间的比例关系、趋势走向）没有任何文字标注，这就是“文本注释稀疏”——图上能OCR识别的文字太少了，大部分信息藏在视觉布局里，没有对应的文本描述。

## 所以现在的核心问题就是：如何在文本注释稀疏的情况下，实现准确的图表理解？





[^1]: [ChartPoint: Guiding MLLMs with Grounding Reflection for Chart Reasoning](https://arxiv.org/html/2512.00305v1)