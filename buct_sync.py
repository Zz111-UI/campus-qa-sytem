"""百花独立实现：短时登录、学校页面被动读取、个人任务隔离与预览。

参考的是用户提供项目的机制和适配证据，不调用或依赖该项目。
服务端独立浏览器会话；用户在网页内完成学校验证，不导出Cookie。
"""
import copy
import importlib.util
import json
import os
import queue
import ipaddress
import secrets
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urljoin
import school_data

SCHOOL = 'jwglxt.buct.edu.cn'
LOGIN_HOSTS = {SCHOOL, 'portal.buct.edu.cn', 'experimental-auth-endpoint.buct.edu.cn'}
CAPTCHA_HOSTS = {'t.captcha.qq.com', 'ssl.captcha.qq.com', 'captcha.gtimg.com', 'turing.captcha.qcloud.com'}
ACTIVE = {'starting', 'login_required', 'collecting'}
TTL = 900


def browser_options():
    channel = os.getenv('BAIHUA_BROWSER_CHANNEL', '')
    edge = any(Path(path).is_file() for path in (
        'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
        'C:/Program Files/Microsoft/Edge/Application/msedge.exe'))
    if not channel and os.name == 'nt' and edge:
        channel = 'msedge'
    if channel not in ('', 'msedge', 'chrome'):
        raise ValueError('unsupported browser channel')
    return {'channel': channel} if channel else {}


def school_dns_options():
    """仅网站管理员显式配置时，为白名单域名使用独立DNS；TLS校验始终启用。"""
    address = os.getenv('BAIHUA_SCHOOL_DNS', '').strip()
    if not address:
        return {}
    if not ipaddress.ip_address(address).is_global:
        raise ValueError('DNS server must be public')
    import dns.resolver
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [address]; resolver.timeout = 2; resolver.lifetime = 4
    rules = []
    for host in sorted(LOGIN_HOSTS | CAPTCHA_HOSTS):
        try:
            result = resolver.resolve(host, 'A')
            ip = str(next(iter(result)))
            if ipaddress.ip_address(ip).is_global:
                rules.append(f'MAP {host} {ip}')
        except (dns.exception.DNSException, StopIteration):
            continue
    return {'args': ['--host-resolver-rules='+', '.join(rules)]} if rules else {}


def trusted(url, hosts=LOGIN_HOSTS):
    try:
        u = urlsplit(url)
        if u.scheme != 'https' or u.hostname not in hosts or u.port not in (None, 443) or u.username or u.password:
            return False
        services = parse_qs(u.query).get('service', [])
        return len(services) <= 1 and all(
            urlsplit(v).scheme == 'https' and urlsplit(v).hostname == SCHOOL
            and urlsplit(v).path == '/sso/jziotlogin' and urlsplit(v).port in (None, 443)
            and not urlsplit(v).username and not urlsplit(v).password for v in services)
    except (ValueError, TypeError):
        return False


def runtime_status():
    if os.getenv('EDUCATION_BROWSER_SYNC', '1') != '1':
        return False, '网站的教务同步服务暂未开启，请联系网站管理员'
    if importlib.util.find_spec('playwright') is None:
        return False, '网站的教务同步服务尚未配置完成，请联系网站管理员；你无需安装软件'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            options = browser_options()
            if options.get('channel') == 'msedge':
                available = any(Path(path).is_file() for path in ('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'))
            elif options.get('channel') == 'chrome':
                available = any(Path(path).is_file() for path in ('C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'))
            else:
                available = Path(p.chromium.executable_path).is_file()
        return available, '网页教务同步服务已就绪，学校验证可在网页中完成' if available else '网站服务器的教务连接环境未就绪，请联系管理员；你无需安装软件'
    except Exception:
        return False, '网站教务连接暂不可用，请稍后重试或联系管理员'


