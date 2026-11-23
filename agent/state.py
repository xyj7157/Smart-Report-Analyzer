from typing import TypedDict
from pydantic import BaseModel, Field

class FinancialMetrics(BaseModel):
    company_name: str = Field(description="公司名称")
    industry: str = Field(description="所属行业")
    revenue_current: float = Field(description="本期营业收入（亿元）")
    revenue_previous: float = Field(description="上期营业收入（亿元）")
    net_profit: float = Field(description="本期净利润（亿元）")

class AgentState(TypedDict):
    raw_text: str
    metrics: dict
    report_year: str  # 从财报原文识别的报告期年份（如 2025）
    report_period: str  # 报告期类型：年度/第一季度/第二季度/第三季度/第四季度/半年度
    growth_rate: float
    competitor_info: str
    compliance_rules: str  # 存放检索到的合规法条
    final_summary: str
    user_id: int  # 当前用户ID，用于数据隔离
