"""百花自己的学校数据解析器。仅保留课程白名单，不保留原始成绩或身份字段。"""
import math
import re

STATES = {'已通过': 'passed', '通过': 'passed', '合格': 'passed', '及格': 'passed',
          '未通过': 'failed', '未过': 'failed', '不及格': 'failed', '不合格': 'failed',
          '在修': 'enrolled', '正在修读': 'enrolled', '未修': 'not_taken',
          '已修': 'completed', '成绩待发布': 'pending', '退课': 'withdrawn'}
SCHOOL_CODES = {'1': ('enrolled', '在修'), '2': ('failed', '未过'), '3': ('not_taken', '未修'),
                '4': ('completed', '已修'), '21': ('completed', '已修')}
BLOCK = re.compile(r'password|cookie|token|session|authorization|login|学生|身份|账户|账号|姓名|手机号', re.I)


def text(value, limit=160):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()[:limit]


def credit(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace('学分', '').strip())
        return n if math.isfinite(n) and 0 <= n <= 50 else None
    except (ValueError, TypeError):
        return None


def state(row):
    # 以参考项目记录的学校显示规则为依据；不把分数>=60或“已修”猜为通过。
    if row.get('MAXCJ') == '未开放':
        return 'enrolled', '在修', 'school_code'
    if 'XDZT' in row:
        value = row['XDZT']
        code = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
        s, label = SCHOOL_CODES.get(code, ('unknown', '替代/认定或未知状态，待核对'))
        return s, label, 'school_code'
    label = text(next((row[k] for k in ('修读状态', '修读情况', '通过情况', '是否通过') if k in row), ''))
    return STATES.get(label, 'unknown'), label or '状态未知', 'school_explicit'


def course_row(row):
    name = text(row.get('KCMC') or row.get('kcmc') or row.get('课程名称'))
    n = credit(row.get('XF', row.get('xf', row.get('学分'))))
    if not name or n is None:
        return None
    s, label, origin = state(row)
    # 学校显示的修读学期，不用建议修读学期代替。
    term = text(row.get('修读学期') or row.get('学年学期') or
                ' '.join(text(row.get(k), 30) for k in ('XNMC', 'XQMMC')), 40)
    return dict(code=text(row.get('KCH') or row.get('kch') or row.get('课程号'), 80),
                name=name, credit=n, status=s, term=term,
                school_status=label[:100], status_origin=origin)


def walk_rows(payload):
    """有界遍历，仅识别课程行；身份容器不递归。"""
    seen, budget = set(), [8000]
    def walk(value, depth=0):
        if depth > 8 or budget[0] <= 0 or not isinstance(value, (dict, list)) or id(value) in seen:
            return
        seen.add(id(value)); budget[0] -= 1
        if isinstance(value, dict):
            if any(k in value for k in ('KCMC', 'kcmc', '课程名称')):
                yield value
            for k, v in list(value.items())[:120]:
                if not BLOCK.search(str(k)):
                    yield from walk(v, depth+1)
        else:
            for v in value[:2000]:
                yield from walk(v, depth+1)
    yield from walk(payload)


def courses(payload):
    result = {}
    for row in walk_rows(payload):
        item = course_row(row)
        if item:
            key = tuple(item[k] for k in ('code', 'name', 'term', 'status', 'credit'))
            result[key] = item
            if len(result) >= 2000:
                break
    return list(result.values())


def weeks(value):
    """仅接受明确的周次与单双周，拒绝缺失值和未识别格式。"""
    if isinstance(value, list):
        if value and all(type(w) is int and 1 <= w <= 40 for w in value):
            return sorted(set(value))
        return []
    raw = text(value, 120).replace('，', ',').replace('、', ',').replace('－', '-').replace('—', '-')
    if '单' in raw and '双' in raw:
        return []
    parity = 1 if '单' in raw else 0 if '双' in raw else None
    raw = re.sub(r'[周单双()（）\s]', '', raw)
    result = set()
    for part in raw.split(','):
        match = re.fullmatch(r'(\d{1,2})(?:-(\d{1,2}))?', part)
        if not match:
            return []
        a, b = int(match[1]), int(match[2] or match[1])
        if not 1 <= a <= b <= 40:
            return []
        result.update(w for w in range(a, b+1) if parity is None or w % 2 == parity)
    return sorted(result)


def periods(value):
    raw = text(value, 30).replace('第', '').replace('节', '').replace('－', '-').replace('—', '-')
    match = re.fullmatch(r'(\d{1,2})(?:-(\d{1,2}))?', raw)
    if not match:
        return None
    a, b = int(match[1]), int(match[2] or match[1])
    return (a, b) if 1 <= a <= b <= 20 else None


def meeting_row(row):
    name = text(row.get('课程名称') or row.get('kcmc'))
    day = row.get('星期', row.get('xqj'))
    day = {'星期一': 1, '周一': 1, '星期二': 2, '周二': 2, '星期三': 3, '周三': 3,
           '星期四': 4, '周四': 4, '星期五': 5, '周五': 5, '星期六': 6, '周六': 6,
           '星期日': 7, '周日': 7, '星期天': 7}.get(str(day), day)
    try:
        if isinstance(day, bool) or str(int(day)) != str(day) or not 1 <= int(day) <= 7:
            return None
        day = int(day)
    except (TypeError, ValueError):
        return None
    when = periods(row.get('节次', row.get('jcs')))
    ws = weeks(row.get('周次', row.get('zcd')))
    if not name or not when or not ws:
        return None
    return dict(code=text(row.get('课程号') or row.get('kch'), 80), name=name,
                section_id=text(row.get('教学班') or row.get('jxbmc'), 80), day=day,
                start=when[0], end=when[1], weeks=ws,
                room=text(row.get('教室') or row.get('cdmc'), 100),
                campus=text(row.get('校区') or row.get('xqmc'), 60))


def meetings(payload):
    result = {}
    for row in walk_rows(payload):
        item = meeting_row(row)
        if item:
            result[(item['code'], item['name'], item['section_id'], item['day'], item['start'],
                    item['end'], tuple(item['weeks']), item['room'])] = item
            if len(result) >= 1000:
                break
    return list(result.values())
