"""统一实际修读状态。课程序列I/II保留，未提供的数据不推测已通过。"""
import re
import unicodedata


def normalize_name(name):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', name or '')).lower()


def progress(plan, snapshot=None):
    courses = plan['courses']
    by_id = {c['code']: c for c in courses}
    mapped, unmatched = {}, []
    groups = {}
    priority = {'passed': 5, 'enrolled': 4, 'pending': 3, 'failed': 2, 'withdrawn': 1,
                'completed': 0, 'unknown': 0, 'not_taken': 0}
    for r in (snapshot or {}).get('records', []):
        key = (r.get('code', ''), normalize_name(r['name']))
        if key not in groups or priority[r['status']] > priority[groups[key]['status']]:
            groups[key] = r
    for r in groups.values():
        exact = [c for c in courses if c.get('original_code', c['code']) == r.get('code')
                 and normalize_name(c['name']) == normalize_name(r['name'])]
        if not exact:
            exact = [c for c in courses if normalize_name(c['name']) == normalize_name(r['name'])]
        if len(exact) == 1:
            code = exact[0]['code']
            if code not in mapped or priority[r['status']] > priority[mapped[code]['status']]:
                mapped[code] = r
        else:
            unmatched.append(r)
    passed = {code for code, r in mapped.items() if r['status'] == 'passed'}
    enrolled = {code for code, r in mapped.items() if r['status'] == 'enrolled'}
    failed = {code for code, r in mapped.items() if r['status'] == 'failed'}
    sections = {}
    for code in passed:
        sections[by_id[code]['section']] = sections.get(by_id[code]['section'], 0)+mapped[code]['credit']
    warnings = []
    if not snapshot:
        warnings.append('尚未同步修读记录，已获学分未知；未将方案中的历史课程当作已通过')
    elif not snapshot.get('history_complete'):
        warnings.append('修读记录尚不完整；当前学分仅为已导入部分')
    if snapshot and any(r['status'] in ('completed', 'unknown') for r in snapshot.get('records', [])):
        warnings.append('存在已修但通过情况待核对或未知状态，未计入已通过学分')
    if snapshot and any(r.get('status_origin') == 'student_review' for r in snapshot.get('records', [])):
        warnings.append('部分修读状态由本人核对后修改，请以学校最终认定为准')
    if unmatched:
        warnings.append(f'{len(unmatched)}条课程记录无法唯一匹配培养方案，暂不计入方案模块完成度')
    mismatch = [by_id[code]['name'] for code in mapped if mapped[code]['credit'] != by_id[code]['credit']]
    if mismatch:
        warnings.append('部分课程学分与方案不同，需核对版本：'+'、'.join(mismatch[:5]))
    if not plan.get('version_matches', True):
        warnings.append('当前只有2025版培养方案，与选择的入学年级不一致；仅作参考，不能判定选课资格')
    if not plan.get('complete', False):
        warnings.append('课程库未覆盖完整毕业环节，不能据此判定毕业要求全部满足')
    return {'passed': passed, 'enrolled': enrolled, 'failed': failed, 'mapped': mapped,
            'unmatched': unmatched, 'sections': sections,
            'done_credit': round(sum(mapped[k]['credit'] for k in passed), 1),
            'earned_credit_all': round(sum(mapped[k]['credit'] for k in passed) + sum(r['credit'] for r in unmatched if r['status'] == 'passed'), 1),
            'enrolled_credit': round(sum(mapped[k]['credit'] for k in enrolled), 1),
            'known': snapshot is not None, 'complete': bool(snapshot and snapshot.get('history_complete')),
            'warnings': warnings}


def public_progress(state):
    return {k: v for k, v in state.items() if k not in ('passed', 'enrolled', 'failed', 'mapped')}