def allowed_request(url, method):
    if method in ('GET', 'HEAD'):
        return trusted(url) or trusted(url, CAPTCHA_HOSTS)
    if method not in ('POST', 'OPTIONS') or not trusted(url):
        return False
    u = urlsplit(url)
    if u.hostname != SCHOOL:
        return True  # 官方认证域名，表单目标另行核验。
    # 正方查询页面的请求也使用POST；仅放行查询模块中的cx动作与登录。
    path = u.path
    return (path.startswith('/jwglxt/xtgl/login_') or path == '/sso/jziotlogin'
            or path.startswith('/jwglxt/xtgl/index_cx')
            or path.startswith(('/jwglxt/xsxy/xsxyqk_cx', '/xsxy/xsxyqk_cx'))
            or any(path.startswith('/jwglxt/'+module+'/') for module in ('xjgl/xyqk', 'kbcx', 'cjcx'))
            and ('_cx' in path or path.rsplit('/', 1)[-1].startswith('cx')))


def query_source(url):
    """按实际学校查询模块识别响应，不依赖自动菜单点击是否成功。"""
    if not trusted(url, {SCHOOL}):
        return None
    path = urlsplit(url).path
    if path.startswith(('/jwglxt/xjgl/xyqk/', '/jwglxt/xsxy/xsxyqk_cx', '/xsxy/xsxyqk_cx')):
        return 'academic'
    if path.startswith('/jwglxt/kbcx/'):
        return 'timetable'
    return None


def try_login(page, student_id, password):
    """仅填写参考证据中确认的portal表单；不猜其他域名上的表单。"""
    if not trusted(page.url):
        return 'manual'
    for frame in page.frames:
        u = urlsplit(frame.url)
        if not trusted(frame.url) or u.hostname != 'portal.buct.edu.cn' or u.path != '/normal/login-normal.html':
            continue
        account = frame.locator('input[name="username"][type="text"]:visible')
        secret = frame.locator('input[name="password"][type="password"]:visible')
        button = frame.locator('button.btn-submit:visible')
        if any(x.count() != 1 for x in (account, secret, button)):
            continue
        for element in (account, secret, button):
            targets = element.evaluate("e => [e.form?.getAttribute('action'), e.getAttribute('formaction')]")
            if any(t and not trusted(urljoin(frame.url, t)) for t in targets):
                return 'manual'
        if frame.locator('input[autocomplete="one-time-code"]:visible, #tcaptcha_iframe_dy:visible').count():
            return 'manual'
        account.fill(student_id, timeout=3000)
        if not trusted(page.url) or not trusted(frame.url):
            return 'manual'
        secret.fill(password, timeout=3000)
        try:
            for element in (account, secret, button):
                targets = element.evaluate("e => [e.form?.getAttribute('action'), e.getAttribute('formaction')]")
                if any(t and not trusted(urljoin(frame.url, t)) for t in targets):
                    return 'manual'
            if not trusted(page.url) or not trusted(frame.url):
                return 'manual'
            button.click(timeout=4000)
        finally:
            # 遗留表单值也清空；不重试密码提交。
            try:
                secret.fill('', timeout=500)
            except Exception:
                pass
        return 'submitted'
    return 'waiting'


def fill_identifiable_login(page, student_id, password):
    """识别官方页面实际提供的唯一账户/密码输入，不构造认证接口或代过验证。"""
    if not trusted(page.url):
        return False
    for frame in page.frames:
        if not trusted(frame.url):
            continue
        account = frame.locator('input[autocomplete="username"]:visible, input[name="username"]:visible, '
                                'input[name="account"]:visible, input[name="userName"]:visible, input[id="username"]:visible')
        secret = frame.locator('input[type="password"]:visible')
        if account.count() != 1 or secret.count() != 1:
            continue
        # 两个输入需属于同一官方表单；无form的JS登录页面允许表单目标为空。
        info = secret.evaluate("e => ({action:e.form?.getAttribute('action'), method:e.form?.method})")
        other = account.evaluate("e => ({action:e.form?.getAttribute('action'), method:e.form?.method})")
        if info != other or info.get('action') and not trusted(urljoin(frame.url, info['action'])):
            continue
        if info.get('method') and info['method'].lower() != 'post':
            continue  # 不把密码提交到GET查询串。
        account.fill(student_id, timeout=2000)
        if not trusted(page.url) or not trusted(frame.url):
            return False
        secret.fill(password, timeout=2000)
        return True  # 学校按钮由用户点击，支持学校自身JS加密及验证码流程。
    return False


