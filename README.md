# 毛泽东文本演变研究库

把作品、版本、历史时间线与来源证据放进同一个可回溯的研究库，供 Agent 阅读、检索和讨论。**Git记录的是研究资料变更，不是伪造历史人物的commit。**

## 实际范围与状态

四套资料全部进入卷册级收集计划：**《毛泽东选集》、旧版/新版《建国以来毛泽东文稿》、旧版/新版《毛泽东年谱》、中文马克思主义文库的毛泽东主目录及关联分库**。另以《毛泽东文集》第七卷作为《正处》的辅助见证本。

**尚未取得四套原书的全部全文，也未重建全部中间稿。**本公开仓库目前发布来源书目、卷册清单、目录索引、采集收据、候选映射和原创研究卡。公开网页的可访问性不等于书籍全文取得或转载授权。

最新实际数字见 [采集覆盖报告](reports/coverage.json)。不存在报告时，代表尚未完成一次采集运行，不代表零缺失。Actions绿色只代表流程成功；失败来源、缺卷与候选关系仍在报告中明确列出。

## 直接给 Agent 使用

先读 [AGENTS.md](AGENTS.md)，再执行：

```bash
python -m pip install -r requirements.txt
python corpus.py validate
python corpus.py context 正处
python corpus.py search 正确处理
python corpus.py trace E003
```

建议提问：“结合 E001–E004，解释《正处》从讲话到发表的变化。区分原文直接观察、后出题注、论文转引和缺失的中间稿。每项判断都给来源和定位，不补造改稿。”

## 数据在哪里

| 文件 | 内容 |
|---|---|
| config/sources.json | 精确来源、网址、性质、限制 |
| config/editions.json | 书系版本及预期卷数，旧新版分开 |
| catalog/volumes.jsonl | 每个预期卷是否真正取得 |
| catalog/entries.jsonl | 全局目录：原题名、卷次线索、URL、源页定位 |
| catalog/fetches.jsonl | 网络取得时间、状态、字节哈希、长度 |
| catalog/relations.jsonl | 跨目录同题候选；不是确认的改稿关系 |
| data/evidence.json | 可讨论的研究断言及证据边界 |
| data/research-gaps.json | 缺稿、缺页、缺授权等问题 |
| cases/zhengchu-1957.json | 《正处》端点、见证本与查书路线 |
| reports/manifest.json | 已生成公共数据文件的SHA256 |

## 采集与补全

```bash
# 读取目录并检查可访问HTML；不公开复制原书。
python corpus.py collect --limit 1500 --workers 3
```

合法取得的原文件可用 corpus.py ingest 导入 local/。先把原书取得来源登记为独立 source_id，再给出版版次、权限说明和已检查的提取文本。不要用出版公告的source_id冒充实际原书的来源。

采集工作流仅在本仓库相关代码/配置变更或手动启动时运行，没有定期监控。它尊重robots、限制并发、记录失败，只提交允许公开的元数据。原始HTML缓存不随Git或Actions附件发布。

## 来源与校勘

官方电子库提供目录/阅读器入口；MIA提供不同底本的网页见证。一个字的差异可能来自转录、排印或不同底本，不能直接解释为作者的历史修改。不同网站的同题匹配仅为候选，日期范围相交只是查书路线。

方法和验收见 [数据模型](docs/data-model.md)，发布边界见 [资料权利](docs/rights.md)，首个专题见 [《正处》导读](cases/README.md)。
