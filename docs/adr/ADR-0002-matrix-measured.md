# ADR-0002 · 解析器 v1.0 实测矩阵（替代 spike 参考值）

- 状态：已接受（实现期实测；**待老板在 M0 演示复核**）
- 背景：规格 §3.2 的 169/24/53/95 来自规格作者 spike 解析器的临时实现。M0 交付的解析器（token_parser v1.0，含 H/R 词典适配）对同一 341 条真实库的实测结果与之不同。按 SDLC §7 变更管理记录。

## 实测（2026-11-02，解析器 v1.0，双引擎已登记）

```
封面有 + tokens 完整：173   → 立即可看、可推荐、可主选（引擎可用族）
封面有 + tokens 残缺： 20   → 可看可对比；不可主选；进补标
封面无 + tokens 完整： 45   → 预演后可比；可推荐、可主选
封面无 + tokens 残缺：103   → no_preview；不可主选；进补标

tokens 完整 = 218（≥3/5 主字段：palette/texture/motion/type/composition；screen 为附加）
补标队列   = 123（解析失败全集，含 A-G 17 条）
producible = 60（print 5 + infographic 44 + pixel 11；riso + code-video 两引擎）
```

## 后果

1. 规格 §3.2 / §14.9 / §15 与 PRD 中的 169/24/53/95、119 保留为 spike 历史值，运行时以 `GET /api/library/status` 实测为准。
2. fixture 9 的矩阵断言改为"内部一致性 + 等于实测记录"（test_matrix_measured_consistency）。
3. photo 族 157 条 tokens 完整但无引擎——R1（引擎工期长杆）的量化呈现；ink 引擎按计划 M2 交付。
4. **code-video 引擎提前至 M0**（原 M1）：使可生产集合达 60 条，首屏推荐池可用。

## 复核要点（老板）

- [ ] 接受 173/20/45/103 与 123 补标为 M0 基线
- [ ] 接受 code-video 提前交付
- [ ] 补标队列 123 条的完成责任人与时限（PRD R3）