# 在浏览器端先选列，避免把姓名/学号/成绩表整页传到应用。
READ_TABLES = r"""() => {
 const allowed = new Set(['课程名称','课程号','学分','修读状态','修读情况','通过情况','是否通过','修读学期','学年学期','星期','节次','周次','教室','校区','教学班']);
 const visible = e => !!e.getClientRects().length;
 const clean = e => (e.innerText || '').replace(/\s+/g,' ').trim().slice(0,160);
 let out=[];
 // 当前学校脚本明确创建这些课程单元格；不依赖表头和成绩列的位置。
 for(const r of [...document.querySelectorAll('tr[kch_id]')].slice(0,2000)) {
  const name=r.querySelector('td[name="kcmc"]'), credit=r.querySelector('td[name="xf"]');
  if(!name || !credit)continue;
  const row={KCMC:clean(name),XF:clean(credit),XDZT:credit.getAttribute('xdzt')};
  if(r.cells[1])row.XNMC=clean(r.cells[1]); if(r.cells[2])row.XQMMC=clean(r.cells[2]);
  const code=r.cells[3]; if(code && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(clean(code)))row.KCH=clean(code);
  const displayed=[...r.querySelectorAll('[title]')].map(e=>e.getAttribute('title'));
  if(displayed.includes('在修'))row.MAXCJ='未开放'; // 学校显示优先级覆盖尚未开放的成绩。
  if(row.KCMC)out.push(row);
 }
 for (const t of [...document.querySelectorAll('table')].filter(visible).slice(0,40)) {
  const grid=t.closest('.ui-jqgrid,.layui-table-view,.el-table');
  let heads=[...t.querySelectorAll('thead tr:last-child th,thead tr:last-child td')].map(clean);
  if(!heads.length && grid) heads=[...grid.querySelectorAll('thead tr:last-child th')].map(clean);
  if(!heads.length) heads=[...(t.rows[0]?.cells || [])].map(clean);
  heads=heads.map(h=>h==='课程代码'||h==='课程编号'?'课程号':h==='课程名'?'课程名称':h==='上课地点'?'教室':h==='星期几'?'星期':h==='学分数'?'学分':h);
  if(!heads.includes('课程名称')) continue;
  for(const r of [...t.rows].filter(visible).slice(0,2001)) {
   if(r.parentElement?.tagName==='THEAD') continue;
   if(r.hasAttribute('kch_id') && r.querySelector('td[name="kcmc"]') && r.querySelector('td[name="xf"]'))continue;
   let row={}; [...r.cells].slice(0,40).forEach((c,i)=>{if(allowed.has(heads[i])) row[heads[i]]=clean(c);});
   const states=new Set(['已修','在修','未过','未修','已通过','未通过','合格','不及格','退课','成绩待发布']);
   const icons=[...r.querySelectorAll('[title],[alt]')].map(e=>e.getAttribute('title')||e.getAttribute('alt')).filter(t=>states.has(t));
   if(!row['修读状态'] && new Set(icons).size===1) row['修读状态']=icons[0];
   if(row['课程名称'] && row['课程名称']!=='课程名称') out.push(row);
  }
 }
 return out.slice(0,2000);
}"""
READ_IDENTITY = r"""() => {
 const text=(document.body?.innerText || '').slice(0,200000);
 const matches=[...text.matchAll(/(?:学号|学生号)\s*[:：]\s*(\d{6,20})(?!\d)/g)];
 return [...new Set(matches.map(m=>m[1]))].slice(0,5);
}"""


