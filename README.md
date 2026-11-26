# Voucher Preflight · 凭证预检

导入账套之前，先离线检查通用凭证 CSV：哪些凭证借贷不平、哪些来源行可能被重复用过、哪些行缺少记账币种或关键字段。只生成报告，不改原文件，不连接任何账套。

```sh
git clone https://github.com/s1166921-png/voucher-preflight.git
cd voucher-preflight
python preflight.py examples/vouchers.csv
```

Python 3.10+，无第三方依赖。上面的样例完全虚构，故意包含问题。退出码：`0` 无问题、`1` 有待复核项（仍输出 JSON）、`2` 文件无法读取或结构错误。

| 虚构凭证 | 检查结果 |
| --- | --- |
| 0001 | 同一凭证号两条分录是正常的；原交易币种不同，按统一的 CNY 记账额检查平衡 |
| 0002 | 借方和贷方相差 CNY 0.02 |
| 0003 | 来源行重复，不能仅凭借贷合计相等就放行 |
| 0004 | 缺少记账币种，不能用原币金额猜测 |

## 输入和检查范围

- UTF-8 CSV，可含 BOM。必需列：`ledger,period,voucher_id,source_line_id,account,booked_currency,debit,credit`。账期格式 `YYYY-MM`，编号按文本处理（保留前导零，忽略首尾空白）。
- 凭证按「账套 + 账期 + 凭证号」分组。每条分录使用稳定来源行编号；若同一业务事项拆成多条分录，应给各分录独立且可重现的编号。只检测同一账套、同一账期的当前输入，不查询历史凭证，不自动去重。
- 借贷必须都是已确定的记账币种金额，同张凭证不能混用多个记账币种；每行只有一边大于零，另一边可空或为零。只支持不带千位分隔符的十进制（小数点用 `.`）。以精确金额比对，不自动四舍五入或换汇。`transaction_currency` 等附加列不参与检查。
- 报告标记原始 CSV 行号。通过只表示符合上述检查，不代表科目、税务、原币或报表币种正确，也不保证任何财务软件能够导入。请勿提交公司账表或个人数据。

## English

Offline validation of a generic voucher CSV: scope by ledger/period/voucher, flag duplicate stable source lines, and compare exact debits and credits in one booked currency per voucher. This does not validate FX, tax, account mappings or posted history. Run tests with `python -m unittest -v`. MIT.

Related: [Statement Normalize](https://github.com/s1166921-png/statement-normalize) for preparing receipt CSVs; [Payout Reconcile](https://github.com/s1166921-png/payout-reconcile) for checking platform payouts against receipts. Neither generates vouchers.
