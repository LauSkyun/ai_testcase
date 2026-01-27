import xmind
import json
import zipfile
from pathlib import Path
from xmind.core.markerref import MarkerId

# ... existing code ...
def create_xmind_from_your_style():
    """生成测试用例，适配XMind 8格式"""
    
    # 创建新的工作簿
    workbook = xmind.load("test2.xmind")
    # workbook = xm.Workbook()

    # # 创建新的画布 可用，但会跟下面冲突
    # sheet1 = workbook.createSheet()
    # sheet1.setTitle("测试用例")
    
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
    
    xmind.save(workbook, "test2.xmind")

if __name__ == "__main__":
    # 示例数据
    testcase_data = {
        "模块1": [
            {
                "title": "用例1",
                "steps": [
                    {
                        "step": "步骤1",
                        "expected": ["预期结果1"]
                    },
                    {
                        "step": "步骤2",
                        "expected": ["预期结果2"]
                    }
                ]
            }
        ]
    }
    print(testcase_data.items())
    create_xmind_from_your_style()