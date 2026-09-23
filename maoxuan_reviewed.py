"""Reviewed source statements as of 2026-09-23. Not manuscript authentication.
PINS prevents reusing a review against changed source bytes. IMAGES stores checksums
of rendered pages visually inspected in this research session (raw PDFs retained).
This module contains curated data, not an autonomous historical judge.
"""
PINS = {'A-08e901d73dcd78e98c4b': 'ba83874b716e334221fc1105f85530900883ec9430e36a13105ab5886eb22830', 'A-0a774548ee55c2288a21': 'fc9d8eb877991db15f55d3862fc949d4732b3e0bf5cf7d71fdfa4de2228b3113', 'A-22723c8864d2e1c9b830': 'c3f9b4434170500136dbbaf074731a17359acbf67406b55eed939ce221eafe58', 'A-264a603d150bc5388914': 'e92fe5099c1c865e951f472479118e4d2c3fa0056d6ef4f7738df4b564cd722c', 'A-273871842698fffe094a': '6dc86e862213defb559536872aa2d8bc7d7f9d4fe818601aa9e8798db588afff', 'A-29557ddcede8c9e85ac9': 'e2e3f27749fe886620ad1a719eacd68b9f404852382c1c47394642b24b1f6e6b', 'A-2c4941acc4b0d57f8bea': 'd0c6e1241d5370be4dd9dc81665080a3b997056bc6bd0b16e0fca7a0e032d90a', 'A-30d13185d1f27d6e4de9': 'db32b9fe81193d6391370affabe7b05b930968e84a81546362eba301a8e72fdd', 'A-3aabe7d7d8be471b024f': '2ee8791d0eb2d0babb07135205cd9c9cf32a6a9866e03a06e34e753ad0c9bfed', 'A-3d8f454387e25bfae9a9': '9e3cb10b0c5c6713fe98b61e09fe509107e512fc784b057367b6934bccb25015', 'A-3edbba386c609096f1e6': 'eee060820b346ecaa09c23476a00d975070d449455db6ceb31568ba30c512637', 'A-5ba786bea4aefb470c0b': '4ca52e96487a8e827a476f5d9b556556d13e3021182e5011bb9ea7ac955f9e6e', 'A-8bfc27ba981e89432b11': '69ab9aabd67e1f99fa085322c5e46d1e193bd493a74d54baefa266863ec6bd93', 'A-93d18940d055820ccb0b': '165c74e7ca4bb3cd0f2e85a05aafb77df18ad07c76da06ecadbd21685257c45e', 'A-97c183f19ad837e7deff': '493c817c7b58f899b5fae5d5287806745b41520aa6053cfab124f186a38e5cf3', 'A-980973716441b9197629': 'c4ad80b15f7c7bde2dac26caec6024460d6775ac4c04a8a0c17b3dc6f45c201c', 'A-99879515e4ed83368bf7': 'b2c76c044223c9e0a95d20f8f4d1c50873044338530e3e3b18ae8537ab5b7b64', 'A-bc29fda8b40043e7d0d2': '19c1956183851a8a23fb562403fcd985d0e2d13f6330b75204b6f58c9ebfa02d', 'A-c5de4e4d84dc4ea01b16': 'bac39d3b18677fccbf96e90055cdb23e27249dbd17a0bf11265d404548b88f3d', 'A-ce6e7a65555cd6cd36fd': 'f0c76c272810d80a1ea93070b4393d276933bc07a63bb54ae815590b803a4468', 'A-d0045246180c909e5ed7': 'bce6fefe71e712454ce136fe97838a26ba70fe68f09c5b6f372d32037d0e7637', 'A-d5c116872a1a98cb93ae': '3623abc1cbbd0df75c4bd359d9cf4fb1448caeeffa88b782f53b7fc760b3e624'}
IMAGES = {'A-ce6e7a65555cd6cd36fd:285': '646df9b08466515af3df70343c624d1c0c0c75836b420d44f5fad8d73d34c96c', 'A-97c183f19ad837e7deff:558': '9a14e2b127fff39106dbc6575ef28cdc4ab731161b06569695ec69ffd9051729', 'A-3aabe7d7d8be471b024f:162': '1fb06920d1942b158f65ca195f6d9fdc30adbbf4dbd903e0d2bb001017d80868', 'A-0a774548ee55c2288a21:348': '12934d1a28c7671d66f7b37a5bba1c9d6a217e992d86cbf0fb32bffe610a5b6a', 'A-08e901d73dcd78e98c4b:455': '4b455b3e9a955b92518636ad39213176316bfd4629a68fc1d844cec7a618c925', 'A-264a603d150bc5388914:196': 'b4dfdf022714ec251865f0d1e2109ed48840cf8b7667618fd537ebaa80773976'}