@dataclass(repr=False)
class Credentials:
    student_id: str | None = field(repr=False)
    password: str | None = field(repr=False)
    def clear(self):
        self.student_id = self.password = None


class SyncJobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}
        self.stop_events = {}
        self.finish_events = {}
        self.secrets = {}
        self.remote = {}

    def prune(self):
        now = time.monotonic()
        for key, job in list(self.jobs.items()):
            if now - job['_created'] > TTL:
                self.stop_events[key].set()
                self.secrets.get(key, Credentials(None, None)).clear()
                self.clear_remote(key)
                job.update(_expired=True, status='cancelled', result=None)
                if job.get('_closed'):
                    self.jobs.pop(key); self.stop_events.pop(key); self.finish_events.pop(key)
                    self.remote.pop(key, None)

    def start(self, owner, term, password=None):
        with self.lock:
            self.prune()
            for j in self.jobs.values():
                if j['_owner'] == owner and j['status'] in ACTIVE:
                    raise ValueError('已有采集任务，请先完成或取消')
            if sum(not j.get('_closed') for j in self.jobs.values()) >= 2:
                raise ValueError('浏览器任务繁忙，请稍后再试')
            completed = [k for k, j in self.jobs.items() if j.get('_closed')]
            for old in completed[:-19]:
                self.jobs.pop(old); self.stop_events.pop(old); self.finish_events.pop(old)
                self.remote.pop(old, None)
            key = secrets.token_urlsafe(24)
            self.jobs[key] = dict(id=key, status='starting', message='正在连接学校，验证窗口将在网页内显示',
                record_count=0, meeting_count=0, result=None, identity_verified=False,
                _owner=owner, _term=term, _created=time.monotonic(), _closed=False)
            self.stop_events[key] = threading.Event(); self.finish_events[key] = threading.Event()
            box = Credentials(owner, password)
            self.secrets[key] = box
            self.remote[key] = {'queue': queue.Queue(maxsize=12), 'image': None, 'revision': 0, 'actions': 0, 'page': None, 'versions': {}}
            threading.Thread(target=self._run, args=(key, box), name='baihua-school-sync', daemon=True).start()
            return key

    def get(self, key, owner):
        with self.lock:
            self.prune()
            j = self.jobs.get(key)
            if not j or j['_owner'] != owner or j.get('_expired'):
                return None
            return copy.deepcopy({k: v for k, v in j.items() if not k.startswith('_')})

    def update(self, key, **values):
        with self.lock:
            if key in self.jobs:
                if self.jobs[key]['status'] == 'cancelled' and values.get('status') != 'cancelled':
                    return
                self.jobs[key].update(values)

    def clear_remote(self, key):
        """图片和交互输入仅暂存在内存，终止时及时释放。"""
        remote = self.remote.get(key)
        if remote:
            remote.update(image=None, page=None, versions={})
            while True:
                try:
                    command = remote['queue'].get_nowait()
                    command.clear()
                except queue.Empty:
                    break

    def screen(self, key, owner):
        with self.lock:
            job = self.get(key, owner)
            if not job or job['status'] not in ACTIVE:
                return None
            remote = self.remote.get(key)
            if not remote or not remote['image']:
                return None
            return remote['image'], remote['revision']

    def enqueue(self, key, owner, command):
        with self.lock:
            job = self.get(key, owner)
            remote = self.remote.get(key)
            if not job or job['status'] not in ACTIVE or not remote or not remote['image']:
                raise ValueError('学校验证窗口尚未就绪或已关闭')
            binding = remote['versions'].get(command['revision'])
            if not binding or binding != (remote['page'], remote['page'].url):
                raise ValueError('学校页面已更新，请等待新画面后重试')
            if remote['actions'] >= 600:
                raise ValueError('本次交互次数已达上限，请取消后重试')
            try:
                remote['queue'].put_nowait(dict(command, _page=binding[0], _url=binding[1]))
            except queue.Full:
                raise ValueError('学校页面正在处理输入，请稍后再试') from None
            remote['actions'] += 1

    def interact(self, key, page):
        """只在任务自己的浏览器线程执行交互，不向客户端开放任意网址或脚本。"""
        with self.lock:
            remote = self.remote.get(key)
            if not remote:
                return
        for _ in range(12):
            try:
                command = remote['queue'].get_nowait()
            except queue.Empty:
                break
            try:
                if (self.stop_events[key].is_set() or page is not command.pop('_page') or page.url != command.pop('_url')
                        or not trusted(page.url)):
                    continue
                kind = command['kind']
                if kind == 'click':
                    page.mouse.click(command['x'], command['y'])
                elif kind == 'drag':
                    page.mouse.move(command['x'], command['y']); page.mouse.down()
                    try:
                        page.mouse.move(command['end_x'], command['end_y'], steps=12)
                    finally:
                        page.mouse.up()
                elif kind == 'key':
                    page.keyboard.press(command['key'])
                elif kind == 'text':
                    # 登录输入只发送到学校官方页面中的编辑框。
                    frames = [f for f in page.frames if trusted(f.url)]
                    for frame in frames:
                        active = frame.locator('input:focus, textarea:focus')
                        if active.count() == 1 and active.is_visible():
                            active.fill(command['text'], timeout=2000)
                            break
                elif kind == 'scroll':
                    page.mouse.wheel(0, command['delta'])
            except Exception:
                self.update(key, message='学校页面已变化，请刷新画面并再次输入；未保存输入内容')
            finally:
                command.clear()
        if self.stop_events[key].is_set() or not trusted(page.url):
            return
        try:
            image = page.screenshot(type='jpeg', quality=65, timeout=1500)
            if len(image) <= 2*1024*1024:
                with self.lock:
                    if not self.stop_events[key].is_set():
                        # 相同画面不改变版本，防止用户正常点击被轮询作废。
                        if remote['image'] != image or remote['page'] is not page:
                            remote.update(image=image, revision=remote['revision']+1, page=page)
                            remote['versions'][remote['revision']] = (page, page.url)
                            for old in sorted(remote['versions'])[:-30]:
                                remote['versions'].pop(old)
        except Exception:
            pass

    def cancel(self, key, owner):
        with self.lock:
            if self.get(key, owner) is None:
                return False
            self.stop_events[key].set()
            self.secrets.get(key, Credentials(None, None)).clear()
            self.clear_remote(key)
            self.update(key, status='cancelled', message='已取消采集，等待关闭学校会话', result=None)
            return True

    def finish(self, key, owner):
        with self.lock:
            if self.get(key, owner) is None:
                return False
            self.finish_events[key].set()
            return True

    def discard(self, key, owner):
        self.cancel(key, owner)

    def shutdown(self):
        with self.lock:
            for key in self.jobs:
                self.stop_events[key].set()
            for box in self.secrets.values():
                box.clear()
            for key in self.remote:
                self.clear_remote(key)

    @staticmethod
    def click_text(page, labels):
        for frame in page.frames:
            if not trusted(frame.url, {SCHOOL}):
                continue
            for label in labels:
                matches = frame.get_by_text(label, exact=True)
                for node in matches.all()[:5]:
                    if node.is_visible():
                        node.click(timeout=1200)
                        return True
        return False

    def _run(self, key, box):
        browser = context = None
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p, ExitStack() as cleanup:
                def close(resource):
                    try:
                        resource.close()
                    except Exception:
                        pass
                browser = p.chromium.launch(headless=True, timeout=15000, **browser_options(), **school_dns_options())
                cleanup.callback(close, browser)
                context = browser.new_context(accept_downloads=False, viewport={'width': 1000, 'height': 700})
                cleanup.callback(close, context)
                context.set_default_timeout(1500)
                context.set_default_navigation_timeout(12000)
                def guard(route):
                    request = route.request
                    allowed = allowed_request(request.url, request.method)
                    route.continue_() if allowed else route.abort()
                context.route('**/*', guard)
                page = context.new_page()
                records, timetable, identity_ids = {}, {}, set()
                phase = 'login'; request_phases = {}
                def requested(request):
                    if len(request_phases) < 1000:
                        request_phases[request] = query_source(request.url)
                def received(request):
                    source = request_phases.pop(request, None)
                    if source not in ('academic', 'timetable') or self.stop_events[key].is_set():
                        return
                    try:
                        response = request.response()
                        if not response or query_source(response.url) != source or response.status != 200:
                            return
                        size = response.headers.get('content-length', '')
                        if size.isdigit() and int(size) > 2*1024*1024:
                            return
                        body = response.body()
                        if len(body) > 2*1024*1024:
                            return
                        # 某些学校查询返回JSON却标记为text/plain；仅在确认查询模块内解析。
                        if not body.lstrip().startswith((b'{', b'[')):
                            return
                        payload = json.loads(body)
                        for row in school_data.walk_rows(payload):
                            for field in ('XH', 'xh'):
                                if field in row and str(row[field]).isdigit():
                                    identity_ids.add(str(row[field]))
                        add(payload, source)
                    except Exception:
                        pass
                def add(payload, source):
                    if source == 'academic':
                        for row in school_data.courses(payload):
                            signature = tuple(row[k] for k in ('code', 'name', 'term', 'status', 'credit'))
                            if len(records) < 2000:
                                records[signature] = row
                    else:
                        for row in school_data.meetings(payload):
                            signature = json.dumps(row, sort_keys=True)
                            if len(timetable) < 1000:
                                timetable[signature] = row
                context.on('request', requested)
                context.on('requestfinished', received)
                self.update(key, status='login_required', message='请在网页内的学校窗口完成登录和验证；只读取课程查询页面')
                page.goto('https://jwglxt.buct.edu.cn/', wait_until='domcontentloaded')
                started = time.monotonic(); phase_started = started; last_change = started
                last_counts = (0, 0); menu_opened = False; entered = False
                while time.monotonic() - started < 360:
                    if self.stop_events[key].is_set():
                        return
                    if self.finish_events[key].is_set():
                        break
                    pages = [x for x in context.pages if not x.is_closed()]
                    if not pages:
                        raise ValueError('closed')
                    page = next((x for x in reversed(pages) if trusted(x.url, {SCHOOL})), pages[-1])
                    page.wait_for_timeout(350)
                    self.interact(key, page)
                    if box.password:
                        outcome = 'waiting'
                        for candidate in reversed(pages[-6:]):
                            outcome = try_login(candidate, box.student_id, box.password)
                            if outcome in ('waiting', 'manual') and fill_identifiable_login(candidate, box.student_id, box.password):
                                outcome = 'filled'
                            if outcome != 'waiting':
                                break
                        if outcome != 'waiting' or time.monotonic() - started > 60:
                            box.clear()
                            self.update(key, message='账号密码已填入学校页面，请在下方学校窗口点击学校登录按钮，并自行完成验证' if outcome == 'filled' else '登录信息已释放。若学校表单未自动填写，请在下方学校窗口点击输入框，使用网页输入栏填写并自行完成验证')
                    if not trusted(page.url, {SCHOOL}):
                        continue
                    detected = {query_source(f.url) for f in page.frames if trusted(f.url, {SCHOOL})}
                    # 手动导航或学校预先加载查询页时，也必须读取，不能永远等菜单点击。
                    already_open = (phase in detected or (phase == 'login' and 'academic' in detected)
                                    or (phase == 'login' and records))
                    if already_open and not entered:
                        if phase == 'login':phase = 'academic'
                        entered = True; phase_started = last_change = time.monotonic(); box.clear()
                        self.update(key,status='collecting',message='已识别实际查询页，正在读取课程与课表；请核对查询条件和分页')
                    elif phase == 'login' and 'timetable' in detected:
                        phase = 'timetable'; entered = True; phase_started = time.monotonic(); box.clear()
                        self.update(key,status='collecting',message='已识别个人课表查询页，正在读取；请核对学期和周次')
                    if not menu_opened:
                        menu_opened = self.click_text(page, ['信息查询'])
                    if not entered:
                        old_phase = phase
                        phase = 'academic' if phase == 'login' else phase
                        labels = ['学生学业情况查询', '学生学业信息情况查询'] if phase == 'academic' else ['学生课表查询', '个人课表查询']
                        entered = self.click_text(page, labels)
                        if not entered:
                            phase = old_phase
                            if phase == 'timetable' and time.monotonic() - phase_started > 45:
                                break
                            continue
                        box.clear(); phase_started = last_change = time.monotonic()
                        self.update(key, status='collecting', message='读取学业查询。请检查筛选条件和分页；也可点击完成读取进行预览' if phase == 'academic' else '读取个人课表。请在学校窗口核对学期、周次和分页后完成读取')
                    for frame in page.frames:
                        if trusted(frame.url, {SCHOOL}):
                            identity_ids.update(frame.evaluate(READ_IDENTITY))
                            add(frame.evaluate(READ_TABLES), phase)
                    owner = self.jobs[key]['_owner']
                    if identity_ids and identity_ids != {owner}:
                        self.update(key, status='failed', message='学校页面学号与百花账号不一致，已停止；未保存任何采集数据', result=None)
                        return
                    counts = (len(records), len(timetable))
                    if counts != last_counts:
                        last_counts = counts; last_change = time.monotonic()
                    self.update(key, record_count=counts[0], meeting_count=counts[1], identity_verified=identity_ids == {owner})
                    if self.finish_events[key].is_set():
                        break
                    # 页面稳定只表示当前已加载部分，不据此标为完整。
                    if phase == 'academic' and records and time.monotonic() - last_change > 4:
                        phase = 'timetable'; entered = False; menu_opened = False
                        phase_started = time.monotonic()
                    elif phase == 'timetable' and entered and time.monotonic() - phase_started > 45:
                        break
                if self.stop_events[key].is_set():
                    return
                if not records and not timetable:
                    self.update(key, status='failed', error_code='query_not_recognized', message='已连接学校，但未读取到课程记录。请在学校窗口打开“信息查询 → 学生学业情况查询”或“个人课表查询”，选择学期并点击查询；若已有结果仍为0，说明当前页面格式尚未适配')
                    return
                snapshot = dict(term=self.jobs[key]['_term'], records=list(records.values()), meetings=list(timetable.values()),
                                offerings=[], history_complete=False, timetable_complete=False, offerings_complete=False)
                self.update(key, status='needs_review', message='已读取学校当前加载的数据，尚未保存。请核对状态、学期与完整性后确认',
                            result=snapshot, identity_verified=identity_ids == {self.jobs[key]['_owner']})
        except Exception as error:
            if not self.stop_events[key].is_set():
                # 只输出固定错误分类，不返回可能包含个人信息的原始异常。
                category = 'school_unavailable'
                message = '学校连接未完成，可能是认证页面变化或服务暂不可用，请稍后重试或联系管理员'
                if 'ERR_NAME_NOT_RESOLVED' in str(error):
                    category = 'school_dns_unavailable'
                    message = '网站服务器暂时无法解析学校教务或认证域名，请管理员检查服务器网络；你无需安装软件'
                elif 'Timeout' in type(error).__name__:
                    category = 'school_timeout'
                    message = '学校登录页面连接超时，请稍后重试；如持续出现，请管理员检查服务器到学校的网络'
                self.update(key, status='failed', message=message, error_code=category, result=None)
        finally:
            box.clear()
            with self.lock:
                self.secrets.pop(key, None)
                self.clear_remote(key)
                if key in self.jobs:
                    self.jobs[key]['_closed'] = True


jobs = SyncJobs()
