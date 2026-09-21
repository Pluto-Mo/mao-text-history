# 全文复制与对应映射：最终验收

生成时间：2026-09-21T14:47:53.957355+00:00

## 实际交付

已保存 **1,476 个来源见证文件**，其中源 PDF **74 份、40,967 页**；另保存官方阅读器原始文字数组及逐页图片。

MIA 三个已登记目录的 **1410/1410 个文件 URL** 已保存。

## 逐套逐卷

| 版本 | 应有卷数 | 整份数字文件／完整阅读器 | 数字文件或全部登记网页已覆盖 |
|---|---:|---:|---:|
| [《毛泽东选集》第一至四卷：官方目录对应版次待版权页确认](../archive/editions/maoxuan-official.md) | 4 | 4 | 4 |
| [《毛泽东选集》第五卷（1977）](../archive/editions/maoxuan-1977-v5.md) | 1 | 0 | 1 |
| [《建国以来毛泽东文稿》旧13册](../archive/editions/wengao-old-13.md) | 13 | 13 | 13 |
| [《建国以来毛泽东文稿》2023修订20册](../archive/editions/wengao-2023-20.md) | 20 | 20 | 20 |
| [《毛泽东年谱（1893—1949）》旧三卷分组](../archive/editions/nianpu-pre1949-3.md) | 3 | 3 | 3 |
| [《毛泽东年谱（1949—1976）》旧六卷分组](../archive/editions/nianpu-post1949-6.md) | 6 | 6 | 6 |
| [《毛泽东年谱》2023修订九卷](../archive/editions/nianpu-2023-9.md) | 9 | 9 | 9 |
| [MIA目录：《毛泽东集》十卷](../archive/editions/mia-ji-10.md) | 10 | 10 | 10 |
| [MIA目录：《毛泽东集补卷》九卷](../archive/editions/mia-bujuan-9.md) | 9 | 9 | 9 |
| [MIA目录：《毛泽东集》著作年表](../archive/editions/mia-nianbiao.md) | 1 | 1 | 1 |
| [MIA目录：1968年武汉版《毛泽东思想万岁》五卷](../archive/editions/mia-1968.md) | 5 | 5 | 5 |
| [《毛泽东文集》第七卷（1999）辅助见证本](../archive/editions/wenji-1999.md) | 1 | 0 | 0 |

“整份数字文件”指来源文件已完整保存并验证字节；不代表原书无缺页、文字层无识别错误，或全部历史原稿已取得。
第五卷的网页转录与实体版扫描件分开计数；新版文稿20册与旧版13册、年谱新旧版本不互相替代。

## 映射已经落地到哪里

- 原网页目录：2,510 条；补入 PDF 内部目录后：11,394 条。
- 源 PDF 书签：8,889 条；标题在具体页／文本行中的出现记录：31,119 条。
- 作品入口 → 原网站目录定位 → 已存网页正文／整卷文件 → PDF页或阅读器页 → 字节校验值。
- 标题出现、同题和同卷关系仍是查阅线索，不自动成为确认的改稿因果链。

## 使用

```bash
python research.py search 关于正确处理人民内部矛盾的问题 --limit 20
python research.py versions 关于正确处理人民内部矛盾的问题
python research.py read <见证本ID> --page <PDF页或阅读器页>
python archive_corpus.py restore <见证本ID> /一个尚不存在的输出路径.pdf
```

扫描件已有文字层时保留其文字层；原文件、原文字层和检索时的空白归一化严格区分。不要把来源已有OCR错误解释成作者修订。
早期 reports/coverage.json、fulltext-coverage.json 和 docs/missing-materials.md 是历史阶段记录；最新状态以本报告与 completion.json 为准。

## 尚未取得的登记目标

本轮登记的四类复制范围内，没有剩余未保存的 MIA 文件 URL 或未覆盖的核心卷册。

辅助来源访问失败（不伪装成已取得）：
[
  {
    "id": "A-5fafe21451239548e96a",
    "url": "https://hprc.cssn.cn/gsyj/zzs/mzdsxyj/202405/t20240515_5751256.html",
    "error": "URLError: <urlopen error timed out>"
  }
]
