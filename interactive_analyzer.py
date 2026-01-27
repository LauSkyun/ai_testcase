# interactive_analyzer.py
import os
import json
import sys
from pathlib import Path
from datetime import datetime

def build_analysis_prompt(doc_texts: list, custom_instruction: str = ""):
    base = """你是一名专业的资深游戏测试，专门将自然语言的需求文档解析为结构化、无歧义的机器可读规范。你的输出将直接用于AI-agent的代码实现检查和游戏用例编写。

要求：
1. 全局理解与摘要：首先快速理解文档的整体目标和核心玩法，用一段话概括
2. 逻辑校验与问题发现：在提取信息的同时，自动检查并记录文档中的逻辑矛盾、规则遗漏、描述模糊和技术风险点
3. 模块化分解：识别所有独立的功能模块，并拆解其核心特性（包括行为、规则、约束、状态等）
4. 实现要素提取：提取协议字段、ID范围、配置表结构、奖励数据等工程实现所需的关键信息
5. 测试支持准备：确保提取的信息包含输入/输出、前后置条件，可用于编写测试用例
6. 输出严格结构化：所有输出必须严格按照指定的JSON格式，不添加任何额外解释

输出格式：
{
  "summary": "string",
  "validation_warnings": [
    {
      "type": "LOGIC_CONFLICT|RULE_GAP|AMBIGUITY|TECH_RISK|IMPLEMENTATION_COMPLEXITY|MISSING_EDGE_CASES|PERFORMANCE_CONCERN",
      "module": "string",
      "description": "string",
      "suggestion": "string"
    }
  ],
  "modules": ["string"],
  "features": [
    {
      "module": "string",
      "name": "string",
      "description": "string",
      "type": "BEHAVIOR|RULE|CONSTRAINT|STATE|EVENT|TRIGGER",
      "input": ["string"],
      "output": ["string"],
      "preconditions": ["string"],
      "postconditions": ["string"],
      "edge_cases": ["string"],
      "failure_scenarios": ["string"]
    }
  ],
  "protocols": {
    "messages": [
      {
        "id_range": "string",
        "name": "string",
        "desc": "string",
        "fields": [
          {"name": "string", "type": "string", "desc": "string"}
        ]
      }
    ],
    "key_entities": [
      {
        "entity": "string",
        "sync_fields": ["string"]
      }
    ]
  },
  "configs": {
    "tables": [
      {
        "name": "string",
        "key_field": "string",
        "columns": [
          {"name": "string", "type": "string", "desc": "string", "constraint": "string"}
        ]
      }
    ],
    "constants": {
      "enums": [
        {
          "name": "string",
          "values": [
            {"name": "string", "value": "string|number", "desc": "string"}
          ]
        }
      ],
      "variables": [
        {"name": "string", "type": "string", "default": "string|number", "desc": "string", "range": "string"}
      ]
    },
    "rewards": [
      {
        "source": "string",
        "reward_id": "string",
        "items": [
          {"type": "string", "id_or_name": "string", "amount": "number", "weight": "number"}
        ]
      }
    ]
  },
  "test_scenarios": [
    {
      "module": "string",
      "scenario_name": "string",
      "precondition": "string",
      "action": "string",
      "expected_result": "string",
      "priority": "HIGH|MEDIUM|LOW",
      "automatable": boolean
    }
  ]
}"""
    if custom_instruction:
        base += f"\n【额外指令】\n{custom_instruction}\n"
    
    base += "\n【文档内容】\n"
    for i, text in enumerate(doc_texts, 1):
        base += f"\n--- 文档 {i} ---\n{text}\n"
    return base


