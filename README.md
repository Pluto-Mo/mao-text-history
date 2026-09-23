# 毛泽东文本演变研究库

## 全《毛选》逐篇研究入口

《正处》只是样例。全书研究先读 [总览与综合结论](research/maoxuan/README.md)、[逐篇总表](research/maoxuan/all-works.md) 和 [映射规则](research/maoxuan/RULES.md)。229篇正文与1篇附录均有首轮研究卡；全库候选、已复核来源陈述及缺稿分别登记。卡片齐全不等于全部历史稿本完成校勘；当前研究进度见 `research/maoxuan/coverage.json`，资料入库进度仍见 `reports/completion.json`。


## 全文库：本轮实际交付

[最终验收与逐卷入口](reports/completion.md) · [全文和原文件](archive/README.md) · [《正处》全文查阅包](exports/zhengchu-fulltext-guide.md)。

源文件、网页全文、整卷PDF及页面定位已实际保存；查看最新验收报告，不再把早期目录数量当作全文数量。复制依据[仓库操作者的授权声明](authorization/user-declared-fulltext.json)。


把作品、版本、历史时间线与来源证据放进同一个可回溯的研究库，供 Agent 阅读、检索和讨论。**Git记录的是研究资料变更，不是伪造历史人物的commit。**

补全工作入口：[缺失资料与补全清单](docs/missing-materials.md)。按四类资料、版次卷册、专题证据和全库校验列出尚缺内容、来源依据及完成条件；后续 Agent 接手时先核对该清单和最新覆盖报告。

## 范围与实际状态

四类资料均登记到具体版次与卷册：**《毛泽东选集》、旧版/新版《建国以来毛泽东文稿》、旧版/新版《毛泽东年谱》、中文马克思主义文库的毛泽东主目录及关联分库**。另以《毛泽东文集》第七卷作为《正处》的辅助见证本。

**全文复制状态以最新 reports/completion.json 为准；全部中间稿的历史校勘不因文件入库而自动完成。**本公开仓库保存原文件、全文、页面索引、来源书目、采集收据、候选映射和原创研究卡。可访问的网页不等于原书全文取得或获准转载。

实际数量见 [覆盖报告](reports/coverage.json)，解析核对见 [校勘检查](reports/parser-audit.json)。不存在报告表示该阶段尚未完成。`parser_version: 2` 表示已用中文编码和多栏目录校正器处理题名与卷次；首轮数据不能直接用作精确引文。

## 直接给 Agent 使用

先读 [AGENTS.md](AGENTS.md) 和 [研究 Skill](skills/text-history/SKILL.md)，再执行：

```bash
python -m pip install -r requirements.txt
python corpus.py validate
python corpus.py context 正处
python corpus.py search 正确处理
python corpus.py trace E003
```

示例：“解释《正处》从讲话到发表的变化。区分原文直接观察、后出题注、论文转引和缺失的中间稿。每项判断都给来源和定位，不补造改稿。先读实际覆盖报告，不能假设四套全文已经齐备。”

## 数据在哪里

| 文件 | 内容 |
|---|---|
| docs/missing-materials.md | 缺失资料总清单、对应来源、补齐标准和执行顺序 |
| config/sources.json | 精确来源、网址、性质和限制 |
| config/editions.json | 书系版本及预期卷数，旧新版分开 |
| catalog/volumes.jsonl | 每个预期卷是否真正取得 |
| catalog/entries.jsonl | 目录：原题名、卷次线索、URL、源页定位 |
| catalog/fetches.jsonl | 取得时间、状态、字节哈希、长度和解析质量 |
| catalog/relations.jsonl | 跨目录同题候选；不是确认的改稿关系 |
| data/evidence.json | 研究断言、来源及证据边界 |
| data/research-gaps.json | 缺稿、缺页、缺授权等问题 |
| cases/zhengchu-1957.json | 《正处》端点、见证本和查书路线 |
| reports/manifest.json | 已生成公共数据文件的SHA256 |

## 采集与补全

```bash
# 用校正器刷新目录，保留首轮原始字节收据；不把旧版文字提取认证为已校验。
python catalogue_v2.py

# 需要重新核查所有HTML见证本时，用新版解析器运行完整采集。
python catalogue_v2.py --full
```

`corpus.py collect` 是首轮采集器，日常采集应使用以上新版入口。旧收据若标记 `legacy_decoder_not_revalidated`，只可用于当时访问与原始字节哈希的回查，不作为已校验的中文正文。首轮缓存没有保留；本轮长期保存的原文件与正文位于 archive/。

合法取得的原文件可通过 corpus.py ingest 导入 local/。先把原书取得来源登记为独立 source_id，再给出版版次、权限说明和已检查的提取文本。不能用出版公告的source_id冒充原书取得来源。

工作流没有定时监控：首轮采集完成后触发目录校正；同时保留手动入口。它尊重robots、限制并发、记录失败，只提交可公开的元数据。旧工作流不发布其临时缓存；本轮授权全文采集在 archive/objects 保存可还原的原始字节。

## 来源与校勘

不同网站是不同文本见证本，一个字的差异可能来自转录、排印、节录或不同底本。自动同题匹配只能提供候选，不能认定作者在哪一次改了什么；日期范围相交也只是查书路线。

方法和验收见 [数据模型](docs/data-model.md)，发布边界见 [资料权利](docs/rights.md)，首个专题见 [《正处》导读](cases/README.md)。

## 已保存的公文正文

见 [全文正文目录及验收](reports/fulltext-coverage.md) 和 [全文文件夹](fulltext/README.md)。这里保存的是实际UTF-8正文快照，不只是网址。来源明确为节录的，仍标为节录。

`python fulltexts.py search 金门` 检索已入库正文；`python fulltexts.py read mia-1958-1006` 阅读；`python fulltexts.py compare mia-1958-1006 ws-1958-1006` 对比两种已成功保存的网页见证本。

本轮逐篇收录依据见 `rights/fulltext-allowlist.json`。原始公文正文与现代编辑题注分开，未授权的整套出版物仍不转载。历史目录报告 reports/coverage.json 不统计后来新增的全文层，两个报告不能混用。
