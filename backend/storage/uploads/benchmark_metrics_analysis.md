# Part 1: Process the Dataset, Run the Benchmark Model and Analyze the Result

> **项目**：CS340 Final Project — Bias Mitigation
> **数据集**：ACSEmployment (2018 ACS PUMS, CA+TX)
> **敏感属性**：SEX (Male=1.0 / Female=2.0)
> **预测目标**：EMPLOYED (1=就业, 0=未就业)

---

## 1.1 Dataset Processing

### 数据来源

ACSEmployment 数据集来源于 2018 年美国社区调查（ACS）Public Use Microdata Sample（PUMS），由 [Ding et al. (NeurIPS 2021)](https://proceedings.neurips.cc/paper_files/paper/2021/file/32e54441e6382a7fbacbbbaf3c450059-Paper.pdf) 作为 Folktables benchmark 的一部分构建。本项目仅选取 **California (CA)** 和 **Texas (TX)** 两州数据。

### 数据规模与划分

| 项目 | 数值 |
|------|------|
| 总样本数 | 646,917 |
| 训练集 (80%) | 517,534 |
| 测试集 (20%) | 129,383 |
| 特征数 | 16 维（不含目标变量） |
| 随机种子 | RANDOM_STATE=200 |

### 测试集分布

| 分组 | 样本数 | 占比 | 就业人数 | 就业率 |
|------|--------|------|----------|--------|
| Overall | 129,383 | 100% | 58,691 | 45.4% |
| Male (SEX=1.0) | 63,564 | 49.1% | 31,183 | 49.1% |
| Female (SEX=2.0) | 65,819 | 50.9% | 27,508 | 41.8% |

> **数据层面的偏差信号**：女性真实就业率（41.8%）比男性（49.1%）低 7.3 个百分点。如果模型学会了这一数据分布，可能在预测中对女性产生系统性不利。

---

## 1.2 Benchmark Model

### 模型架构

采用 Keras Functional API 构建的全连接神经网络：

```
Input (16 features) → Normalization → Dense(64, ReLU) → Dense(32, ReLU) → Dense(1, Sigmoid)
```

### 训练配置

| 参数 | 值 |
|------|-----|
| Optimizer | Adam |
| Loss | BinaryCrossentropy |
| Batch Size | 100 |
| Epochs | 10 |

---

## 1.3 Base Model — 13 Fairness Indicators Metrics

使用 TensorFlow Fairness Indicators 对基准模型进行评估，按 SEX 属性分片（阈值 = 0.5）。

### 1.3.1 整体性能

| 指标 | 值 |
|------|-----|
| Test Loss | 0.3847 |
| Test Accuracy | 82.00% |
| Test AUC | 0.9016 |

### 1.3.2 13 项指标总览

| #    | 指标                 | Overall | Male   | Female | 组间差异 (\|M−F\|) | 偏差方向     |
| ---- | -------------------- | ------- | ------ | ------ | ------------------ | ------------ |
| 1    | example_count        | 129,383 | 63,564 | 65,819 | —                  | —            |
| 2    | binary_accuracy      | 0.821   | 0.854  | 0.789  | 0.065              | 女性更差     |
| 3    | AUC                  | 0.902   | 0.925  | 0.872  | 0.053              | 女性更差     |
| 4    | precision            | 0.778   | 0.827  | 0.724  | **0.103**          | 女性更差     |
| 5    | recall / TPR         | 0.847   | 0.887  | 0.802  | **0.085**          | 女性更差     |
| 6    | true_negative_rate   | 0.799   | 0.822  | 0.780  | 0.042              | 女性更差     |
| 7    | false_positive_rate  | 0.201   | 0.178  | 0.220  | 0.042              | 女性更差     |
| 8    | false_negative_rate  | 0.153   | 0.113  | 0.198  | **0.085**          | **女性更差** |
| 9    | false_discovery_rate | 0.222   | 0.173  | 0.276  | **0.103**          | 女性更差     |
| 10   | false_omission_rate  | 0.137   | 0.117  | 0.154  | 0.037              | 女性更差     |
| 11   | positive_rate        | 0.494   | 0.526  | 0.463  | **0.063**          | 女性更差     |
| 12   | negative_rate        | 0.506   | 0.474  | 0.537  | 0.063              | 女性更差     |
| 13   | true_positive_rate   | 0.847   | 0.887  | 0.802  | **0.085**          | 女性更差     |

> 注：recall 与 true_positive_rate 为同一指标；差异 ≥ 0.05 的项已加粗。

### 1.3.3 逐指标解读

#### 指标 1：example_count（样本数）

测试集中女性 65,819（50.9%），男性 63,564（49.1%），分布基本均衡。样本量不存在偏斜，排除了样本不均衡导致的评估偏差。

#### 指标 2–3：binary_accuracy 和 AUC（整体预测能力）

- **Accuracy**: 男性 85.4% vs 女性 78.9%（差距 6.5pp）。模型对男性预测正确率显著更高。
- **AUC**: 男性 0.925 vs 女性 0.872（差距 0.053）。模型对男性正负例的区分能力更强。

#### 指标 4：precision（精确率）★ 最大差异指标

$$Precision = \frac{TP}{TP + FP}$$

| Overall | Male | Female | 差异 |
|---------|------|--------|------|
| 0.778 | 0.827 | 0.724 | **0.103** |

**含义**：当模型预测一个人"就业"时，该预测正确的概率。

女性精确率仅 72.4%，即模型对女性的"就业"预测中 **27.6% 是错误的（假阳性）**，而男性为 17.3%。在所有 13 项指标中，精确率是组间差异最大的一项（10.3pp）。

#### 指标 5 & 13：recall / true_positive_rate（召回率 / 真正率）

$$Recall = TPR = \frac{TP}{TP + FN}$$

| Overall | Male | Female | 差异 |
|---------|------|--------|------|
| 0.847 | 0.887 | 0.802 | **0.085** |

**含义**：实际就业的人中，有多少被模型正确识别。

女性召回率仅 80.2%，即实际就业的女性中 **19.8% 被模型漏判为"未就业"**，而男性漏判率仅 11.3%。这直接关系到 **Equality of Opportunity** 原则。

#### 指标 6–7：true_negative_rate 和 false_positive_rate

$$TNR = \frac{TN}{TN + FP}, \quad FPR = \frac{FP}{FP + TN}$$

| 指标 | Male | Female | 差异 |
|------|------|--------|------|
| TNR | 0.822 | 0.780 | 0.042 |
| FPR | 0.178 | 0.220 | 0.042 |

女性 FPR（22.0%）高于男性（17.8%），模型更容易将未就业女性误判为就业。FPR 与 FNR 的双重偏高意味着模型在两个错误方向上对女性均不利。

#### 指标 8：false_negative_rate（假负率 / 漏报率）★ 最关键的公平性指标

$$FNR = \frac{FN}{FN + TP}$$

| Overall | Male | Female | 差异 | 相对比 |
|---------|------|--------|------|--------|
| 0.153 | **0.113** | **0.198** | **0.085** | **Female 是 Male 的 1.75 倍** |

女性就业者中 **19.8% 被漏报**，男性仅 11.3%，差距 8.5pp，相对高出 75%。这直接违反 **Equality of Opportunity** 原则。

#### 指标 9：false_discovery_rate（错误发现率）

$$FDR = \frac{FP}{FP + TP}$$

| Overall | Male | Female | 差异 |
|---------|------|--------|------|
| 0.222 | 0.173 | 0.276 | **0.103** |

女性 FDR 高达 27.6%，近三成的"就业"预测是错误的。与 Precision 互补（FDR = 1 − Precision）。

#### 指标 10：false_omission_rate（错误遗漏率）

$$FOR = \frac{FN}{FN + TN}$$

| Overall | Male | Female | 差异 |
|---------|------|--------|------|
| 0.137 | 0.117 | 0.154 | 0.037 |

当模型判定"未就业"时，对女性的出错概率略高。

#### 指标 11–12：positive_rate 和 negative_rate（正/负预测率 / Selection Rate）

| 指标 | Male | Female | 差异 |
|------|------|--------|------|
| Positive Rate | 0.526 | 0.463 | **0.063** |
| Negative Rate | 0.474 | 0.537 | 0.063 |

模型预测 52.6% 的男性为"就业"，但仅预测 46.3% 的女性为"就业"——差距 6.3pp。违反 **Demographic Parity**。

---

## 1.4 MinDiff Model — 13 Fairness Indicators Metrics

MinDiff（Minimizing Difference）通过 MMD（Maximum Mean Discrepancy）损失在训练时惩罚敏感组（Female）与非敏感组（Male）之间的分布差异，目标是在训练过程中缩小不同群体间的错误率差距。

### 1.4.1 整体性能

| 指标 | 值 |
|------|-----|
| Test Loss | 0.3963 |
| Test Accuracy | 81.74% |
| Test AUC | 0.8943 |

### 1.4.2 13 项指标总览

| # | 指标 | Overall | Male | Female | 组间差异 (|M−F|) | 偏差方向 |
|---|------|---------|------|--------|-------------------|---------|
| 1 | **example_count** | 129,383 | 63,564 | 65,819 | — | — |
| 2 | **binary_accuracy** | 0.819 | 0.852 | 0.787 | 0.065 | 女性更差 |
| 3 | **AUC** | 0.895 | 0.922 | 0.871 | 0.051 | 女性更差 |
| 4 | **precision** | 0.761 | 0.824 | 0.698 | **0.126** | 女性更差 |
| 5 | **recall / TPR** | 0.877 | 0.887 | 0.865 | **0.022** | 女性更差 |
| 6 | **true_negative_rate** | 0.771 | 0.818 | 0.731 | 0.087 | 女性更差 |
| 7 | **false_positive_rate** | 0.229 | 0.182 | 0.269 | 0.087 | 女性更差 |
| 8 | **false_negative_rate** | 0.123 | 0.113 | 0.135 | **0.022** | 女性更差 |
| 9 | **false_discovery_rate** | 0.239 | 0.176 | 0.302 | **0.126** | 女性更差 |
| 10 | **false_omission_rate** | 0.117 | 0.118 | 0.117 | **0.001** | 几乎均等 |
| 11 | **positive_rate** | 0.523 | 0.528 | 0.518 | **0.010** | 女性更差 |
| 12 | **negative_rate** | 0.477 | 0.472 | 0.482 | 0.010 | 女性更差 |
| 13 | **true_positive_rate** | 0.877 | 0.887 | 0.865 | **0.022** | 女性更差 |

### 1.4.3 关键变化解读

#### 改善显著的指标

**false_negative_rate（FNR）** — MinDiff 的核心优化目标：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.198 | **0.135** | **−6.3pp (−32%)** |
| Male | 0.113 | 0.113 | 不变 |
| FNR Gap | 0.085 | **0.022** | **−74%** |

女性漏报率从 19.8% 骤降至 13.5%，与男性的差距从 8.5pp 压缩至仅 2.2pp。

**false_omission_rate（FOR）**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.154 | **0.117** | −3.7pp |
| F-M Gap | 0.037 | **0.001** | **−97%** |

当模型判定"未就业"时，男女出错概率几乎完全一致。

**positive_rate（Selection Rate）**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.463 | **0.518** | +5.5pp |
| F-M Gap | 0.063 | **0.010** | **−84%** |

男女被预测为"就业"的比例接近均等，Demographic Parity 大幅改善。

**recall / true_positive_rate**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.802 | **0.865** | **+6.3pp** |
| F-M Gap | 0.085 | **0.022** | **−74%** |

#### 恶化的指标

**precision**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.724 | **0.698** | −2.6pp |
| F-M Gap | 0.103 | **0.126** | **+22%（扩大）** |

女性精确率进一步下降，30.2% 的"就业"预测是错误的。

**false_positive_rate（FPR）**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.220 | **0.269** | +4.9pp |
| F-M Gap | 0.042 | **0.087** | **+107%（翻倍）** |

更多未就业女性被误判为就业。

**true_negative_rate（TNR）**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.780 | **0.731** | −4.9pp |

识别未就业女性的能力下降。

**false_discovery_rate（FDR）**：

| 组别 | Base | MinDiff | 变化 |
|------|------|---------|------|
| Female | 0.276 | **0.302** | +2.6pp |
| F-M Gap | 0.103 | **0.126** | **+22%（扩大）** |

---

## 1.5 Base Model vs MinDiff Model — Full Comparison

### 1.5.1 整体性能对比

| 指标 | Base | MinDiff | Δ |
|------|------|---------|---|
| Accuracy | 0.8200 | 0.8174 | −0.0026 |
| AUC | 0.9016 | 0.8943 | −0.0073 |
| Loss | 0.3847 | 0.3963 | +0.0116 |

整体准确率和 AUC 仅微小下降（< 1%），MinDiff 以极小的性能代价换来了公平性提升。

### 1.5.2 13 项指标逐一对比

| # | 指标 | Base F-M Gap | MinDiff F-M Gap | 公平性变化 | 评价 |
|---|------|-------------|----------------|-----------|------|
| 2 | binary_accuracy | 0.065 | 0.065 | → | 持平 |
| 3 | AUC | 0.053 | 0.051 | ↓ 0.002 | 微改善 |
| 4 | precision | 0.103 | 0.126 | **↑ 0.023** | **恶化** |
| 5 | recall / TPR | 0.085 | 0.022 | **↓ 0.063** | **大幅改善 74%** |
| 6 | true_negative_rate | 0.042 | 0.087 | **↑ 0.045** | **恶化** |
| 7 | false_positive_rate | 0.042 | 0.087 | **↑ 0.045** | **恶化** |
| 8 | false_negative_rate | 0.085 | 0.022 | **↓ 0.063** | **大幅改善 74%** |
| 9 | false_discovery_rate | 0.103 | 0.126 | **↑ 0.023** | **恶化** |
| 10 | false_omission_rate | 0.037 | 0.001 | **↓ 0.036** | **大幅改善 97%** |
| 11 | positive_rate | 0.063 | 0.010 | **↓ 0.053** | **大幅改善 84%** |
| 12 | negative_rate | 0.063 | 0.010 | ↓ 0.053 | 大幅改善 |
| 13 | true_positive_rate | 0.085 | 0.022 | **↓ 0.063** | **大幅改善 74%** |

### 1.5.3 公平性维度对比

| 公平性概念 | 关键指标 | Base Gap | MinDiff Gap | 改善幅度 | 趋势 |
|-----------|---------|---------|------------|---------|------|
| **Equality of Opportunity** | FNR | 8.5pp | 2.2pp | ↓ 74.1% | ✅ 大幅改善 |
| **Demographic Parity** | Positive Rate | 6.3pp | 1.0pp | ↓ 84.1% | ✅ 大幅改善 |
| **Equalized Odds (FPR侧)** | FPR | 4.2pp | 8.7pp | ↑ 107% | ❌ 恶化 |
| **Predictive Parity** | Precision | 10.3pp | 12.6pp | ↑ 22% | ❌ 恶化 |
| **Predictive Parity (FOR侧)** | FOR | 3.7pp | 0.1pp | ↓ 97.3% | ✅ 几乎完美 |

---

## 1.6 Bias Identification — Three Fairness Violations in Base Model

基于以上指标分析，基准模型在 SEX 维度上存在三类明确的公平性违反：

| # | 公平性概念 | 关键指标 | Male | Female | 差距 | 严重程度 |
|---|-----------|---------|------|--------|------|---------|
| 1 | **Equality of Opportunity** | FNR | 11.3% | 19.8% | +8.5pp | **高** |
| 2 | **Demographic Parity** | Positive Rate | 52.6% | 46.3% | −6.3pp | 中 |
| 3 | **Predictive Parity** | Precision | 82.7% | 72.4% | −10.3pp | **高** |

### Violation 1: Equality of Opportunity（机会均等违反）

- **表现**：Female FNR (19.8%) = Male FNR (11.3%) × 1.75
- **含义**：已就业女性被错误分类为"未就业"的概率是男性的 1.75 倍
- **MinDiff 修复效果**：FNR 差距从 8.5pp 降至 2.2pp（↓74%），Female FNR 从 19.8% 降至 13.5%

### Violation 2: Demographic Parity（人口均等违反）

- **表现**：Male Positive Rate (52.6%) vs Female (46.3%)，差距 6.3pp
- **MinDiff 修复效果**：Positive Rate 差距从 6.3pp 降至 1.0pp（↓84%），几乎实现均等

### Violation 3: Predictive Parity（预测均等违反）

- **表现**：Female Precision (72.4%) vs Male (82.7%)，差距 10.3pp
- **MinDiff 修复效果**：Precision 差距反而扩大至 12.6pp，这是 MinDiff 方法的主要副作用

---

## 1.7 Root Cause Analysis

### 1.7.1 数据层面的偏差

数据集本身存在性别就业率差异（Male 49.1% vs Female 41.8%）。模型在训练时学到了这一先验分布，将其作为预测依据。

### 1.7.2 代理特征（Proxy Features）

SEX 属性与其他特征高度相关（如职业、教育、婚姻状况）。即使显式删除 SEX 列，性别信息仍可通过其他特征间接泄露。仅靠删除敏感属性无法消除偏差。

### 1.7.3 目标函数未约束公平性

BinaryCrossentropy 损失函数仅优化整体预测误差，不关心误差在子群体间的分布。模型可以在 Overall Accuracy 高达 82% 的同时，对 Female 子群体产生 19.8% 的假负率。

### 1.7.4 MinDiff 的 Tradeoff 本质

MinDiff 通过在训练时加入 MMD 损失来惩罚组间分布差异，成功缩小了 FNR 差距（Equality of Opportunity）和 Selection Rate 差距（Demographic Parity），但付出了 **FPR 差距和 Precision 差距扩大**的代价。这揭示了公平性优化的根本 tradeoff：不存在在所有公平性维度上都最优的模型，优化某个维度往往在其他维度上产生代价。

---

## 1.8 Summary of Observations

1. **Base Model 存在系统性偏差**：在所有 13 项评估指标上，Female 组均不如 Male 组。FNR 差距 8.5pp 和 Precision 差距 10.3pp 是最突出的两个问题。

2. **MinDiff 在核心公平性维度上显著有效**：FNR 差距缩小 74%，Selection Rate 差距缩小 84%，FOR 差距缩小 97%。MinDiff 成功实现了其设计目标——最小化组间假负率差异。

3. **但 MinDiff 引入了新的公平性代价**：Female FPR 从 22.0% 升至 26.9%（差距翻倍），Precision 从 72.4% 降至 69.8%。这表明 MinDiff 通过更"慷慨"地预测女性就业来降低漏报率，但代价是更多误报。

4. **Accuracy-Fairness Tradeoff**：整体准确率损失仅 0.26%（82.00% → 81.74%），但公平性改善显著。这说明在一定程度上，公平性与准确性并非完全互斥，但需要针对具体应用场景权衡各公平性维度的优先级。

---

---

# Part 2: Mitigate Bias from a Variety of Methods

> **自定义方法**：Sample Re-weighting + Enhanced Network Architecture + Weighted Training
> **核心理念**：不修改损失函数结构（区别于 MinDiff 的 MMD 惩罚），而是通过数据层和模型架构层的干预来缓解偏差