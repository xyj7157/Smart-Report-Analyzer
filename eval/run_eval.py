import json
import os
import sys
from dotenv import load_dotenv

# 把项目根目录加入系统路径，方便导入 agent 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.nodes import extract_data_node, llm  # 直接复用你写好的提取节点

load_dotenv()


def evaluate_extraction():
    print("=== 🚀 开始大模型数据提取评测 (LLM-as-a-Judge) ===")

    # 1. 加载评测数据集
    with open("eval/eval_dataset.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)

    total_tests = len(dataset)
    correct_count = 0

    for item in dataset:
        print(f"\n[测试用例 {item['id']}] 正在提取 {item['expected']['company_name']}...")

        # 2. 调用你的 Agent 节点进行提取
        state = {"raw_text": item["text"]}
        try:
            result = extract_data_node(state)
            extracted_metrics = result["metrics"]
        except Exception as e:
            print(f"  ❌ 提取失败（代码报错）: {e}")
            continue

        # 3. 让大模型作为裁判，对比“提取结果”与“标准答案”
        judge_prompt = f"""
        你是一个严格的财务数据审核员。请对比以下两份数据是否一致。

        【标准答案】
        {json.dumps(item['expected'], ensure_ascii=False)}

        【AI提取结果】
        {json.dumps(extracted_metrics, ensure_ascii=False)}

        请注意：如果数字的误差在 ±0.1 以内，视为一致。如果公司名称或行业有轻微同义词（如"新能源"和"新能源电池"），也视为一致。

        请返回严格的JSON格式：
        {{"is_correct": true或false, "reason": "简要说明原因"}}
        """

        judge_response = llm.invoke(judge_prompt).content
        # 清理可能存在的 markdown 标记
        judge_response = judge_response.replace("```json", "").replace("```", "").strip()

        try:
            judgement = json.loads(judge_response)
            if judgement.get("is_correct"):
                print(f"  ✅ 评测通过！")
                correct_count += 1
            else:
                print(f"  ❌ 评测不通过。裁判理由：{judgement.get('reason')}")
        except Exception as e:
            print(f"  ⚠️ 裁判解析失败，原始输出: {judge_response}")

    # 4. 计算准确率并输出最终报告
    accuracy = (correct_count / total_tests) * 100
    print("\n" + "=" * 40)
    print(f"📊 评测完成！")
    print(f"总测试用例: {total_tests}")
    print(f"提取正确数: {correct_count}")
    print(f"🎯 最终准确率 (Accuracy): {accuracy:.2f}%")
    print("=" * 40)


if __name__ == "__main__":
    evaluate_extraction()