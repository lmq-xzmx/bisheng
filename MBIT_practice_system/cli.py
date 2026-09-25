#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MBTI 功能冲突对话建议系统 - CLI查询工具
"""

import sqlite3
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'database', 'mbti.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def print_type_info(code):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM mbti_type WHERE code = ?', (code.upper(),))
    row = cursor.fetchone()
    
    if not row:
        print(f"错误: MBTI类型 {code} 不存在")
        conn.close()
        return
    
    print_header(f"MBTI类型: {row['code']} - {row['name_cn']}")
    print(f"  E/I: {'外倾(E)' if row['e_i'] == 'E' else '内倾(I)'}")
    print(f"  S/N: {'感觉型(S)' if row['s_n'] == 'S' else '直觉型(N)'}")
    print(f"  T/F: {'思考型(T)' if row['t_f'] == 'T' else '情感型(F)'}")
    print(f"  J/P: {'判断型(J)' if row['j_p'] == 'P' else '知觉型(P)'}")
    print(f"  描述: {row['description']}")
    
    cursor.execute('''
        SELECT fs.position, f.code, f.name_cn, f.category, f.attitude
        FROM mbti_function_stack fs
        JOIN mbti_function f ON fs.function_code = f.code
        WHERE fs.mbti_code = ?
        ORDER BY fs.position
    ''', (code,))
    
    print("\n功能序位:")
    for func in cursor.fetchall():
        shadow = "(阴影)" if func[4] == 1 else ""
        print(f"  {func[0]}. {func[2]} {shadow}")
    
    conn.close()

def print_pair_suggestion(code_a, code_b):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM mbti_pair_suggestion 
        WHERE (mbti_a = ? AND mbti_b = ?) OR (mbti_a = ? AND mbti_b = ?)
    ''', (code_a.upper(), code_b.upper(), code_b.upper(), code_a.upper()))
    
    row = cursor.fetchone()
    
    if not row:
        print(f"未找到 {code_a} 与 {code_b} 的预设建议，生成动态建议...")
        generate_dynamic_suggestion(cursor, code_a, code_b)
        conn.close()
        return
    
    print_header(f"对话建议: {code_a} + {code_b}")
    print(f"  匹配度: {row['compatibility']}")
    print(f"  主要冲突: {row['main_conflict']}")
    print(f"\n  沟通要点:")
    print(f"    {row['communication_tips']}")
    print(f"\n  推荐话题:")
    print(f"    {row['recommended_topics']}")
    
    things_to_do = json.loads(row['things_to_do']) if row['things_to_do'] else []
    things_to_avoid = json.loads(row['things_to_avoid']) if row['things_to_avoid'] else []
    
    print(f"\n  ✅ 应该做的:")
    for item in things_to_do:
        print(f"    • {item}")
    
    print(f"\n  ❌ 不应该做的:")
    for item in things_to_avoid:
        print(f"    • {item}")
    
    conn.close()

def generate_dynamic_suggestion(cursor, mbti_a, mbti_b):
    cursor.execute('SELECT * FROM mbti_type WHERE code = ?', (mbti_a.upper(),))
    type_a = dict(cursor.fetchone())
    cursor.execute('SELECT * FROM mbti_type WHERE code = ?', (mbti_b.upper(),))
    type_b = dict(cursor.fetchone())
    
    if not type_a or not type_b:
        print(f"错误: MBTI类型不存在")
        return
    
    print_header(f"对话建议: {mbti_a} + {mbti_b} (动态生成)")
    
    conflicts = []
    if type_a['e_i'] != type_b['e_i']:
        conflicts.append('E vs I - 外倾/内倾')
    if type_a['s_n'] != type_b['s_n']:
        conflicts.append('S vs N - 感觉/直觉')
    if type_a['t_f'] != type_b['t_f']:
        conflicts.append('T vs F - 思考/情感')
    if type_a['j_p'] != type_b['j_p']:
        conflicts.append('J vs P - 判断/知觉')
    
    score = 0
    if type_a['e_i'] == type_b['e_i']: score += 1
    if type_a['s_n'] == type_b['s_n']: score += 1
    if type_a['t_f'] == type_b['t_f']: score += 1
    if type_a['j_p'] == type_b['j_p']: score += 1
    
    compatibility = '高' if score >= 3 else ('中' if score >= 2 else '低')
    print(f"  匹配度: {compatibility}")
    print(f"  主要冲突: {' | '.join(conflicts) if conflicts else '无明显冲突'}")
    
    print(f"\n  沟通要点:")
    if type_a['e_i'] != type_b['e_i']:
        print(f"    • 尊重对方的社交节奏，外倾型给内倾型足够的思考空间")
    if type_a['s_n'] != type_b['s_n']:
        print(f"    • 互相举例说明自己的观点，感觉型注重细节，直觉型关注可能")
    if type_a['t_f'] != type_b['t_f']:
        print(f"    • 尊重对方的决策方式，思考型注重逻辑，情感型注重感受")
    if type_a['j_p'] != type_b['j_p']:
        print(f"    • 找到计划与灵活的平衡点")
    
    print(f"\n  ✅ 应该做的:")
    print(f"    • 尊重对方的性格特点")
    print(f"    • 保持开放和真诚的沟通")
    print(f"    • 理解并接纳不同的思维方式")
    
    print(f"\n  ❌ 不应该做的:")
    print(f"    • 强制改变对方的性格特点")
    print(f"    • 嘲笑或否定对方的思维方式")
    print(f"    • 把自己的沟通方式强加给对方")

def print_conflict_solutions():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM function_conflict_type')
    conflicts = cursor.fetchall()
    
    print_header("功能冲突类型")
    for conflict in conflicts:
        print(f"\n【{conflict['conflict_code']}】- {conflict['dimension']}")
        print(f"  {conflict['description']}")
        
        cursor.execute('SELECT * FROM conflict_solution WHERE conflict_code = ?', (conflict['conflict_code'],))
        solution = cursor.fetchone()
        if solution:
            print(f"\n  典型场景: {solution['situation']}")
            print(f"  解决方案: {solution['solution']}")
            do_list = json.loads(solution['do_list']) if solution['do_list'] else []
            dont_list = json.loads(solution['dont_list']) if solution['dont_list'] else []
            if do_list:
                print(f"  应该做: {', '.join(do_list[:2])}")
            if dont_list:
                print(f"  不应该做: {', '.join(dont_list[:2])}")
    
    conn.close()

def main():
    if len(sys.argv) < 2:
        print("""
MBTI 功能冲突对话建议系统 - CLI工具
====================================

用法:
  python cli.py list                          - 列出所有MBTI类型
  python cli.py type <类型代码>                - 查询类型详情
  python cli.py pair <类型A> <类型B>           - 查询两种类型的对话建议
  python cli.py conflicts                     - 查看所有冲突类型及解决方案

示例:
  python cli.py type INTJ
  python cli.py pair INTJ ESFP
  python cli.py conflicts
        """)
        return
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT code, name_cn FROM mbti_type ORDER BY code')
        print_header("所有MBTI类型")
        for row in cursor.fetchall():
            print(f"  {row[0]} - {row[1]}")
        conn.close()
    
    elif command == 'type':
        if len(sys.argv) < 3:
            print("请提供MBTI类型代码")
            return
        print_type_info(sys.argv[2])
    
    elif command == 'pair':
        if len(sys.argv) < 4:
            print("请提供两个MBTI类型代码")
            return
        print_pair_suggestion(sys.argv[2], sys.argv[3])
    
    elif command == 'conflicts':
        print_conflict_solutions()
    
    else:
        print(f"未知命令: {command}")

if __name__ == '__main__':
    main()
