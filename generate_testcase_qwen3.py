# generate_testcase_qwen3.py
import os
import re
import json
import zipfile
import requests
from pathlib import Path
from unstructured.partition.auto import partition

# ===== 配置区 =====
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:8b"  # 确保你已 ollama pull qwen3:8b


def extract_text(file_path: str) -> str:
    """解析 Word/PDF/Markdown/TXT 为纯文本"""
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_ext in ['.md', '.markdown']:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_ext == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        full_text.append(cell.text)
            return '\n'.join(full_text)
        except ImportError:
            raise RuntimeError(f"❌ 请安装 python-docx: pip install python-docx")
    elif file_ext == '.pdf':
        try:
            import PyPDF2
            text = ""
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except ImportError:
            raise RuntimeError(f"❌ 请安装 PyPDF2: pip install PyPDF2")
    else:
        # 如果是其他格式，尝试使用 unstructured
        try:
            from unstructured.partition.auto import partition
            elements = partition(filename=file_path)
            return "\n".join([str(e) for e in elements])
        except ImportError:
            raise RuntimeError(f"❌ 不支持的文件格式 {file_ext} 且未安装相应解析库")
        except Exception as e:
            raise RuntimeError(f"❌ 文档解析失败: {e}")


def build_prompt_with_your_style(requirement_text: str) -> str:
    """构建严格匹配你格式的 Prompt"""
    return f"""你是一名资深游戏测试工程师，请根据以下需求文档生成测试用例。

【输出规则】
1. 每个用例标题必须以 "tc:" 开头（例如 "tc:单人"）
2. 用例结构为：
   - 用例标题（带 tc:）
   - 测试步骤（行为描述，如“只有玩家自己进入游戏”）
   - 每个测试步骤下挂 1~N 个预期结果（验证点，如“进入随机抽取的关卡”）
3. 不要写“前置条件”“步骤”等字段名，不要解释，不要 Markdown
4. 仅输出严格 JSON，格式如下：

{{
  "游戏模式": [
    {{
      "title": "tc:单人",
      "steps": [
        {{
          "step": "只有玩家自己进入游戏",
          "expected": ["正常进行游戏", "进入随机抽取的关卡"]
        }}
      ]
    }}
  ]
}}

【需求文档】
---
{requirement_text}
---
"""


def clean_json_output(raw: str) -> str:
    """从 LLM 输出中提取最外层 JSON 对象"""
    # 匹配从第一个 {{ 到最后一个 }}
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("未找到有效 JSON")
    return match.group()


def generate_testcase_json(requirement_text: str) -> dict:
    prompt = build_prompt_with_your_style(requirement_text)
    
    print("🧠 正在调用 Qwen3 生成测试用例（请稍候）...")
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192
            }
        },
        timeout=600
    )
    response.raise_for_status()
    raw_output = response.json()["response"]
    
    try:
        json_str = clean_json_output(raw_output)
        return json.loads(json_str)
    except Exception as e:
        print("❌ 模型输出解析失败，原始输出：")
        print(raw_output)
        raise RuntimeError(f"JSON 解析错误: {e}")


def create_xmind_from_your_style(testcase_data: dict, output_path: str):
    """使用xmind库生成.xmind文件，适配XMind 8格式"""
    import xmind
    from xmind.core.markerref import MarkerId
    
    # 直接使用输出路径加载文件，如果不存在会自动创建
    workbook = xmind.load(output_path)
    
    # 获取第一个画布（Sheet）
    sheet = workbook.getPrimarySheet()
    sheet.setTitle("测试用例")

    # 获取画布的中心主题
    root_topic = sheet.getRootTopic()
    root_topic.setTitle("AI生成测试用例")

    # 为每个模块创建子主题
    for module, cases in testcase_data.items():
        module_topic = root_topic.addSubTopic()
        module_topic.setTitle(module)
        
        # 为每个测试用例创建子主题
        for case in cases:
            case_topic = module_topic.addSubTopic()
            case_topic.setTitle(case["title"])
            
            # 为每个测试步骤创建子主题
            for step_info in case.get("steps", []):
                step_topic = case_topic.addSubTopic()
                step_topic.setTitle(step_info["step"])
                
                # 为每个预期结果创建子主题
                for exp in step_info.get("expected", []):
                    exp_topic = step_topic.addSubTopic()
                    exp_topic.setTitle(exp)
    
    # 保存文件到目标路径
    xmind.save(workbook, path=output_path)


def main(input_file: str, output_file: str = "testcase.xmind"):
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"输入文件不存在: {input_file}")

    print("📄 1. 解析需求文档...")
    text = extract_text(input_file)
    if not text.strip():
        raise ValueError("文档内容为空")

    print("🤖 2. 调用本地 Qwen3 生成测试用例...")
    testcase_json = generate_testcase_json(text)

    print("📁 3. 生成 XMind 文件...")
    create_xmind_from_your_style(testcase_json, output_file)

    print(f"✅ 成功！XMind 文件已保存至:\n{os.path.abspath(output_file)}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python generate_testcase_qwen3.py <需求文档路径> [输出.xmind]")
        print("示例: python generate_testcase_qwen3.py req.docx game_test.xmind")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "testcase.xmind"
    try:
        main(input_path, output_path)
    except Exception as e:
        print(f"💥 错误: {e}")
        sys.exit(1)