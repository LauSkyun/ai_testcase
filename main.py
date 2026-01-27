#!/usr/bin/env python3
"""
AI驱动的自动化测试系统
双阶段Pipeline: 文档&代码分析 -> 测试用例生成
"""

import os
from pathlib import Path
from agents.doc_analyzer import analyze_documents
from generators.testcase_generator import generate_testcases_from_ir


def interactive_mode():
    """交互模式，允许用户查看和修改IR"""
    print("=== 进入交互模式 ===")
    print("正在分析文档并生成中间表示(IR)...")
    
    # 定义输入目录
    req_dir = Path("inputs/requirements")
    config_dir = Path("inputs/configs")
    protocol_dir = Path("inputs/protocols")
    
    # 获取输入文件
    req_files = [f for f in req_dir.iterdir() if f.suffix in ['.md', '.docx', '.txt', '.pdf']]
    config_files = [f for f in config_dir.iterdir() if f.suffix in ['.json', '.yaml', '.yml', '.txt']]
    protocol_files = [f for f in protocol_dir.iterdir() if f.suffix in ['.proto', '.txt']]
    
    if not req_files:
        print(f"警告: 未找到需求文档，请将文件放入 {req_dir} 目录")
        return
    
    # Phase 1: 分析文档
    ir = analyze_documents(
        requirement_files=req_files,
        config_files=config_files if config_files else None,
        protocol_files=protocol_files if protocol_files else None
    )
    
    while True:
        print("\n=== 第一阶段分析结果 ===")
        print(f"识别到 {len(ir.get('modules', []))} 个模块:")
        for i, module in enumerate(ir.get('modules', [])):
            print(f"  {i+1}. {module}")
        
        print(f"\n识别到 {len(ir.get('features', []))} 个特性:")
        for i, feature in enumerate(ir.get('features', [])[:5]):  # 只显示前5个
            print(f"  {i+1}. [{feature.get('module', '未知')} - {feature.get('type', '未知')}] {feature.get('desc', '无描述')}")
        
        if len(ir.get('features', [])) > 5:
            print(f"  ... 还有 {len(ir.get('features', [])) - 5} 个特性")
        
        print("\n选项:")
        print("1. 查看完整IR结构")
        print("2. 继续执行第二阶段（生成测试用例）")
        print("3. 退出")
        
        choice = input("\n请选择 (1/2/3): ").strip()
        
        if choice == '1':
            print("\n--- 完整IR结构 ---")
            print(ir)
            input("\n按回车键继续...")
        elif choice == '2':
            print("\n开始第二阶段：测试用例生成...")
            output_path = "outputs/test_cases.xmind"
            generate_testcases_from_ir(ir, output_path)
            print(f"测试用例已生成到: {output_path}")
            break
        elif choice == '3':
            print("退出交互模式")
            break
        else:
            print("无效选择，请重新输入")


def phase1_only():
    """只执行第一阶段：文档分析"""
    print("=== 只执行第一阶段：文档分析 ===")
    
    # 定义输入目录
    req_dir = Path("inputs/requirements")
    config_dir = Path("inputs/configs")
    protocol_dir = Path("inputs/protocols")
    
    # 获取输入文件
    req_files = [f for f in req_dir.iterdir() if f.suffix in ['.md', '.docx', '.txt', '.pdf']]
    config_files = [f for f in config_dir.iterdir() if f.suffix in ['.json', '.yaml', '.yml', '.txt']]
    protocol_files = [f for f in protocol_dir.iterdir() if f.suffix in ['.proto', '.txt']]
    
    if not req_files:
        print(f"警告: 未找到需求文档，请将文件放入 {req_dir} 目录")
        return
    
    print("开始第一阶段：文档分析...")
    # Phase 1: 分析文档
    ir = analyze_documents(
        requirement_files=req_files,
        config_files=config_files if config_files else None,
        protocol_files=protocol_files if protocol_files else None
    )
    
    print("文档分析完成，IR结构:")
    print(ir)
    

def main():
    print("AI驱动的自动化测试系统")
    print("请选择运行模式:")
    print("1. 正常模式（执行完整双阶段Pipeline）")
    print("2. 仅第一阶段（只分析文档）")
    print("3. 交互模式（可查看、验证IR并决定后续操作）")
    
    choice = input("请输入选择 (1/2/3): ").strip()
    
    if choice == '1':
        # 正常模式 - 执行完整流程
        req_dir = Path("inputs/requirements")
        config_dir = Path("inputs/configs")
        protocol_dir = Path("inputs/protocols")
        
        # 获取输入文件
        req_files = [f for f in req_dir.iterdir() if f.suffix in ['.md', '.docx', '.txt', '.pdf']]
        config_files = [f for f in config_dir.iterdir() if f.suffix in ['.json', '.yaml', '.yml', '.txt']]
        protocol_files = [f for f in protocol_dir.iterdir() if f.suffix in ['.proto', '.txt']]
        
        if not req_files:
            print(f"警告: 未找到需求文档，请将文件放入 {req_dir} 目录")
            return
        
        print("开始第一阶段：文档分析...")
        # Phase 1: 分析文档
        ir = analyze_documents(
            requirement_files=req_files,
            config_files=config_files if config_files else None,
            protocol_files=protocol_files if protocol_files else None
        )
        
        print("文档分析完成，IR结构:")
        print(ir)
        
        print("\n开始第二阶段：测试用例生成...")
        # Phase 2: 生成测试用例
        output_path = "outputs/test_cases.xmind"
        generate_testcases_from_ir(ir, output_path)
        
        print(f"测试用例已生成到: {output_path}")
    
    elif choice == '2':
        phase1_only()
    
    elif choice == '3':
        interactive_mode()
    
    else:
        print("无效选择，运行默认完整流程")
        # 默认运行完整流程
        req_dir = Path("inputs/requirements")
        config_dir = Path("inputs/configs")
        protocol_dir = Path("inputs/protocols")
        
        # 获取输入文件
        req_files = [f for f in req_dir.iterdir() if f.suffix in ['.md', '.docx', '.txt', '.pdf']]
        config_files = [f for f in config_dir.iterdir() if f.suffix in ['.json', '.yaml', '.yml', '.txt']]
        protocol_files = [f for f in protocol_dir.iterdir() if f.suffix in ['.proto', '.txt']]
        
        if not req_files:
            print(f"警告: 未找到需求文档，请将文件放入 {req_dir} 目录")
            return
        
        print("开始第一阶段：文档分析...")
        # Phase 1: 分析文档
        ir = analyze_documents(
            requirement_files=req_files,
            config_files=config_files if config_files else None,
            protocol_files=protocol_files if protocol_files else None
        )
        
        print("文档分析完成，IR结构:")
        print(ir)
        
        print("\n开始第二阶段：测试用例生成...")
        # Phase 2: 生成测试用例
        output_path = "outputs/test_cases.xmind"
        generate_testcases_from_ir(ir, output_path)
        
        print(f"测试用例已生成到: {output_path}")


if __name__ == "__main__":
    main()