def reviewed(works, records):
    W = {w['id']: w for w in works}
    E = []
    byid = {r['id']: r for r in records}

    def p(rid, n, end=None, kind='pdf_page'):
        q = {'witness_id': rid, 'kind': kind, 'number': n, 'end': end or n, 'review_method': 'source_text_read'}
        assert byid[rid]['raw_sha256'] == PINS[rid], ('Reviewed source changed; re-review required', rid)
        if rid + ':' + str(n) in IMAGES:
            q.update(review_method='source_text_and_rendered_page_visual_check', review_image_sha256=IMAGES[rid + ':' + str(n)], printed_page_seen=n - 5)
        return q

    def b(wid):
        w = W[wid]
        q = w['baseline']
        return p(q['witness_id'], q['number'], kind=q['kind'])

    def web(wid, line=7, end=7):
        return p(W[wid]['baseline']['witness_id'], line, end, 'web_lines')

    def add(ids, rel, claim, sources, date=None, evclass='原书编者陈述'):
        E.append(dict(id=f'MXE-{len(E) + 1:03d}', work_ids=ids, relation_type=rel, claim=claim, sources=sources, date=date, evidence_class=evclass, summary_type='attributed_source_paraphrase', assistant_analysis=None, independent_historical_verification='not_asserted', limit='所列内容为来源记载的汇录；底本、转引、版本及文字层状态见逐条来源记录。'))
    add([], 'later_editorial_policy', '《毛泽东选集》1991年第二版出版说明称，保留原有篇目，增收《反对本本主义》，并校正部分日期、史实、字词和题解；说明将修订重点列为注释。', [p('A-8bfc27ba981e89432b11', 6, 7, 'reader_page')], '1991-02')
    add([], 'author_review_before_compilation', '《毛泽东选集》1951年出版说明称，收入作品经过作者校阅，有文字修正及个别内容的补充和修改；说明另述材料散失和选编情况。', [p('A-8bfc27ba981e89432b11', 8, 9, 'reader_page')], '1951-08-25')
    add(['MX1-003'], 'excerpt_and_retitle', '《中国的红色政权为什么能够存在？》题注称，该篇是《政治问题和边界党的任务》决议的一部分。', [b('MX1-003')], '1928-10-05')
    add(['MX1-005'], 'resolution_part', '《关于纠正党内的错误思想》题注称，该篇是红四军第九次党代会决议的第一部分。', [b('MX1-005')], '1929-12')
    add(['MX1-006'], 'retitle_and_named_criticism_removal', '《星星之火，可以燎原》题注称，该篇原为给林彪的信；题注记有1948年不公开姓名的请求，以及收入选集第一版时改题并删改指名批评之处的情况。', [b('MX1-006')], '1948／收入第一版时')
    add(['MX1-006'], 'publication_withheld_before_later_release', '《毛泽东年谱》1948年2月12日条载，毛泽东批示这封给林彪的信不要出版，并要求审阅所拟文集，暂缓东北局印行和翻译。', [p('A-ce6e7a65555cd6cd36fd', 285)], '1948-02-12', '年谱转录批语及编者说明')
    add(['MX1-007'], 'rediscovery_revision_and_retitle', '《毛泽东年谱》1961年3月11日条载，《调查工作》经文字修改后改题《关于调查工作》并印发；同条编者说明称，1964年收入《毛泽东著作选读》时改题《反对本本主义》，署为1930年5月。', [p('A-97c183f19ad837e7deff', 558)], '1961-03-11；1964')
    add(['MX1-007'], 'addition_to_second_edition', '《毛泽东选集》1991年第二版出版说明将《反对本本主义》列为增收篇目，并称该文曾散失、六十年代初重新找到，经作者审定，于1964年公开发表。', [p('A-8bfc27ba981e89432b11', 6, 7, 'reader_page')], '1964；1991-02')
    add(['MX1-013'], 'never_completed_not_lost', '《中国革命战争的战略问题》题注转述作者说明，已写成五章，原拟续写的战略进攻、政治工作等部分因西安事变发生而搁笔。', [b('MX1-013')], '1936-12', '原书编者转述作者说明')
    add(['MX1-017'], 'proposed_change_not_executed_at_first_publication', '《毛泽东年谱》1951年3月27日条转引致李达信，称《实践论》中将太平天国放在排外主义中一起说不妥，拟在出选集时修改；同页编者注称，第1卷出版时尚未按该意见修改。', [p('A-0a774548ee55c2288a21', 323)], '1951-03-27／第1卷出版时', '年谱转引书信＋编者实施状态说明')
    add(['MX1-018'], 'authorial_revision_on_collection', '《矛盾论》题注称，收入选集第一版时，作者作了部分补充、删节和修改。', [b('MX1-018')], '收入第一版时')
    add(['MX2-009'], 'speech_date_range', '《论持久战》题注所载讲演日期为1938年5月26日至6月3日；篇下日期标签为1938年5月。', [b('MX2-009')], '1938-05-26／1938-06-03')
    add(['MX2-010'], 'part_of_political_report', '《中国共产党在民族战争中的地位》题注称，该篇是《论新阶段》政治报告的一部分，报告于1938年10月12日至14日作，该部分于14日讲述。', [b('MX2-010')], '1938-10-12／1938-10-14')
    add(['MX2-011', 'MX2-012'], 'different_parts_of_concluding_speech', '《统一战线中的独立自主问题》和《战争和战略问题》的题注分别称，两篇是六届六中全会结论的一部分，讲述日期分别为1938年11月5日和6日。', [b('MX2-011'), b('MX2-012')], '1938-11-05／1938-11-06')
    add(['MX2-012'], 'translation_deletion_request_rejected', '《毛泽东年谱》1954年8月13日条记有英国共产党方面提出的英译本删段请求：拟删《战争和战略问题》第一节前两个自然段；同条所载中方复信不同意该请求。', [p('A-08e901d73dcd78e98c4b', 273, 274)], '1954-03-29请求／1954-08-13处理', '年谱转录来信、批语和复信')
    add(['MX2-023'], 'chapter_level_collaborative_authorship', '《中国革命和中国共产党》题注称，第一章由其他同志起草、毛泽东修改，第二章由毛泽东写，原拟第三章因承担写作的人没有完成而停止。', [b('MX2-023')], '1939年冬季')
    add(['MX2-023'], 'contextual_substantive_addition', '《毛泽东年谱》称，1940年反对第一次反共高潮结束后，《中国革命和中国共产党》第二章第四节加写三段，分别区分大资产阶级与民族资产阶级、亲日派与英美派大资产阶级、大地主与中小地主及开明绅士。', [p('A-3aabe7d7d8be471b024f', 162)], '1940年第一次反共高潮之后', '年谱编者关于修订的说明')
    add(['MX2-023'], 'author_explanation_reported_in_annotation', 'MIA所录《毛选》注释[34]和[34a]转引致萧向荣信，记有早先不易辨别不同阶层态度、至1940年3月看得更清楚的说明，并述及第二章的相应修改。', [p('A-29557ddcede8c9e85ac9', 284, 291, 'web_lines')], '1940年／注释称4月以后', '网页转录书注，再转引作者信件')
    add(['MX2-026'], 'publication_retitle', '《新民主主义论》题注记载原题为《新民主主义的政治与新民主主义的文化》，1940年2月15日刊于《中国文化》，2月20日刊于《解放》时改为现题。', [b('MX2-026')], '1940-01-09讲演；02-15／02-20刊载')
    add(['MX2-029'], 'institutional_telegram_not_personal_essay', '《向国民党的十点要求》题注称，该文是为延安民众讨汪大会起草的通电。', [b('MX2-029')], '1940-02-01')
    add(['MX3-008'], 'speech_parts_and_delayed_publication', '《在延安文艺座谈会上的讲话》的选集基线列有引言和结论。《毛泽东年谱》记载，1943年10月19日《解放日报》发表1942年5月的讲话，20日中央总学委通知组织学习。', [b('MX3-008'), p('A-3aabe7d7d8be471b024f', 483)], '1942-05；1943-10-19／10-20')
    add(['MX3-012'], 'retitled_first_chapter_not_whole_report', '《抗日时期的经济问题和财政问题》题注称，该篇是《经济问题与财政问题》报告的第一章，原章名为《关于过去工作的基本总结》。', [b('MX3-012'), p('A-8bfc27ba981e89432b11', 8, 8, 'reader_page')], '1942-12／编选时')
    add(['MX3-019'], 'institutional_appendix', '《毛泽东选集》第三卷将《关于若干历史问题的决议》标为附录，并注明1945年4月20日六届七中全会通过。', [b('MX3-019')], '1945-04-20', '基线标题和通过日期的直接观察')
    add(['MX4-003'], 'multiple_telegrams_one_collection_entry', '《第十八集团军总司令给蒋介石的两个电报》题注称，两份电报由毛泽东为第十八集团军总司令写。', [b('MX4-003')], '1945-08')
    add(['MX4-018'], 'different_dated_documents_compiled', '《中共中央关于暂时放弃延安和保卫陕甘宁边区的两个文件》在选集中合列两份文件，篇下注有不同日期；题注记述各自写作地点以及敌军占领延安前后的情况。', [b('MX4-018')], '1946-11／1947-04')
    add(['MX4-040'], 'operation_telegrams_compilation', '《关于辽沈战役的作战方针》的选集文本列有电报分项，首个小标题为“九月七日的电报”。', [b('MX4-040')], '1948-09／1948-10')
    add(['MX4-059'], 'excerpt_from_concluding_speech', '《党委会的工作方法》题注称，该篇是七届二中全会结论的一部分。', [b('MX4-059')], '1949-03-13')
    add(['MX4-066', 'MX4-067', 'MX4-068', 'MX4-069', 'MX4-070'], 'related_commentary_series_not_versions', '《丢掉幻想，准备斗争》题注将该篇及其后四篇列为毛泽东为新华社写的评论，评论对象为美国国务院白皮书和艾奇逊的信。', [b('MX4-066')], '1949-08／1949-09')
    add(['MX5-002'], 'collective_amendment', '《中国人民大团结万岁》网页题注称，毛泽东受会议委托起草宣言，“在人民领袖毛泽东主席领导之下”一句由会议代表在通过时提议增加。', [web('MX5-002')], '1949-09-30', '网站转录的第五卷题注')
    add(['MX5-007', 'MX5-006'], 'explanatory_speech_relates_to_written_report', '《不要四面出击》网页题注称，该篇是讲话的一部分，对《为争取国家财政经济状况的基本好转而斗争》书面报告作了说明。', [web('MX5-007')], '1950-06-06', '网站转录的第五卷题注')
    add(['MX5-015'], 'drafted_by_other_rewritten_and_retitled', '《毛泽东年谱》1951年5月19日条记载，毛泽东修改胡乔木起草的《为什么重视〈武训传〉的讨论》，改为《应当重视电影〈武训传〉的讨论》，以《人民日报》社论发表。', [p('A-0a774548ee55c2288a21', 348)], '1951-05-19', '年谱关于起草、改题及改写的说明')
    add(['MX5-015'], 'excerpt_of_editorial', 'MIA所录第五卷《应当重视电影〈武训传〉的讨论》题注称，该篇是社论的节录。', [web('MX5-015')], '第五卷编选时', '网站转录的第五卷题注')
    add(['MX5-018'], 'editorial_framing_separate_from_notice', 'MIA所录第五卷《把农业互助合作当作一件大事去做》的网页题注包含有关刘少奇和农业互助合作政策的编者说明；本记录的引用位置为网页题注。', [web('MX5-018')], '1951年正文／1977版题注', '对网页中题注与正文层次的观察')
    add(['MX5-044'], 'specified_textual_changes_reported_by_letter', '《毛泽东年谱》1955年10月13日条转录征求《关于农业合作化问题》第三次修正稿意见的信，信中列出合并章节、增加解释工农联盟的一节、替换适用地区表述、删例，以及补入注重质量、停顿间歇和及时批评等修改。', [p('A-08e901d73dcd78e98c4b', 455)], '1955-10-13', '年谱转录作者征求意见信')
    add(['MX5-044'], 'reported_revision_count_not_six_extant_drafts', '《毛泽东年谱》1955年10月14日讲话记录载，作者称农业合作化报告经过六次修改；10月13日条所转录信件使用“第三次修正稿”的表述。', [p('A-08e901d73dcd78e98c4b', 455, 456)], '1955-10-14', '年谱转录作者讲话')
    add(['MX5-048'], 'selection_of_annotations', '《〈中国农村的社会主义高潮〉的按语》网页题注称，作者写过104篇按语，本卷选辑43篇；题注另述1958年部分按语重印的情况。', [web('MX5-048')], '1955年写作／1958年重印／1977年选编', '网站转录的第五卷题注')
    add(['MX5-051'], 'internal_circulation_for_future_revision', '《毛泽东年谱》1965年12月条载，《论十大关系》拟发县团以上学习；18日批示称不大满意，发下去征求意见，以助将来修改。', [p('A-93d18940d055820ccb0b', 552)], '1965-12-18', '年谱转录批示')
    add(['MX5-051'], 'public_release_deferred', '《毛泽东年谱》1975年7月13日条载，在审阅《论十大关系》整理稿和公开发表请示时，批示暂不公开，可印发全党讨论，不登报，将来出选集时再公开。', [p('A-bc29fda8b40043e7d0d2', 603)], '1975-07-13', '年谱转录批示')
    add(['MX5-058'], 'speech_edited_before_publication', '《关于正确处理人民内部矛盾的问题》网页题注称，该文根据讲话原始记录整理并作补充，于1957年6月19日发表。', [web('MX5-058')], '1957-02-27讲话／1957-06-19发表', '网站转录的第五卷题注')
    add(['MX5-059'], 'later_prepublication_review', '《毛泽东年谱》1964年3月14日条载，1957年全国宣传工作会议讲话整理稿交康生、陈伯达审阅并提修改意见，拟收入新简选本；编者注称，1964年6月收入《毛泽东著作选读》甲种本。', [p('A-93d18940d055820ccb0b', 327, 328)], '1957年讲话／1964-03-14审核／1964-06编入', '年谱转录批示和编者出版说明')
    add(['MX5-060'], 'two_speeches_compiled', '《坚持艰苦奋斗，密切联系群众》网页题注称，该篇分别取自1957年3月18日济南讲话和3月19日南京讲话的一部分。', [web('MX5-060')], '1957-03-18／1957-03-19', '网站转录的第五卷题注')
    add(['MX5-066'], 'dated_sequence_of_revision_reports', '《毛泽东年谱》1957年7月19日至30日条载，《一九五七年夏季的形势》19日形成草稿和第一次修改稿，20日第二和第三次，25日第四次，26至27日第五至第八次，29日第九次，30日第十次。', [p('A-264a603d150bc5388914', 196, 197)], '1957-07-19／1957-07-30', '年谱逐日修订记载（关键日期已对照页图）')
    add(['MX5-066'], 'distribution_scope_and_approval_state_change', '《毛泽东年谱》所载《一九五七年夏季的形势》稿上说明及批示中，第三次稿拟发至地委一级，第四次稿拟发至县委及相当一级；第十次稿标称最后定稿，同时注明须交政治局批准，如有修改须告知。', [p('A-264a603d150bc5388914', 196, 197)], '1957-07-20／1957-07-25／1957-07-30', '年谱转录稿上说明、批示（已核关键页图）')
    add(['MX5-069', 'MX5-070'], 'same_meeting_different_excerpts', '《党内团结的辩证方法》和《一切反动派都是纸老虎》的网页题注均称，各篇为莫斯科共产党和工人党代表会议发言的节录。', [web('MX5-069'), web('MX5-070')], '1957-11-18', '网站转录的第五卷题注')
    add(['MX3-008', 'MX2-026', 'MX5-058', 'MX5-059'], 'revision_of_later_commentary_not_of_cited_works', '《毛泽东年谱》1966年文艺座谈会纪要修订条，记述纪要中引用四篇著作及相关措辞的修改；该条所列被修改文件为纪要。', [p('A-93d18940d055820ccb0b', 567)], '1966年', '对年谱所记被修改对象的核对')
    obj = {'schema_version': 1, 'review_scope': '只汇录公开来源所载信息和定位，不作助手的历史解释或评价', 'evidence': E}
    return obj
