# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
import sqlite3
import json
import os

app = Flask(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(PROJECT_DIR, 'database', 'mbti.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'MBTI对话建议系统API运行中'})

@app.route('/api/mbti/types', methods=['GET'])
def get_all_mbti_types():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM mbti_type')
    results = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'code': 0, 'data': results})

@app.route('/api/mbti/type/<code>', methods=['GET'])
def get_mbti_type(code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM mbti_type WHERE code = ?', (code.upper(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({'code': 0, 'data': row_to_dict(row)})
    return jsonify({'code': 404, 'message': 'MBTI类型不存在'}), 404

@app.route('/api/mbti/<code>/functions', methods=['GET'])
def get_mbti_functions(code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT fs.position, fs.is_shadow, f.code, f.name_cn, f.category, f.attitude, f.description
        FROM mbti_function_stack fs
        JOIN mbti_function f ON fs.function_code = f.code
        WHERE fs.mbti_code = ?
        ORDER BY fs.position
    ''', (code.upper(),))
    results = []
    for row in cursor.fetchall():
        results.append({
            'position': row[0],
            'is_shadow': bool(row[1]),
            'function_code': row[2],
            'name_cn': row[3],
            'category': row[4],
            'attitude': row[5],
            'description': row[6]
        })
    conn.close()
    return jsonify({'code': 0, 'data': results})

@app.route('/api/functions', methods=['GET'])
def get_all_functions():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM mbti_function')
    results = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'code': 0, 'data': results})

@app.route('/api/conflicts', methods=['GET'])
def get_all_conflicts():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM function_conflict_type')
    results = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'code': 0, 'data': results})

@app.route('/api/conflict/<conflict_code>', methods=['GET'])
def get_conflict_solution(conflict_code):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM function_conflict_type WHERE conflict_code = ?', (conflict_code,))
    conflict = row_to_dict(cursor.fetchone())
    
    if conflict:
        cursor.execute('SELECT * FROM conflict_solution WHERE conflict_code = ?', (conflict_code,))
        solution = row_to_dict(cursor.fetchone())
        if solution:
            solution['do_list'] = json.loads(solution['do_list']) if solution['do_list'] else []
            solution['dont_list'] = json.loads(solution['dont_list']) if solution['dont_list'] else []
        conn.close()
        return jsonify({'code': 0, 'data': {'conflict': conflict, 'solution': solution}})
    conn.close()
    return jsonify({'code': 404, 'message': '冲突类型不存在'}), 404

@app.route('/api/conflicts/dimension/<dimension>', methods=['GET'])
def get_conflicts_by_dimension(dimension):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM function_conflict_type WHERE dimension = ?', (dimension,))
    results = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'code': 0, 'data': results})

@app.route('/api/pair/suggestion', methods=['GET'])
def get_pair_suggestion():
    mbti_a = request.args.get('a', '').upper()
    mbti_b = request.args.get('b', '').upper()
    
    if not mbti_a or not mbti_b:
        return jsonify({'code': 400, 'message': '请提供两个MBTI类型参数: a和b'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM mbti_pair_suggestion 
        WHERE (mbti_a = ? AND mbti_b = ?) OR (mbti_a = ? AND mbti_b = ?)
    ''', (mbti_a, mbti_b, mbti_b, mbti_a))
    
    row = cursor.fetchone()
    if row:
        result = row_to_dict(row)
        result['things_to_do'] = json.loads(result['things_to_do']) if result['things_to_do'] else []
        result['things_to_avoid'] = json.loads(result['things_to_avoid']) if result['things_to_avoid'] else []
        conn.close()
        return jsonify({'code': 0, 'data': result})
    
    result = generate_dynamic_suggestion(cursor, mbti_a, mbti_b)
    conn.close()
    return jsonify({'code': 0, 'data': result})

def generate_dynamic_suggestion(cursor, mbti_a, mbti_b):
    cursor.execute('SELECT * FROM mbti_type WHERE code = ?', (mbti_a,))
    type_a = row_to_dict(cursor.fetchone())
    cursor.execute('SELECT * FROM mbti_type WHERE code = ?', (mbti_b,))
    type_b = row_to_dict(cursor.fetchone())
    
    if not type_a or not type_b:
        return {'error': 'MBTI类型不存在'}
    
    conflicts = []
    if type_a['e_i'] != type_b['e_i']:
        conflicts.append('E vs I')
    if type_a['s_n'] != type_b['s_n']:
        conflicts.append('S vs N')
    if type_a['t_f'] != type_b['t_f']:
        conflicts.append('T vs F')
    if type_a['j_p'] != type_b['j_p']:
        conflicts.append('J vs P')
    
    score = 0
    if type_a['e_i'] == type_b['e_i']: score += 1
    if type_a['s_n'] == type_b['s_n']: score += 1
    if type_a['t_f'] == type_b['t_f']: score += 1
    if type_a['j_p'] == type_b['j_p']: score += 1
    
    compatibility = 'high' if score >= 3 else ('medium' if score >= 2 else 'low')
    
    tips = []
    if type_a['e_i'] != type_b['e_i']:
        tips.append('尊重对方的社交节奏')
    if type_a['s_n'] != type_b['s_n']:
        tips.append('互相举例说明自己的观点')
    if type_a['t_f'] != type_b['t_f']:
        tips.append('尊重对方的决策方式')
    if type_a['j_p'] != type_b['j_p']:
        tips.append('找到计划与灵活的平衡点')
    
    return {
        'mbti_a': mbti_a,
        'mbti_b': mbti_b,
        'compatibility': compatibility,
        'main_conflict': ' | '.join(conflicts) if conflicts else '无明显冲突',
        'communication_tips': '；'.join(tips) if tips else '沟通顺畅',
        'recommended_topics': '共同兴趣话题',
        'things_to_do': ['尊重对方的性格特点', '保持开放沟通'],
        'things_to_avoid': ['不要强制改变对方', '不要嘲笑对方的思维方式']
    }

@app.route('/api/pair/conflicts', methods=['GET'])
def get_pair_conflicts():
    mbti_a = request.args.get('a', '').upper()
    mbti_b = request.args.get('b', '').upper()
    
    if not mbti_a or not mbti_b:
        return jsonify({'code': 400, 'message': '请提供两个MBTI类型参数: a和b'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT e_i, s_n, t_f, j_p FROM mbti_type WHERE code = ?', (mbti_a,))
    type_a = row_to_dict(cursor.fetchone())
    cursor.execute('SELECT e_i, s_n, t_f, j_p FROM mbti_type WHERE code = ?', (mbti_b,))
    type_b = row_to_dict(cursor.fetchone())
    
    if not type_a or not type_b:
        conn.close()
        return jsonify({'code': 404, 'message': 'MBTI类型不存在'}), 404
    
    conflicts = []
    if type_a['e_i'] != type_b['e_i']:
        cursor.execute('SELECT * FROM function_conflict_type WHERE conflict_code = ?', ('E_vs_I',))
        conflicts.append(row_to_dict(cursor.fetchone()))
    if type_a['s_n'] != type_b['s_n']:
        cursor.execute('SELECT * FROM function_conflict_type WHERE conflict_code = ?', ('S_vs_N',))
        conflicts.append(row_to_dict(cursor.fetchone()))
    if type_a['t_f'] != type_b['t_f']:
        cursor.execute('SELECT * FROM function_conflict_type WHERE conflict_code = ?', ('T_vs_F',))
        conflicts.append(row_to_dict(cursor.fetchone()))
    if type_a['j_p'] != type_b['j_p']:
        cursor.execute('SELECT * FROM function_conflict_type WHERE conflict_code = ?', ('J_vs_P',))
        conflicts.append(row_to_dict(cursor.fetchone()))
    
    result = []
    for conflict in conflicts:
        if conflict:
            cursor.execute('SELECT * FROM conflict_solution WHERE conflict_code = ?', (conflict['conflict_code'],))
            solution = row_to_dict(cursor.fetchone())
            if solution:
                solution['do_list'] = json.loads(solution['do_list']) if solution['do_list'] else []
                solution['dont_list'] = json.loads(solution['dont_list']) if solution['dont_list'] else []
            result.append({'conflict': conflict, 'solution': solution})
    
    conn.close()
    return jsonify({'code': 0, 'data': result})

if __name__ == '__main__':
    print("启动MBTI对话建议系统API...")
    print("访问 http://localhost:5001/api/health 检查服务状态")
    app.run(host='0.0.0.0', port=5001, debug=True)
