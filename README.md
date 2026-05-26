# GaussDB 数据库季度巡检报告自动生成工具

## 项目目标

本项目用于自动生成 GaussDB 数据库季度巡检报告。工具从 GaussDB 巡检包中提取基础信息、节点信息、容量指标、性能指标、配置检查、告警风险和整改建议，生成结构化 YAML，并最终按照既有客户交付版 Word 样例的格式输出正式健康诊断报告。

样例 Word 报告仅用于参考格式、章节结构、标题层级、表格样式和措辞风格。样例巡检包仅用于解析器开发和测试。项目禁止将样例中的客户名、IP、数据库名、巡检日期、检查结论或指标值写死到代码中。

## 输入文件

计划支持的输入包括：

- GaussDB 巡检压缩包，例如 `.rar`、`.tar.gz`、`.zip`
- 巡检文本文件，例如 `.txt`
- 巡检 HTML 文件，例如 `.html`
- 数据库日志文件，例如 `.log`
- 后续可扩展的 CSV、Excel、JSON 或其他导出格式

所有客户信息、节点 IP、数据库名、巡检日期、检查结论和指标数据都必须来自输入文件。无法解析的字段统一输出为“未采集”或“未提供”。

## 输出文件

计划输出包括：

- 结构化巡检结果 YAML，例如 `output/inspection.yaml`
- 风险分析结果 YAML，例如 `output/risk_summary.yaml`
- Word 巡检报告，例如 `output/GaussDB数据库健康诊断报告.docx`
- 解析日志和中间文件，例如 `output/intermediate/`
- 长明细或完整原始内容附录路径，例如 `output/appendix/`

报告正文面向客户交付，措辞应正式、简洁、专业。长明细默认只展示 Top N，完整内容保留在中间文件或附录路径中。

## 核心流程

```text
巡检包 -> 解压 -> 解析 -> 风险分析 -> YAML -> Word 报告
```

## 安装依赖

建议在虚拟环境中安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 本地解压依赖

`.tar.gz`、`.zip` 等格式优先使用 Python 标准库解压。`.rar` 文件需要本地环境提供兼容的 RAR 解压后端，建议安装以下任意一种工具并加入 `PATH`：

- 7-Zip，提供 `7z`
- UnRAR，提供 `unrar`
- bsdtar，提供 `bsdtar`

如果缺少 RAR 解压依赖，程序会给出明确错误提示，不会静默跳过巡检包。

## 运行命令示例

当前流程会检查输入文件和模板文件是否存在，创建 `output/` 与 `workdir/`，将巡检包递归解压到 `workdir/extracted/`，生成解压文件清单，解析所有 `inspection_rec.txt` 的巡检章节，并输出一个包含基础章节结构的 Word 报告。当前阶段只做通用章节分段，不做复杂风险判断，也不会硬编码样例巡检包中的真实客户数据。

```powershell
python -m src.cli `
  --input .\samples\收益所有人.rar `
  --template .\templates\GaussDB数据库健康诊断报告.docx `
  --output .\output\收益所有人_GaussDB数据库健康诊断报告.docx
```

运行后计划生成：

```text
output/extracted_manifest.yaml
output/inspection_data.generated.yaml
output/收益所有人_GaussDB数据库健康诊断报告.docx
workdir/extracted/
```

`output/inspection_data.generated.yaml` 会保留每个 `inspection_rec.txt` 的来源路径、章节名称、章节原始内容和内容预览。无法解析为具体业务字段的内容保持在原始章节中，结构化字段统一使用“未采集”或空列表。

当前已从系统资源类章节中提取节点级结构化数据，包括操作系统摘要、CPU 型号、CPU 核数、内存使用、磁盘使用和 CPU 近一天使用情况。节点按 IP 或 hostname 聚合，未能解析的字段使用“未采集”或默认空值；风险判断仍留给后续 `analyzer.py` 阶段。

## 测试

```powershell
pytest
```

## 后续开发阶段

1. 建立 Python 项目骨架、依赖管理和命令行入口。已完成第一版。
2. 实现巡检包自动解压，支持 `.rar`、`.tar.gz`、`.zip` 等格式。已完成第一版。
3. 实现文件清单扫描，识别文本、HTML、日志和结构化数据文件。已完成第一版。
4. 解析 `inspection_rec.txt` 巡检章节并生成结构化 YAML。已完成第一版。
5. 解析系统资源类信息并写入 `nodes` 与 `cluster.resource_summary`。已完成第一版。
6. 定义统一 YAML schema，承载客户、实例、节点、指标、风险和附录路径。
7. 开发通用解析器，避免依赖单一客户文件名、单一 IP 或单一节点数量。
8. 实现风险分析规则，将解析结果转换为风险等级、问题说明和整改建议。
9. 基于 Word 样例格式生成正式 GaussDB 数据库健康诊断报告。
10. 扩展测试体系，覆盖解析成功、字段缺失、多节点、多格式和异常输入场景。
11. 持续提升解析覆盖率，并保持工具在不完整输入下仍可运行。

## 开发约束

- 禁止硬编码样例报告或样例巡检包中的具体数据。
- 解析失败不得编造内容，只能输出“未采集”或“未提供”。
- 每次功能修改后必须同步更新 README 和测试。
- 优先保证工具可运行，再逐步提升解析深度和报告质量。