def main():
    print("🔍 欢迎使用 AI 需求分析器（Phase 1）")
    print("支持 .docx, .pdf, .md, .txt 等格式")
    
    # 导入文档分析器
    try:
        from agents.doc_analyzer import extract_text
    except ImportError as e:
        print(f"❌ 无法导入文档分析器: {e}")
        print("请确保在项目根目录下运行此脚本")
        sys.exit(1)
    
    doc_files = []
    file_paths = []

    # 创建输出目录
    output_dir = Path("doc_output")
    output_dir.mkdir(exist_ok=True)

    while True:
        print("\n=== 操作选项 ===")
        print("1. 添加需求文档（自动从requirements目录查找）")
        print("2. 查看已加载文档")
        print("3. 开始分析并自动保存结果")
        print("4. 自定义分析指令（可选）")
        print("5. 查看requirements目录下的所有文档")
        print("6. 退出")
        
        choice = input("\n请选择 (1-6): ").strip()
        
        if choice == "1":
            filename = input("请输入文件名（例如: requirement.docx）: ").strip()
            req_path = Path("requirements") / filename
            
            if req_path.exists():
                # 验证是否支持该文件类型
                file_ext = req_path.suffix.lower()
                supported_exts = ['.md', '.docx', '.txt', '.pdf', '.json', '.yaml', '.yml', '.xml', '.proto']
                if file_ext in supported_exts:
                    doc_files.append(req_path)
                    file_paths.append(str(req_path))
                    print(f"✅ 已加载: {req_path}")
                else:
                    print(f"⚠️ 不支持的文件类型: {file_ext}，支持的类型: {supported_exts}")
            else:
                print(f"❌ 文件不存在: {req_path}")
                
        elif choice == "2":
            if not file_paths:
                print("ostringstream 尚未加载任何文档")
            else:
                print("📄 已加载:")
                for p in file_paths:
                    print(f" - {p}")
        
        elif choice == "5":
            req_dir = Path("requirements")
            if req_dir.exists():
                files = [f for f in req_dir.iterdir() if f.suffix in ['.md', '.docx', '.txt', '.pdf', '.json', '.yaml', '.yml', '.xml', '.proto']]
                if files:
                    print("📄 requirements目录下的文档:")
                    for f in files:
                        print(f" - {f.name}")
                else:
                    print("ostringstream requirements目录中没有找到支持的文档")
            else:
                print("❌ requirements目录不存在")
                    
        elif choice == "3":
            if not doc_files:
                print("❗ 请先添加至少一个文档")
                continue
                
            # 使用doc_analyzer中的extract_text函数
            doc_texts = []
            for file_path in doc_files:
                print(f"🔄 正在解析: {file_path.name}")
                text = extract_text(str(file_path))
                if text.strip():
                    doc_texts.append(text)
                else:
                    print(f"⚠️ 无法从 {file_path.name} 提取内容")
            
            if not doc_texts:
                print("❌ 没有成功解析任何文档")
                continue
            
            custom_inst = getattr(main, "custom_instruction", "")
            prompt = build_analysis_prompt(doc_texts, custom_inst)
            
            # 使用llm_client调用大模型
            try:
                from core.llm_client import call_qwen3
                ir = call_qwen3(prompt)
            except ImportError:
                print("❌ 无法导入LLM客户端，请确保core/llm_client.py存在")
                return
            except Exception as e:
                print(f"💥 分析出错: {e}")
                return
            
            if ir and isinstance(ir, dict) and ir.get("modules") is not None:
                print("\n✅ 结构化分析结果 (IR):")
                print(json.dumps(ir, ensure_ascii=False, indent=2))
                
                # 显示摘要信息
                modules_count = len(ir.get("modules", []))
                features_count = len(ir.get("features", []))
                warnings_count = len(ir.get("validation_warnings", []))
                print(f"\n📊 摘要: 识别到 {modules_count} 个模块, {features_count} 个特性, {warnings_count} 个潜在问题")
                
                # 自动生成输出文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_filename = doc_files[0].stem  # 获取第一个文档的基础文件名（不含扩展名）
                output_filename = f"{base_filename}_{timestamp}.json"
                output_path = output_dir / output_filename
                
                # 保存结果
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(ir, f, ensure_ascii=False, indent=2)
                print(f"💾 已自动保存至: {output_path}")
            else:
                print("❌ 未能生成有效结果")
                if not ir:
                    print("   请检查Ollama服务和模型是否正确安装")
                
        elif choice == "4":
            inst = input("请输入自定义指令（例如：'重点关注异常流程'）: ").strip()
            main.custom_instruction = inst
            print("📝 自定义指令已设置")
            
        elif choice == "6":
            print("👋 再见！")
            break
        else:
            print("❓ 无效选项")

if __name__ == "__main__":
    # 检查必要的依赖
    try:
        import requests
    except ImportError:
        print("❌ 缺少依赖，请先安装:")
        print("pip install requests")
        sys.exit(1)
    
    main()