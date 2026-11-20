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
    growth_rate: float
    competitor_info: str
    final_summary: str