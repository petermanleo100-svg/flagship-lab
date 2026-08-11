from __future__ import annotations

from .regintel import RegIntelService


DEMO_DOCUMENTS = [
    ("vat-calc", "增值税税额计算演示规则", "一般计税方法下，演示税额按照不含税销售额乘以适用税率计算。", "2026-01-01"),
    ("invoice-check", "电子发票信息核验演示规则", "电子发票核验应检查发票号码、开票日期、销售方税号、购买方税号和价税合计。", "2026-01-02"),
    ("cit-deduction", "企业所得税费用扣除演示规则", "企业所得税演示场景中，费用扣除需要真实业务、合规凭证并与生产经营相关。", "2026-01-03"),
    ("iit-special", "个人所得税专项附加扣除演示规则", "个人所得税演示场景包括子女教育、继续教育、住房贷款利息和赡养老人等专项附加扣除。", "2026-01-04"),
    ("export-refund", "出口退税单证演示规则", "出口退税演示流程需要匹配报关单、出口发票、收汇信息和申报批次。", "2026-01-05"),
    ("transfer-price", "转让定价同期资料演示规则", "关联交易达到演示阈值时，应准备主体文档、本地文档或特殊事项文档并说明定价方法。", "2026-01-06"),
    ("social-insurance", "社会保险缴费基数演示规则", "社会保险演示核验比较员工工资数据、缴费基数上下限和实际申报记录。", "2026-01-07"),
    ("tax-calendar", "税务申报日历演示规则", "税务申报日历记录税种、所属期、申报截止日期、责任人和完成状态。", "2026-01-08"),
]


DEMO_CASES = [
    {"query": "增值税如何根据销售额算税额", "relevant_keys": ["vat-calc"]},
    {"query": "核对电子票需要检查哪些字段", "relevant_keys": ["invoice-check"]},
    {"query": "企业所得税费用税前扣除凭证", "relevant_keys": ["cit-deduction"]},
    {"query": "住房贷款利息属于什么个税扣除", "relevant_keys": ["iit-special"]},
    {"query": "出口退税要匹配报关单吗", "relevant_keys": ["export-refund"]},
    {"query": "关联交易同期资料本地文档", "relevant_keys": ["transfer-price"]},
    {"query": "社保缴费基数如何核验", "relevant_keys": ["social-insurance"]},
    {"query": "申报截止日期和责任人在哪里管理", "relevant_keys": ["tax-calendar"]},
    {"query": "价税合计和购买方税号核验", "relevant_keys": ["invoice-check"]},
    {"query": "赡养老人专项附加扣除", "relevant_keys": ["iit-special"]},
    {"query": "主体文档与定价方法", "relevant_keys": ["transfer-price"]},
    {"query": "申报所属期完成状态", "relevant_keys": ["tax-calendar"]},
]


def load_demo_corpus(service: RegIntelService) -> None:
    for key, title, content, published in DEMO_DOCUMENTS:
        service.add_document(key, title, f"https://example.invalid/{key}", published, content + " 本材料为合成演示文本，不构成税务建议。")

