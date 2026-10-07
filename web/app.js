// 本文件由团队编写为主；标注 [AI编写] 的段落为开发迭代过程中由 AI（千问工作助理）生成的代码，均已标注。
var KY_SEC = ""; var KY_TOPIC = ""; var KY_MODE = "policy";
/* 百花学习与生活顾问系统 · 前端逻辑（无框架，直接可跑） */
let TOKEN = localStorage.getItem("bh_token") || "";
let PROFILE = null;
let graphChart = null;
let curNodes = [];
let TT_DATA = null;      // 「实时课程表」最近一次 /api/timetable 的返回
let TT_EDIT = null;      // 「实时课程表」正在录入的格子 {day, period}

/* ---------- 通用请求 ---------- */
async function api(path, opt = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opt.headers || {});
  if (TOKEN) headers["X-Session-Token"] = TOKEN;
  const resp = await fetch(path, Object.assign({}, opt, { headers }));
  if (resp.status === 401) { showLogin(); throw new Error("登录已过期，请重新登录"); }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || "请求失败");
  return data;
}
const $ = (id) => document.getElementById(id);

/* ---------- 弹层：登录/注册/找回密码 三表单切换 ---------- */
let needLoginThen = null;      // 登录后要自动执行的动作
function showLogin(then) {
  needLoginThen = then || null;
  $("login-page").classList.remove("hidden");
  switchAuthForm("login");
}
function switchAuthForm(which) {
  $("login-form").classList.toggle("hidden", which !== "login");
  $("register-form").classList.toggle("hidden", which !== "register");
  $("forgot-form").classList.toggle("hidden", which !== "forgot");
}
function hideLogin() { $("login-page").classList.add("hidden"); }
$("btn-login-open").addEventListener("click", () => showLogin());
$("btn-guest").addEventListener("click", () => { hideLogin(); });
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-err").textContent = "";
  try {
    const r = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: $("login-phone").value, password: $("login-pw").value }),
    });
    const d = await r.json();
    if (!r.ok) { $("login-err").textContent = d.detail || "登录失败"; return; }
    TOKEN = d.token; PROFILE = d.profile;
    localStorage.setItem("bh_token", TOKEN);
    hideLogin(); refreshUserUI();
    const act = needLoginThen; needLoginThen = null;
    if (act) act();
  } catch (err) { $("login-err").textContent = "无法连接服务，请确认已运行 app.py"; }
});
$("btn-logout").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST" }); } catch (e) {}
  TOKEN = ""; PROFILE = null; localStorage.removeItem("bh_token");
  refreshUserUI(); switchTab("home");
});

/* ---------- 注册：学院→专业联动，全字段必填 ---------- */
$("go-register").addEventListener("click", async () => {
  switchAuthForm("register");
  $("reg-err").textContent = "";
  loadRegisterMeta();
});
let COLLEGES = [];
let META_LOADED = false;
async function loadRegisterMeta(force = false) {
  if (META_LOADED && !force) return;
  try {
    const r = await fetch("/api/register/meta"); const m = await r.json();
    COLLEGES = m.colleges || [];
    $("reg-college").innerHTML = COLLEGES.map(c =>
      `<option value="${c.college}">${c.college}（${c.majors.length}个专业）</option>`).join("");
    $("reg-campus").innerHTML = (m.campuses || ["东校区", "西校区", "昌平校区"]).map(x => `<option>${x}</option>`).join("");
    $("reg-goal").innerHTML = (m.goals || ["保研", "考研", "出国", "就业/企业", "暂未确定"])
      .map(x => `<option>${x}</option>`).join("");
    $("reg-grade").value = m.grade_suggest || new Date().getFullYear();
    $("reg-grade").min = (m.grade_range || [2020, 2030])[0];
    $("reg-grade").max = (m.grade_range || [2020, 2030])[1];
    $("reg-college").addEventListener("change", fillMajorOptions);
    META_LOADED = true;
    fillMajorOptions();
  } catch (e) { $("reg-err").textContent = "学院选项加载失败，请刷新重试"; }
}
function fillMajorOptions() {
  const c = COLLEGES.find(x => x.college === $("reg-college").value) || COLLEGES[0];
  if (!c) return;
  $("reg-major").innerHTML = c.majors.map(x => `<option>${x}</option>`).join("");
  const planned = c.planned || [];
  $("reg-plan-tip").textContent = planned.length
    ? `✔ 本院已有真实培养方案（可选课推荐）：${planned.join("、")}`
    : "该学院培养方案暂未录入，选课推荐将提示补充";
}
$("go-login").addEventListener("click", () => switchAuthForm("login"));
$("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("reg-err").textContent = "";
  const body = {
    student_id: $("reg-id").value, name: $("reg-name").value,
    phone: $("reg-phone").value.trim(),
    password: $("reg-pw").value, confirm: $("reg-pw2").value,
    college: $("reg-college").value,
    major: $("reg-major").value, grade: Number($("reg-grade").value),
    campus: $("reg-campus").value, goal: $("reg-goal").value,
    preference: ($("reg-pref") || {}).value || "",
  };
  try {
    const r = await fetch("/api/register", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) { $("reg-err").textContent = d.detail || "注册失败"; return; }
    TOKEN = d.token; PROFILE = d.profile;
    localStorage.setItem("bh_token", TOKEN);
    hideLogin(); refreshUserUI();
    const act = needLoginThen; needLoginThen = null;
    if (act) act();
  } catch (err) { $("reg-err").textContent = "无法连接服务"; }
});

/* ---------- 忘记密码：获取验证码 + 重置 ---------- */
$("go-forgot").addEventListener("click", () => { switchAuthForm("forgot"); $("fg-err").textContent = ""; });
$("fg-back").addEventListener("click", () => switchAuthForm("login"));
let fgTimer = null;
$("fg-send").addEventListener("click", async () => {
  const phone = $("fg-phone").value.trim();
  $("fg-err").textContent = ""; $("fg-tip").textContent = "";
  if (!/^1[3-9]\d{9}$/.test(phone)) { $("fg-err").textContent = "请先填写正确的 11 位手机号"; return; }
  try {
    const r = await fetch("/api/forgot/send", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone }) });
    const d = await r.json();
    if (!r.ok) { $("fg-err").textContent = d.detail || "发送失败"; return; }
    $("fg-tip").textContent = d.msg + " 你的验证码：" + d.demo_code;
    $("fg-code").value = d.demo_code;                       // 演示：自动回填
    let sec = 60;
    $("fg-send").disabled = true;
    clearInterval(fgTimer);
    fgTimer = setInterval(() => {
      $("fg-send").textContent = sec <= 0 ? "重新获取" : sec + "秒后重发";
      if (sec-- <= 0) { clearInterval(fgTimer); $("fg-send").disabled = false; $("fg-send").textContent = "获取验证码"; }
    }, 1000);
    $("fg-send").textContent = "60秒后重发";
  } catch (e) { $("fg-err").textContent = "无法连接服务"; }
});
$("forgot-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("fg-err").textContent = "";
  try {
    const r = await fetch("/api/forgot/reset", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: $("fg-phone").value.trim(), code: $("fg-code").value.trim(),
                             new_password: $("fg-pw").value }) });
    const d = await r.json();
    if (!r.ok) { $("fg-err").textContent = d.detail || "重置失败"; return; }
    switchAuthForm("login");
    $("login-phone").value = $("fg-phone").value.trim();
    $("login-err").textContent = ""; $("login-err").classList.add("ok");
    $("login-err").textContent = "✔ " + d.msg;
    setTimeout(() => $("login-err").classList.remove("ok"), 4000);
  } catch (err) { $("fg-err").textContent = "无法连接服务"; }
});

/* ---------- 启动：游客直接进系统；有 token 则恢复登录态 ---------- */
(async function boot() {
  if (TOKEN) {
    try { PROFILE = await api("/api/profile"); }
    catch (e) { TOKEN = ""; PROFILE = null; localStorage.removeItem("bh_token"); hideLogin(); }
  }
  enterApp();
})();

function refreshUserUI() {
  const logged = !!(PROFILE && !PROFILE.guest);
  $("user-name").textContent = logged ? `${PROFILE.name} · ${PROFILE.major} · ${PROFILE.grade}级` : "游客";
  $("btn-login-open").classList.toggle("hidden", logged);
  $("btn-logout").classList.toggle("hidden", !logged);
  // 业务大厅画像卡片
  if (logged) {
    $("hello-name").textContent = `${PROFILE.name}，欢迎使用百花顾问系统`;
    $("hello-meta").textContent = `学号 ${PROFILE.student_id} · ${PROFILE.college || ""} ${PROFILE.major} · ${PROFILE.grade}级`;
    $("pill-goal").textContent = "目标：" + (PROFILE.goal || "未填写");
    $("pill-campus").textContent = "校区：" + (PROFILE.campus || "-");
  } else {
    $("hello-name").textContent = "你好，欢迎来到百花顾问系统";
    $("hello-meta").textContent = "当前为游客浏览：智能问答（校园生活）、培养方案图谱、FAQ 可直接使用；二课积分与选课推荐需登录";
    $("pill-goal").textContent = "未登录";
    $("pill-campus").textContent = "游客模式";
  }
  if (TT_DATA) loadTimetable();   // 登录 / 退出后刷新「实时课程表」的个人课表
}

async function enterApp() {
  $("login-page").classList.add("hidden");
  $("main-page").classList.remove("hidden");
  refreshUserUI();
  loadNotice(); switchTab("home"); loadMajors();
  if (PROFILE && !PROFILE.guest) loadErkeTypes();
  if (!$("btn-chat-new")._bound) {
    $("btn-chat-new").addEventListener("click", newChat);
    $("btn-chat-new")._bound = true;
  }
  if (!$("chat-box").children.length) greet();
}

/* ---------- 业务大厅：卡片点击 → 跳转 / 自动提问 ---------- */
document.querySelectorAll(".biz-card").forEach(card => card.addEventListener("click", () => {
  if (card.dataset.go) { switchTab(card.dataset.go); }
  else if (card.dataset.ask) {
    switchTab("chat");
    sendChat(card.dataset.ask);
  }
}));

/* ---------- 我的资料：查看与修改注册信息 ---------- */
async function loadProfileForm() {
  await loadRegisterMeta(true);
  const p = PROFILE || {};
  $("pf-id").value = p.student_id || "";
  $("pf-name").value = p.name || "";
  $("pf-phone").value = p.phone || "";
  $("pf-grade").value = p.grade || "";
  $("pf-college").innerHTML = COLLEGES.map(c =>
    `<option ${c.college === p.college ? "selected" : ""}>${c.college}</option>`).join("");
  $("pf-campus").innerHTML = ["东校区", "西校区", "昌平校区"].map(x =>
    `<option ${x === p.campus ? "selected" : ""}>${x}</option>`).join("");
  $("pf-goal").innerHTML = ["保研", "考研", "出国", "就业/企业", "暂未确定"]
    .map(x => `<option ${x === p.goal ? "selected" : ""}>${x}</option>`).join("");
  $("pf-pref").value = p.preference || "";
  fillPfMajors(false);
  $("pf-err").textContent = ""; $("pf-msg").textContent = "";
}
function fillPfMajors(keep = true) {
  const c = COLLEGES.find(x => x.college === $("pf-college").value) || COLLEGES[0];
  if (!c) return;
  const prev = keep ? $("pf-major").value : "";
  $("pf-major").innerHTML = c.majors.map(x => `<option ${x === prev ? "selected" : ""}>${x}</option>`).join("");
  const planned = c.planned || [];
  $("pf-plan-tip").textContent = planned.length
    ? `✔ 本院已有真实培养方案（可选课推荐）：${planned.join("、")}`
    : "该学院培养方案暂未录入，选课推荐将提示补充";
}
$("pf-college").addEventListener("change", () => fillPfMajors(false));
$("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("pf-err").textContent = ""; $("pf-msg").textContent = "保存中…";
  try {
    const d = await api("/api/profile/update", { method: "POST", body: JSON.stringify({
      name: $("pf-name").value, phone: $("pf-phone").value.trim(),
      college: $("pf-college").value, major: $("pf-major").value,
      grade: Number($("pf-grade").value), campus: $("pf-campus").value,
      goal: $("pf-goal").value, preference: $("pf-pref").value }) });
    PROFILE = d.profile;
    $("pf-msg").textContent = ""; $("pf-err").textContent = "";
    $("pf-msg").textContent = "✔ " + d.msg;
    // 画像即时生效：顶部信息、学业规划面板、图谱专业全部刷新
    refreshUserUI();
    loadMajors().then(() => {
      onSubMajorChange();
      if (!document.getElementById("tab-graph").classList.contains("hidden")) loadPlan();
    });
    setTimeout(() => { $("pf-msg").textContent = ""; }, 6000);
  } catch (err) { $("pf-msg").textContent = ""; $("pf-err").textContent = err.message; }
});

/* ---------- Tab 切换 ---------- */
document.querySelectorAll(".tab-btn").forEach(b =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));
function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  // [AI编写] 标签页切换补充 education 面板与登录引导（修复个性化标签空白，UI 修复轮）
  ["home", "chat", "graph", "erke", "profile", "education", "faq"].forEach(t => $("tab-" + t).classList.toggle("hidden", t !== name));
  if (name === "education") {
    if (!isLogged()) { showLogin(() => switchTab("education")); return; }
    loadEducation();
    eduLoadTimetable();
  }
  if (name === "graph") {
    renderGraph(); loadGoalOptions();
    if (isLogged()) loadPlan();
    else $("plan-body").innerHTML = `<p class="muted">选课推荐与学业规划需要结合你的专业画像。</p>
      <button class="btn-primary btn-sm-inline" onclick="showLogin(() => loadPlan())">登录 / 注册后查看我的规划</button>`;
  }
  if (name === "erke") {
    if (!isLogged()) { showLogin(() => switchTab("erke")); return; }
    loadErke();
  }
  if (name === "profile") {
    if (!isLogged()) { showLogin(() => switchTab("profile")); return; }
    loadProfileForm();
  }
  if (name === "faq") { loadFaq(); }
}
const isLogged = () => !!(PROFILE && !PROFILE.guest);

/* ---------- 学业规划（真实培养方案） ---------- */
async function loadPlan() {
  try {
    const d = await api("/api/plan");
    $("plan-meta").textContent = `${d.college} · ${d.major} · ${d.grade}级 · 依据${d.source}`;
    const synced = !!d.credit_synced;
    const gap = synced ? d.progress.filter(p => p.required && p.done_required != null && p.done_required < p.required && /必修|实践环节/.test(p.section)) : [];
    const nextReq = d.next_courses.filter(c => c.nature === "必修");
    const nextSel = d.next_courses.filter(c => c.nature !== "必修");
    // [AI编写] 学业规划统计卡“待同步”态渲染与开启引导（学分待同步轮）
    const syncTip = synced ? "" :
      `<p class="plan-warn">⏳ 已获学分待同步：实际修读学分需开启个性化服务后读取。
        <a href="javascript:void(0)" onclick="openPersonalService()">点此开启个性化服务 ›</a></p>`;
    $("plan-body").innerHTML = `
      <div class="plan-grid">
        <div class="plan-cell"><b>${synced ? d.done_credit : "待同步"}</b><span>已获学分 / ${d.grad_credit}</span>
          <div class="bar"><i style="width:${synced ? d.pct : 0}%"></i></div></div>
        <div class="plan-cell"><b>${d.current_term}/${d.total_terms}</b><span>当前学期</span></div>
        <div class="plan-cell"><b>${synced ? d.remaining : "待同步"}</b><span>剩余学分</span></div>
        <div class="plan-cell"><b>${nextReq.length}</b><span>下学期必修门数（${d.next_required_credit}分）</span></div>
      </div>
      ${syncTip}
      ${synced ? (gap.length ? `<p class="plan-warn">⚠ 必修模块进度缺口：${gap.map(p => `${p.section}差 ${Math.round((p.required - p.done_required) * 10) / 10} 分`).join("、")}</p>` : '<p class="plan-ok">✔ 各必修模块进度正常</p>') : ""}
      <p class="muted">下学期（${d.next_term_label}）建议课程：</p>
      <div class="plan-courses">${d.next_courses.map(c => `
        <span class="pc ${c.nature === "必修" ? "pc-req" : "pc-ele"}" title="${c.section}">
          ${c.name} ${c['credit']}分${c.prereq_missing.length ? `<em class="pc-warn">缺先修:${c.prereq_missing.join("、")}</em>` : ""}
        </span>`).join("")}</div>
      <p class="muted">注：课程与学分来自执行计划原文；先修关系由规则引擎按课程依赖推断，正式选课以教务系统为准。</p>`;
  } catch (e) {
    $("plan-meta").textContent = "";
    $("plan-body").innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

/* ---------- 资讯推送 ---------- */
async function loadNotice() {
  try { const d = await api("/api/notice"); $("notice-bar").textContent = d.notice; } catch (e) {}
}

/* ---------- 智能问答 ---------- */
function addMsg(role, text, sources, extra) {
  const box = $("chat-box");
  const wrap = document.createElement("div");
  wrap.className = "msg " + (role === "user" ? "user" : "bot");
  if (role === "bot" && extra) {
    const tag = document.createElement("div");
    tag.className = "role-tag";
    const routeName = { study: "→ 学习顾问", life: "→ 生活顾问", mixed: "→ 双顾问协同" }[extra.route] || "→ 通用";
    tag.textContent = routeName + (extra.generic ? " · 🤖 AI 通用建议"
      : ((extra.llm_mode === "local" || extra.llm_mode === "bailian") ? " · 大模型已接入"
         : (extra.llm_mode === "local-demo" ? " · 本地演示模式" : "")));
    wrap.appendChild(tag);
  }
  const b = document.createElement("div"); b.className = "bubble"; b.textContent = text; wrap.appendChild(b);
  if (sources && sources.length) {
    const s = document.createElement("div"); s.className = "sources";
    s.innerHTML = sources.map(x => `<div class="src-card"><b>📄 ${esc(x.title || "来源")}</b><br>
      出处：${esc(x.source || "-")}<br>适用：${esc(x.scope || "-")}<br>更新：${esc(x.updated_at || "-")}
      · ${x.verified ? '<span class="v-ok">已人工核验</span>' : '<span class="v-no">待核验</span>'}</div>`).join("");
    wrap.appendChild(s);
  }
  box.appendChild(wrap); box.scrollTop = box.scrollHeight;
  return wrap;
}
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let CHAT_ID = "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
async function newChat() {
  CHAT_ID = "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  $("chat-box").innerHTML = "";
  greet();
}
function greet() {
  addMsg("bot", "你好！我是百花生活学习顾问 🌸\n· 校园办事、就医、食堂这类问题，我会查学校知识库并附来源\n· 其他任何问题（学习技巧、心理、数码、闲聊…）也可以直接问我\n点击下方快捷提问，或输入你的问题；换话题点右上「新对话」。", null, { route: "other" });
}

async function sendChat(text) {
  if (!text.trim()) return;
  addMsg("user", text);
  $("chat-text").value = "";
  const holder = addMsg("bot", "思考中…");
  try {
    const d = await api("/api/chat", { method: "POST",
      body: JSON.stringify({ question: text, chat_id: CHAT_ID }) });
    holder.remove();
    $("llm-mode").textContent = d.llm_mode === "local" ? "本地大模型已接入（Qwen3·免Key免费）"
      : d.llm_mode === "bailian" ? "百炼云端大模型已接入" : "本地演示模式（未接大模型）";
    addMsg("bot", d.answer, d.sources, d);
    if (d.need_login) {
      const tip = document.createElement("div");
      tip.className = "msg bot";
      tip.innerHTML = `<div class="bubble" style="background:#e8f2ec">
        <button id="login-guide-btn" class="btn-primary btn-sm-inline">立即登录 / 注册，获取个性化推荐</button></div>`;
      $("chat-box").appendChild(tip);
      $("login-guide-btn").addEventListener("click", () => showLogin(() => sendChat(text)));
      $("chat-box").scrollTop = 1e9;
    }
    if (d.needs_feedback) {
      const tip = document.createElement("div");
      tip.className = "msg bot";
      tip.innerHTML = `<div class="bubble" style="background:#fff7e0">该问题知识库暂未覆盖，
        <a href="javascript:void(0)" onclick="switchTab('faq')" style="color:#1a6b4f">点此提交反馈 →</a></div>`;
      $("chat-box").appendChild(tip); $("chat-box").scrollTop = 1e9;
    }
  } catch (e) { holder.remove(); addMsg("bot", "出错了：" + e.message); }
}
$("chat-send").addEventListener("click", () => sendChat($("chat-text").value));
$("chat-text").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(e.target.value); });
document.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => sendChat(c.textContent)));

/* ---------- 学期课表查询（有序调取培养方案） ---------- */
async function runTermSchedule() {
  const major = $("ts-major").value, term = $("ts-term").value, grade = $("ts-grade").value;
  const box = $("ts-result");
  box.innerHTML = '<p class="muted">正在按培养方案定位学期…</p>';
  try {
    const d = await api("/api/term-schedule?major=" + encodeURIComponent(major) +
      "&term=" + term + "&grade=" + (grade || 0));
    const row = c => `<div class="ts-course"><span>${c.name}</span><b>${c.credit}分</b>` +
      (c.prereq_missing.length ? `<em>⚠ 先修注意：${c.prereq_missing.join("；")}</em>` : "") + `</div>`;
    const secs = Object.entries(d.required_by_section).map(([sec, cs]) =>
      `<div class="ts-sec"><div class="ts-sec-head">◆ ${sec}（${cs.length}门）</div>${cs.map(row).join("")}</div>`).join("");
    box.innerHTML = `
      <div class="ts-head">📖 依据《${d.source.replace(/[《》]/g, "")}》 · ${d.college} · ${d.major} · ${d.grade}级
        <span class="ts-tag">${d.target_label}（${d.term_year_label}）</span>
        <span class="ts-tag ghost">当前第${d.current_term}学期</span></div>
      <div class="ts-block"><h4>一、本学期必修安排（方案固定，共 ${d.required.length} 门 ${d.required_credit} 学分）</h4>${secs || '<p class="muted">本学期方案未安排必修课堂课程（多为毕业实习/论文/求职学期）</p>'}</div>
      <div class="ts-block"><h4>二、本学期选修池（${d.electives.length} 门可选，合计 ${d.elective_credit} 学分 —— 按兴趣与学分缺口自选）</h4>
        ${d.electives.map(c => `<div class="ts-course"><span>${c.name}</span><b>${c.credit}分</b><i>${c.section}</i>${c.prereq_missing.length ? `<em>⚠ 先修注意：${c.prereq_missing.join("；")}</em>` : ""}</div>`).join("") || '<p class="muted">本学期方案未安排选修课</p>'}</div>
      <div class="ts-block ts-note">三、按方案进度：修完本学期后距最低毕业学分还剩约 <b>${d.remaining_after}</b> 学分。</div>`;
  } catch (e) { box.innerHTML = `<p class="bad">${e.message}</p>`; }
}
$("btn-ts").addEventListener("click", runTermSchedule);

/* ---------- 目标导向学业规划 ---------- */
let GP_GOAL = "保研";
async function loadGoalOptions() {
  try {
    const d = await api("/api/goal-options");
    const logged = isLogged();
    if (logged && PROFILE.goal && d.goals.some(g => g.goal === PROFILE.goal)) GP_GOAL = PROFILE.goal;
    $("gp-pills").innerHTML = d.goals.map(g =>
      `<button class="gp-pill ${g.goal === GP_GOAL ? "on" : ""}" data-goal="${g.goal}" title="${g.focus}">${g.goal}</button>`).join("");
    document.querySelectorAll("#gp-pills .gp-pill").forEach(p => p.addEventListener("click", () => {
      GP_GOAL = p.dataset.goal;
      BY_MODE = "policy"; BY_CH = ""; KY_SEC = ""; KY_TOPIC = ""; KY_MODE = "policy";
      SA_MODE = "policy"; SA_QUERY = "";
      document.querySelectorAll("#gp-pills .gp-pill").forEach(x => x.classList.toggle("on", x === p));
      syncToMajorSel();
      syncBaoyanView();
      const policyView = GP_GOAL === "就业"
        || ((GP_GOAL === "保研" || GP_GOAL === "考研" || GP_GOAL === "出国") &&
            (GP_GOAL !== "保研" || BY_MODE === "policy") &&
            (GP_GOAL !== "考研" || KY_MODE === "policy") &&
            (GP_GOAL !== "出国" || SA_MODE === "policy"));
      if (!policyView) runGoalPlan();
    }));
    syncToMajorSel();
    syncBaoyanView();
  } catch (e) {}
}
function syncToMajorSel() {
  const isT = GP_GOAL === "转专业";
  document.querySelector(".gp-to-major").classList.toggle("hidden", !isT);
  if (isT) {
    const cur = $("gp-major").value;
    const opts = [...$("gp-major").options].map(o => o.value).filter(v => v && v !== cur);
    $("gp-to-major").innerHTML = opts.map(v => `<option>${v}</option>`).join("");
  }
}
async function runGoalPlan() {
  const box = $("gp-result");
  box.innerHTML = '<p class="muted">链路执行中：识别目标 → 检索课程知识库 → 组装提示词 → 生成规划…</p>';
  try {
    let url = "/api/goal-plan?major=" + encodeURIComponent($("gp-major").value) +
      "&grade=" + ($("gp-grade").value || 0) + "&goal=" + encodeURIComponent(GP_GOAL);
    if (GP_GOAL === "转专业") url += "&to_major=" + encodeURIComponent(($("gp-to-major") || {}).value || "");
    const d = await api(url);

    // ===== 转专业分支：政策要求 + 两方案对比 + 要做的工作 =====
    if (d.need_to_major) {
      box.innerHTML = `<div class="ts-block"><h4>请先选择转入专业</h4><p class="muted" style="font-size:15px">
        可选（已收录培养方案）：${d.options.filter(o => o !== d.from_major).join("、")}</p></div>`;
      return;
    }
    if (d.transfer) { box.innerHTML = renderTransfer(d.transfer); return; }

    const tag = (c) => `<b class="cc-tag ${c.nature === "必修" ? "req" : "ele"}">${c.nature}</b>`;
    const diffTag = (x) => `<b class="diff diff-${x === "难" ? "h" : x === "中" ? "m" : "e"}">${x}</b>`;
    // 表格化：优先选课
    const courseTable = (arr) => `<table class="gp-table"><thead><tr>
        <th>课程名称</th><th>性质</th><th>学分</th><th>开课学期</th><th>匹配度</th><th>推荐理由 / 注意</th></tr></thead>
      <tbody>${arr.map(c => `<tr><td>${c.name}</td><td>${tag(c)}</td><td>${c.credit}</td>
        <td>${c.term_label}</td><td class="gp-score">${c.score}</td>
        <td class="gp-why">${c.prereq_ok ? "" : '<span class="bad">⚠先修链未闭合；</span>'}${(c.reasons || []).join("；") || "-"}</td></tr>`).join("")}</tbody></table>`;
    // 板块：分学期排期（结构化数据 → 表格）
    let schedHtml = "";
    if (d.schedule) {
      const sc = d.schedule;
      schedHtml = `<div class="ts-block"><h4>板块二 · 分学期课程规划表（按 ${d.goal || sc.goal} 目标排定，满足学分/课时/难度三约束）</h4>
        <div class="gp-kpis">
          <span>毕业要求 <b>${sc.grad_credit}</b> 学分</span>
          <span>按方案已修 <b>${sc.done_credit}</b></span>
          <span>规划覆盖 <b>${sc.planned_credit}</b></span>
          ${sc.shortfall > 0 ? `<span class="bad">知识库缺口 <b>${sc.shortfall}</b>（分流后/后续新课）</span>` : `<span class="ok">总学分约束 ✔</span>`}
        </div>
        ${sc.schedule.map(s => {
          if (!s.courses.length) return "";
          return `<div class="tt-term"><div class="tt-term-h">第 ${s.term} 学期 <span class="muted">${s.label} · ${s.hours} 学时 · ${s.credit} 学分 · 难课 ${s.hard} 门</span></div>
            <table class="gp-table"><thead><tr><th>课程</th><th>性质</th><th>学分</th><th>课时</th><th>难度</th><th>模块</th><th>简介</th></tr></thead>
            <tbody>${s.courses.map(c => `<tr><td>${c.name}</td><td>${tag(c)}</td><td>${c.credit}</td>
              <td>${Math.round(c.hours)}</td><td>${diffTag(c.difficulty)}</td><td>${c.section}</td>
              <td class="gp-intro">${(c.intro || "").slice(0, 46)}</td></tr>`).join("")}</tbody></table></div>`;
        }).join("")}
      </div>`;
    }
    const gp = d.plan;
    let main = "";
    if (d.answer) {
      main = `<details class="ts-block gp-text"><summary>🤖 规划完整文字稿
        <span class="ts-tag ${d.mode === "llm" ? "" : "ghost"}">${d.mode === "llm" ? "大模型生成" : "规则引擎（同约束）"}</span></summary>
        <pre class="gp-md">${esc(d.answer)}</pre>
        <details class="gp-prompt"><summary>查看本次发送给大模型的提示词（含知识库数据）</summary>
        <pre class="gp-md small">${esc(d.prompt || "（本次未生成提示词）")}</pre></details></details>`;
    }
    const detail = gp ? `
      <div class="ts-block"><h4>板块三 · 未来两学期优先选课（按目标匹配度排序）</h4>
        ${Object.entries(gp.by_term).map(([label, cs]) =>
          `<div class="tt-sub"><span class="tt-sub-h">◆ ${label}</span>${courseTable(cs)}</div>`).join("") || '<p class="muted">近两学期无新增可选课程</p>'}</div>
      <div class="ts-block"><h4>板块四 · 全程匹配度最高的 ${gp.top.length} 门（提前规划先修链）</h4>${courseTable(gp.top)}</div>
      ${gp.erke_tips.length ? `<div class="ts-block"><h4>板块五 · 第二课堂配套建议（依据实施办法条款）</h4>
        <table class="gp-table"><thead><tr><th>建议</th><th>条款</th></tr></thead>
        <tbody>${gp.erke_tips.map(t => `<tr><td>${t.hint}</td><td>${t.article}</td></tr>`).join("")}</tbody></table></div>` : ""}` : "";
    box.innerHTML = `
      <div class="ts-head">🎯 目标 <b>${gp ? gp.goal : d.goal}</b>（${d.note || "面板选择"}）${gp ? " · " + gp.college + " · " + gp.major + " · " + gp.grade + "级" : ""}
        ${gp ? `<span class="ts-tag ghost">当前第${gp.current_term}学期 / 未修 ${gp.pending_count} 门</span>` : ""}</div>
      ${gp ? `<div class="ts-block"><h4>板块一 · 目标策略</h4><p style="font-size:15px;line-height:1.8">${gp.focus}</p></div>` : ""}
      ${schedHtml}${main}${detail}
      <p class="muted" style="margin-top:8px">流程：提问目标 → 外接课程知识库(简介/学分/课时/难度) → 整合生成提示词 → 大模型/规则引擎输出规划。课程与学分取自培养方案原文；正式选课以教务系统与学院意见为准。</p>`;
  } catch (e) { box.innerHTML = `<p class="bad">${e.message}</p>`; }
}
$("btn-gp").addEventListener("click", runGoalPlan);

/* ---------- 保研四通道（挂在“目标导向规划 → 保研”下） ---------- */
const BY_ICON = { "普通学业推免": "🎓", "支教保研": "🏫", "行政保研": "🏛", "直博推免": "🔬" };
let BY_DATA = null;                 // 总览数据缓存
let BY_CH = "";                     // 当前展开的通道，空 = 四板块总览
let BY_MODE = "policy";             // policy=通道政策视图，plan=保研选课规划视图

function renderByPills() {
  const list = ["四通道总览", "普通学业推免", "支教保研", "行政保研", "直博推免"];
  $("by-pills").innerHTML = list.map(c => {
    const on = (c === "四通道总览") ? !BY_CH : BY_CH === c;
    const ico = c === "四通道总览" ? "📊" : BY_ICON[c];
    return `<button class="gp-pill ${on ? "on" : ""}" data-ch="${c === "四通道总览" ? "" : c}">${ico} ${c}</button>`;
  }).join("");
  document.querySelectorAll("#by-pills .gp-pill").forEach(p => p.addEventListener("click", () => {
    BY_CH = p.dataset.ch;
    runBaoyan();
  }));
}

async function runBaoyan() {
  const box = $("by-result");
  box.innerHTML = '<p class="muted">正在调取保研政策库…</p>';
  try {
    if (BY_CH) {
      BY_DATA = null;
      const d = await api("/api/baoyan?channel=" + encodeURIComponent(BY_CH));
      box.innerHTML = renderBaoyan(d.baoyan, d.logged_in);
    } else {
      if (!BY_DATA) {
        const d = await api("/api/baoyan?channel=" + encodeURIComponent("保研"));
        BY_DATA = d.baoyan;
      }
      box.innerHTML = renderByOverview(BY_DATA);
    }
    renderByPills();
    document.querySelectorAll(".by-board").forEach(b => b.addEventListener("click", () => {
      BY_CH = b.dataset.ch; runBaoyan();
    }));
    const back = document.getElementById("by-back");
    if (back) back.addEventListener("click", () => { BY_CH = ""; runBaoyan(); });
    const planBtn = document.getElementById("by-plan-btn");
    if (planBtn) planBtn.addEventListener("click", () => {
      BY_MODE = "plan";                       // 切到“按保研目标生成选课规划”
      $("gp-baoyan").classList.add("hidden");
      $("gp-normal-tools").classList.remove("hidden");
      $("gp-result").classList.remove("hidden");
      runGoalPlan();
    });
  } catch (e) { box.innerHTML = `<p class="bad">${e.message}</p>`; }
}

/* —— 四板块总览：共用地基 + 四通道卡片 + 学年路线 —— */
function renderByOverview(a) {
  const common = a.common.points.map(p => `<li>${p}</li>`).join("");
  const boards = a.boards.map(b => `
    <div class="by-board" data-ch="${b.name}">
      <div class="by-b-head"><span class="by-b-ico">${BY_ICON[b.name]}</span><b>${b.name}</b>
        <span class="by-b-go">查看详情 →</span></div>
      <p class="by-b-ess">${b.essence}</p>
      <ul class="by-b-keys">${b.hard_simple.map(([k, v]) => `<li><i>${k}</i><b>${v}</b></li>`).join("")}</ul>
      <p class="by-b-quota">📊 名额：${b.quota}</p>
      <p class="by-b-risk">⚠ ${b.risk}</p>
    </div>`).join("");
  const plan = Object.entries(a.year_plan).map(([yr, items]) =>
    `<details ${yr === "大一" ? "open" : ""}><summary><b>${yr}</b> 要做的事（${items.length} 项）</summary>
      <ul class="tf-ul">${items.map(t => `<li>☐ ${t}</li>`).join("")}</ul></details>`).join("");
  const src = a.meta.sources.map(s => `<li>${s}</li>`).join("");
  return `
    <div class="ts-head by-head">🎓 ${a.meta.college} · 保研四通道<span class="ts-tag ghost">更新至 ${a.meta.updated_at}</span>
      <button id="by-plan-btn" class="btn-primary btn-sm" style="margin-left:auto">📚 按保研目标生成选课规划</button></div>
    <div class="ts-block" style="background:#eef7ee;border-color:#bcd8bc"><h4>先记住：四条通道共用的地基</h4>
      <ul class="tf-ul">${common}</ul></div>
    <div class="ts-block"><h4>四条通道 · 点选板块看完整政策（条件 / 名额 / 流程 / 材料 / 风险）</h4>
      <div class="by-grid">${boards}</div></div>
    <div class="ts-block"><h4>按学年的准备路线（大学四年倒排）</h4>${plan}</div>
    <details class="gp-prompt"><summary>📄 政策原文出处（${a.meta.sources.length} 份正式文件）与口径说明</summary>
      <ul class="tf-ul">${src}</ul><p class="muted">${a.meta.disclaimer}</p></details>`;
}

function renderBaoyan(a, logged) {
  const src = a.meta.sources.map(s => `<li>${s}</li>`).join("");
  const foot = `<details class="gp-prompt"><summary>📄 政策原文出处（${a.meta.sources.length} 份正式文件）与口径说明</summary>
      <ul class="tf-ul">${src}</ul><p class="muted">${a.meta.disclaimer}</p></details>`;

  /* —— 总览：对比表 + 共用地基 + 学年路线 —— */
  if (a.channel === "保研") {
    const head = ["维度", "普通学业推免", "支教保研", "行政保研", "直博推免"];
    const rows = a.compare_rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("");
    const common = a.common.points.map(p => `<li>${p}</li>`).join("");
    const plan = Object.entries(a.year_plan).map(([yr, items]) =>
      `<details ${yr === "大一" ? "open" : ""}><summary><b>${yr}</b> 要做的事（${items.length} 项）</summary>
        <ul class="tf-ul">${items.map(t => `<li>☐ ${t}</li>`).join("")}</ul></details>`).join("");
    return `
      <div class="ts-head">🎓 ${a.meta.college} · 保研四通道总览<span class="ts-tag ghost">更新至 ${a.meta.updated_at}</span></div>
      <div class="ts-block"><h4>四条通道核心对比（横看一列，竖看一行）</h4>
        <table class="gp-table by-cmp"><thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="ts-block" style="background:#eef7ee;border-color:#bcd8bc"><h4>① 四条通道共用的地基（先看这里）</h4>
        <ul class="tf-ul">${common}</ul></div>
      <div class="ts-block"><h4>② 按学年的准备路线（大学四年倒排）</h4>${plan}</div>
      <p class="muted" style="margin-top:8px">👆 点击上方任一通道，查看该通道的硬性条件、名额、流程、材料清单与风险点；登录后填写下方自评表，可逐项核对达标情况。</p>
      ${foot}`;
  }

  /* —— 单通道 —— */
  const hard = a.hard.map(([it, req, note]) => `<tr><td><b>${it}</b></td><td>${req}</td><td class="muted">${note || "—"}</td></tr>`).join("");
  const prio = a.priority.map(p => `<li>${p}</li>`).join("");
  const proc = a.process.map((s, i) => `<li><b>${i + 1}.</b> ${s}</li>`).join("");
  const mats = (a.materials || []).map((m, i) => `<li>${i + 1}. ${m}</li>`).join("");
  const chk = (a.checklist || []).map(c => `<li>☐ ${c}</li>`).join("");
  const ben = (a.benefit || []).map(b => `<li>${b}</li>`).join("");
  let scHtml = "";
  if (a.self_check) {
    const mk = { true: "✅", false: "❌" };
    const rows = a.self_check.map(s => `<tr><td>${s.item}</td><td>${s.require}</td>
      <td>${s.actual}</td><td class="${s.ok === true ? "ok" : s.ok === false ? "bad" : "muted"}" style="text-align:center">${s.ok === null ? "⚪" : mk[String(s.ok)]}</td></tr>`).join("");
    scHtml = `<div class="ts-block"><h4>你的条件核对（依据你在下方填写的自评数据）</h4>
      <table class="gp-table"><thead><tr><th>项目</th><th>政策要求</th><th>你的情况</th><th>判定</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="muted">⚪ 表示该项为优先项或尚未填写自评数据，不构成一票否决。</p></div>`;
  } else if (!logged) {
    scHtml = `<div class="ts-block" style="background:#fdf6e6;border-color:#e3cf9a"><h4>想逐项核对自己的达标情况？</h4>
      <p class="muted">登录后在「学业规划 → 目标导向规划 → 条件自评核对」填入 GPA、六级、排名与学生工作等，系统会在这里逐条标出 ✅达标 / ❌未达 / ⚪待补。</p></div>`;
  }
  return `
    <div class="ts-head by-head">${BY_ICON[a.channel]} 保研通道 · ${a.channel}<span class="ts-tag ghost">更新至 ${a.meta.updated_at}</span>
      <button id="by-back" class="by-back-btn">← 返回四板块总览</button></div>
    <div class="ts-block"><h4>这条通道是什么</h4><p><b>${a.essence}</b></p>
      <p class="muted" style="margin-top:4px">名额：${a.quota}</p></div>
    ${scHtml}
    <div class="ts-block"><h4>硬性条件（缺一不可）</h4>
      <table class="gp-table"><thead><tr><th>项目</th><th>要求</th><th>说明 / 特例</th></tr></thead><tbody>${hard}</tbody></table></div>
    <div class="ts-block"><h4>优先与加分项</h4><ul class="tf-ul">${prio}</ul></div>
    <div class="ts-block"><h4>流程与时间节点</h4><ol class="tf-ol">${proc}</ol></div>
    ${mats ? `<div class="ts-block"><h4>报名材料清单</h4><ol class="tf-ol">${mats}</ol></div>` : ""}
    ${chk ? `<div class="ts-block"><h4>从现在起要做的工作</h4><ul class="tf-ul">${chk}</ul></div>` : ""}
    ${ben ? `<div class="ts-block"><h4>直博待遇与培养</h4><ul class="tf-ul">${ben}</ul></div>` : ""}
    <div class="ts-block" style="background:#fdeceb;border-color:#eab9b2"><h4>⚠️ 最大风险点</h4><p><b>${a.risk}</b></p></div>
    ${foot}`;
}

async function saveBaoyanSelf() {
  $("by-self-err").textContent = "";
  const body = {
    gpa: $("by-gpa").value.trim(), cet6: $("by-cet6").value.trim(),
    rank_pct: $("by-rank").value.trim(), discipline: "无违纪处分",
    cadre: $("by-cadre").checked, party: $("by-party").checked,
    volunteer: $("by-vol").checked, teacher_cert: $("by-cert").checked,
    research: $("by-res").checked, advisor_contacted: $("by-adv").checked,
  };
  try {
    const d = await api("/api/baoyan/self", { method: "POST", body: JSON.stringify(body) });
    $("by-self-note").textContent = "已保存 ✓ " + (d.msg || "");
    if (BY_CH) runBaoyan();
  } catch (e) { $("by-self-err").textContent = e.message; }
}

function fillBaoyanSelf() {
  const s = (PROFILE && PROFILE.baoyan_self) || {};
  $("by-gpa").value = s.gpa || ""; $("by-cet6").value = s.cet6 || ""; $("by-rank").value = s.rank_pct || "";
  ["cadre", "party", "volunteer", "teacher_cert", "research", "advisor_contacted"].forEach(k => {
    const el = { cadre: "by-cadre", party: "by-party", volunteer: "by-vol", teacher_cert: "by-cert", research: "by-res", advisor_contacted: "by-adv" }[k];
    if (el) $(el).checked = !!s[k];
  });
}

$("btn-by-self").addEventListener("click", saveBaoyanSelf);
renderByPills();

/* ---------- 考研六大板块 ---------- */
let KY_ACTIONS = [];   // 行动清单已完成项："阶段-条目"
const KY_ICON = { "自身情况概览": "🙋", "考研基本常识": "💡", "具体考试内容": "📝",
                  "时间线及择校选专业": "🧭", "录取规则梳理": "🎯", "查信息防诈骗": "🛡" };

function syncBaoyanView() {
  const isBy = GP_GOAL === "保研" && BY_MODE === "policy";
  const isKy = GP_GOAL === "考研" && KY_MODE === "policy";
  const isSa = GP_GOAL === "出国" && SA_MODE === "policy";
  const isCr = GP_GOAL === "就业";
  $("gp-baoyan").classList.toggle("hidden", !isBy);
  $("gp-kaoyan").classList.toggle("hidden", !isKy);
  $("gp-sa").classList.toggle("hidden", !isSa);
  $("gp-career").classList.toggle("hidden", !isCr);
  $("gp-normal-tools").classList.toggle("hidden", isBy || isKy || isSa || isCr);
  $("gp-result").classList.toggle("hidden", isBy || isKy || isSa || isCr);
  if (isBy) {
    BY_DATA = null;
    if (isLogged()) fillBaoyanSelf();
    runBaoyan();
  } else if (isKy) {
    runKaoyan();
  } else if (isSa) {
    runStudyabroad();
  } else if (isCr) {
    runCareer();
  }
}

async function runCareer() {
  const box = $("cr-result");
  box.innerHTML = '<p class="muted">正在调取就业任务清单…</p>';
  try {
    const d = await api("/api/career");
    box.innerHTML = d.html;
    document.querySelectorAll(".cr-year").forEach(el => {
      const k = "cr-" + el.querySelector("b").textContent;
      if (localStorage.getItem(k) === "1") el.setAttribute("open", "");
      el.addEventListener("toggle", () =>
        localStorage.setItem(k, el.open ? "1" : "0"));
    });
  } catch (e) { box.innerHTML = `<p class="bad">${e.message}</p>`; }
}

async function runKaoyan() {
  const box = $("ky-result");
  $("ky-sub-bar").classList.add("hidden");
  box.innerHTML = '<p class="muted">正在调取考研资料库…</p>';
  try {
    const sec = KY_SEC || "总览";
    const d = await api("/api/kaoyan?section=" + encodeURIComponent(sec));
    KY_ACTIONS = d.actions || [];
    box.innerHTML = KY_SEC ? renderKySection(d.kaoyan) : renderKyOverview(d.kaoyan);
    renderKyPills();
    document.querySelectorAll(".ky-bind").forEach(b => b.addEventListener("click", () => {
      if (b.classList.contains("ky-todo")) return;
      KY_SEC = b.dataset.sec; KY_TOPIC = ""; runKaoyan();
    }));
    const back = document.getElementById("ky-back");
    if (back) back.addEventListener("click", () => { KY_SEC = ""; runKaoyan(); });
    const planBtn = document.getElementById("ky-plan-btn");
    if (planBtn) planBtn.addEventListener("click", () => {
      KY_MODE = "plan";
      $("gp-kaoyan").classList.add("hidden");
      $("gp-normal-tools").classList.remove("hidden");
      $("gp-result").classList.remove("hidden");
      runGoalPlan();
    });
    document.querySelectorAll("#ky-result .ky-act input").forEach(cb =>
      cb.addEventListener("change", () => saveKyAction(cb)));
  } catch (e) { box.innerHTML = `<p class="bad">${e.message}</p>`; }
}

async function saveKyAction(cb) {
  const box = $("ky-result");
  if (!isLogged()) {
    cb.checked = false;
    showLogin(() => runKaoyan());
    return;
  }
  const keys = [...box.querySelectorAll(".ky-act input:checked")].map(x => x.dataset.k);
  try {
    const d = await api("/api/kaoyan/actions", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ checked: keys }) });
    KY_ACTIONS = d.actions || keys;
    box.querySelectorAll(".ky-act").forEach(lb =>
      lb.classList.toggle("done", lb.querySelector("input").checked));
    const p = document.getElementById("ky-act-progress");
    if (p) p.textContent = `已完成 ${KY_ACTIONS.length} 项 ✔ 已保存到你的账号，下次登录仍然记得`;
  } catch (e) { cb.checked = false; }
}

function renderKyPills() {
  $("ky-pills").innerHTML = ["总览"].concat(Object.keys(KY_ICON)).map(s => {
    const on = s === "总览" ? !KY_SEC : KY_SEC === s;
    const ico = s === "总览" ? "📊" : KY_ICON[s];
    return `<button class="gp-pill ${on ? "on" : ""}" data-sec="${s === "总览" ? "" : s}">${ico} ${s}</button>`;
  }).join("");
  document.querySelectorAll("#ky-pills .gp-pill").forEach(p => p.addEventListener("click", () => {
    KY_SEC = p.dataset.sec; KY_TOPIC = ""; runKaoyan();
  }));
}

function renderKyOverview(a) {
  const o = a.overview;
  const rows = o.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("");
  const cards = a.sections.map(s => {
    const done = !a.todo.includes(s);
    return `<div class="by-board ky-bind ${done ? "" : "ky-todo"}" data-sec="${s}">
      <div class="by-b-head"><span class="by-b-ico">${KY_ICON[s]}</span><b>${s}</b>
        <span class="by-b-go">${done ? "进入板块 →" : "整理中"}</span></div>
    </div>`;
  }).join("");
  return `
    <div class="ts-head by-head">📚 考研规划 · 六大板块<span class="ts-tag ghost">更新至 ${a.meta.updated_at}</span>
      <button id="ky-plan-btn" class="by-back-btn">📖 按考研目标生成选课规划</button></div>
    <div class="ts-block"><h4>先看你属于哪类考生，确定当下该干什么</h4>
      <table class="gp-table"><thead><tr>${o.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>
      ${o.reminders.map(r => `<p class="ky-remind">⚠ ${r}</p>`).join("")}</div>
    <div class="ts-block"><h4>六大板块 · 点选进入</h4>
      <div class="by-grid">${cards}</div></div>`;
}

function renderKySection(a) {
  const backBtn = `<button id="ky-back" class="by-back-btn">← 返回板块总览</button>`;
  const foot = "";   // 按需求：考研板块页面不展示"资料来源与口径说明"折叠块
  if (a.pending) {
    return `<div class="ts-head by-head">${KY_ICON[a.section]} ${a.section}${backBtn}</div>
      <div class="ts-block" style="background:#fdf6e6;border-color:#e3cf9a">
        <h4>该板块正在按你提供的资料整理中，暂未上线</h4>
        <p class="muted">六大板块已全部开放：自身情况概览 · 考研基本常识 · 具体考试内容 · 时间线及择校选专业 · 录取规则梳理 · 查信息防诈骗</p></div>`;
  }
  const head = `<div class="ts-head by-head">${KY_ICON[a.section]} ${a.section}<span class="ts-tag ghost">更新至 ${a.meta.updated_at}</span>${backBtn}</div>`;

  /* —— 板块一：自身情况概览 —— */
  if (a.section === "自身情况概览") {
    const d = a.data;
    const rows = d.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("");
    return head + `
      <div class="ts-block"><h4>${d.intro}</h4>
        <table class="gp-table"><thead><tr>${d.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="ts-block" style="background:#fdeceb;border-color:#eab9b2"><h4>重要提醒</h4>
        ${d.reminders.map(r => `<p class="ky-remind">⚠ ${r}</p>`).join("")}</div>` + foot;
  }

  /* —— 板块二：考研基本常识（考研到底是什么） —— */
  if (a.section === "考研基本常识") {
    const d = a.data;
    const paras = d.paras.map(p => `<p style="line-height:1.9"><b>${p.b}</b>${p.t}</p>`).join("");
    const diffs = d.diffs.map((x, i) => `<li><b>${x.b}</b>${x.t}</li>`).join("");
    return head + `
      <div class="ts-block"><h4>${d.title}</h4>${paras}
        <p class="muted" style="margin:10px 0 4px">${d.core_label}</p>
        <div class="ky-quote">${d.core_quote}</div></div>
      <div class="ts-block"><h4>${d.diff_title}</h4><ol class="tf-ol ky-diffs">${diffs}</ol></div>` + foot;
  }

  /* —— 板块四：时间线及择校选专业（两个子选项） —— */
  if (a.section === "时间线及择校选专业") {
    const d = a.data;
    if (!KY_TOPIC) KY_TOPIC = d.tabs[0];
    $("ky-sub-bar").classList.remove("hidden");
    $("ky-sub-pills").innerHTML = d.tabs.map(n =>
      `<button class="gp-pill ${n === KY_TOPIC ? "on" : ""}" data-tp="${n}">${n}</button>`).join("");
    document.querySelectorAll("#ky-sub-pills .gp-pill").forEach(p => p.addEventListener("click", () => {
      KY_TOPIC = p.dataset.tp; runKaoyan();
    }));
    if (KY_TOPIC === d.tabs[0]) {           // 考研时间线（以2027年为例）
      const f = d.flow;
      const rows = f.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("");
      return head + `<div class="ts-block"><h4>${f.title}</h4>
        <table class="gp-table"><thead><tr>${f.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>` + foot;
    }
    const tb = (lay) => `<table class="gp-table"><thead><tr>${lay.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead>
      <tbody>${lay.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    const blocks = d.choice.layers.map(lay => {
      if (lay.type === "flow") {            // 决策顺序流程图
        const steps = lay.steps.map((s, i) => `
          <div class="ky-flow-step"><span class="ky-flow-no">${i + 1}</span>
            <div><b>${s.name}</b>${s.desc ? `<p class="muted">${s.desc}</p>` : ""}</div></div>
          ${i < lay.steps.length - 1 ? '<div class="ky-flow-arrow">↓</div>' : ""}`).join("");
        return `<div class="ts-block"><h4>${lay.title}</h4><div class="ky-flow">${steps}</div></div>`;
      }
      if (lay.type === "table") {
        return `<div class="ts-block"><h4>${lay.title}</h4>${tb(lay)}</div>`;
      }
      return `<div class="ts-block"><h4>${lay.title}</h4>
        <ol class="tf-ol ky-diffs">${lay.items.map(x => `<li>${x}</li>`).join("")}</ol>
        ${lay.notes.map(n => `<div class="ky-quote" style="margin-top:6px">${n}</div>`).join("")}</div>`;
    }).join("");
    return head + `<div class="ts-block"><h4>择校选专业三步走：先看顺序，再核数据，最后排查风险</h4></div>
      ${blocks}` + foot;
  }

  /* —— 板块五：录取规则梳理（两个子选项） —— */
  if (a.section === "录取规则梳理") {
    const d = a.data;
    if (!KY_TOPIC) KY_TOPIC = d.tabs[0];
    $("ky-sub-bar").classList.remove("hidden");
    $("ky-sub-pills").innerHTML = d.tabs.map(n =>
      `<button class="gp-pill ${n === KY_TOPIC ? "on" : ""}" data-tp="${n}">${n}</button>`).join("");
    document.querySelectorAll("#ky-sub-pills .gp-pill").forEach(p => p.addEventListener("click", () => {
      KY_TOPIC = p.dataset.tp; runKaoyan();
    }));
    if (KY_TOPIC === d.tabs[0]) {           // 各类分数线
      const ln = d.lines;
      const rows = ln.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("");
      return head + `
        <div class="ts-block"><h4>${ln.title}</h4>
          <table class="gp-table"><thead><tr>${ln.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
        <div class="ts-block" style="background:#fdeceb;border-color:#eab9b2"><h4>重要提醒</h4>
          ${ln.reminders.map(r => `<p class="ky-remind">⚠ ${r}</p>`).join("")}</div>` + foot;
    }
    const sc = d.score;                     // 总成绩计算规则
    return head + `
      <div class="ts-block"><h4>${sc.title}</h4>
        <p style="line-height:1.9">${sc.formula_label}<b>${sc.formula}</b></p>
        <ul class="tf-ul" style="margin-top:8px">${sc.bullets.map(t => `<li>${t}</li>`).join("")}</ul>
        ${sc.quotes.map(q => `<div class="ky-quote" style="margin-top:8px">${q}</div>`).join("")}</div>` + foot;
  }

  /* —— 板块六：查信息防诈骗（三个子选项） —— */
  if (a.section === "查信息防诈骗") {
    const d = a.data;
    if (!KY_TOPIC) KY_TOPIC = d.tabs[0];
    $("ky-sub-bar").classList.remove("hidden");
    $("ky-sub-pills").innerHTML = d.tabs.map(n =>
      `<button class="gp-pill ${n === KY_TOPIC ? "on" : ""}" data-tp="${n}">${n}</button>`).join("");
    document.querySelectorAll("#ky-sub-pills .gp-pill").forEach(p => p.addEventListener("click", () => {
      KY_TOPIC = p.dataset.tp; runKaoyan();
    }));
    if (KY_TOPIC === d.tabs[0]) {           // 查信息：渠道表 + 高频踩坑清单
      const inf = d.info;
      const rows = inf.rows.map(r => `<tr><td class="by-dim">${r[0]}</td><td>${r[1]}</td><td class="ky-url">${r[2]}</td></tr>`).join("");
      return head + `
        <div class="ts-block"><h4>${d.purpose}</h4></div>
        <div class="ts-block"><h4>${inf.title}</h4>
          <table class="gp-table"><thead><tr>${inf.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
        <div class="ts-block"><h4>${inf.pitfalls_title}</h4>
          <ol class="tf-ol ky-diffs">${inf.pitfalls.map(x => `<li>${x}</li>`).join("")}</ol></div>` + foot;
    }
    if (KY_TOPIC === d.tabs[1]) {           // 防诈骗：要点列表
      const an = d.anti;
      return head + `
        <div class="ts-block"><h4>${an.title}</h4>
          <ol class="tf-ol ky-diffs">${an.items.map(x => `<li>${x}</li>`).join("")}</ol></div>` + foot;
    }
    const ac = d.action;                    // 行动清单：可勾选保存
    const done = new Set(KY_ACTIONS);
    let total = 0, doneN = 0;
    const stages = ac.stages.map((st, si) => {
      const items = st.items.map((t, ii) => {
        const key = si + "-" + ii; total++;
        const on = done.has(key); if (on) doneN++;
        return `<label class="ky-act ${on ? "done" : ""}"><input type="checkbox" data-k="${key}" ${on ? "checked" : ""}> ${t}</label>`;
      }).join("");
      return `<div class="ts-block"><h4>✨ ${st.name}</h4><div class="ky-acts">${items}</div></div>`;
    }).join("");
    return head + `
      <div class="ts-block"><h4>${ac.title}</h4>
        <p class="muted" id="ky-act-progress">已完成 ${doneN}/${total} —— 做完一项就打勾，系统自动保存到你的账号，下次登录仍然记得</p></div>
      ${stages}` + foot;
  }

  /* —— 板块三：具体考试内容（3.1~3.5 五小节） —— */
  const d = a.data;
  const tbl = (tb) => `<table class="gp-table"><thead><tr>${tb.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead>
    <tbody>${tb.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="by-dim"' : ""}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const parts = d.parts.map(p => `
    <div class="ts-block"><h4>${p.title}</h4>
      ${p.intro ? `<p class="muted" style="margin-bottom:6px">${p.intro}</p>` : ""}
      ${p.tables.map(tbl).join("")}
      ${p.sub ? `<p class="muted" style="margin:10px 0 4px"><b>${p.sub.title}</b></p>
        <ol class="tf-ol">${p.sub.items.map(s => `<li>${s}</li>`).join("")}</ol>` : ""}
      ${p.note ? `<div class="ky-mis"><b>💡 提示</b>${p.note}</div>` : ""}
    </div>`).join("");
  return head + parts + foot;
}

/* ---------- 出国留学（挂在“目标导向规划 → 出国”下） ---------- */
let SA_MODE = "policy";     // policy=项目检索视图，plan=选课规划视图
let SA_QUERY = "";          // 当前搜索词，空=地区总览

function saProjTable(p) {
  return `<div class="sa-proj">
    <div class="sa-proj-form">${p.form}${p.term ? ` <span class="sa-term">⏱ ${p.term}</span>` : ""}</div>
    <table class="gp-table sa-proj-tb"><tbody>
      <tr><td>派出学院</td><td>${p.colleges || "——"}</td></tr>
      <tr><td>申请专业</td><td>${p.majors || "——"}</td></tr>
      <tr><td><b>选拔要求</b></td><td class="sa-req">${p.req || "以项目公告为准"}</td></tr>
      <tr><td>学校声誉</td><td>${p.rep || "——"}</td></tr>
      ${p.dest ? `<tr><td>学生去向</td><td>${p.dest}</td></tr>` : ""}
    </tbody></table></div>`;
}

function saSchoolCard(s, open) {
  return `<details class="sa-school" ${open ? "open" : ""}>
    <summary>🏛 <b>${s.name}</b><span class="sa-pn">${s.projects.length} 个项目</span></summary>
    ${s.projects.map(saProjTable).join("")}
  </details>`;
}

async function runStudyabroad() {
  const box = $("sa-result");
  const q = SA_QUERY.trim();
  $("btn-sa-clear").classList.toggle("hidden", !q);
  box.innerHTML = '<p class="muted">正在调取北化留学项目库…</p>';
  try {
    const d = await api("/api/studyabroad?query=" + encodeURIComponent(q));
    const a = d.studyabroad;
    let html = `<div class="ts-head by-head">✈️ ${a.meta.title}
      <span class="ts-tag ghost">共 ${a.meta.school_count ?? ""} ${a.meta.school_count ? "所学校 · " : ""}更新至 ${a.meta.updated_at}</span>
      ${q ? "" : `<button id="sa-plan-btn" class="btn-primary btn-sm" style="margin-left:auto">📚 按出国目标生成选课规划</button>`}</div>
      <p class="muted">${a.meta.intro}</p>`;
    if (a.mode === "search") {
      if (!a.results.length) {
        html += `<div class="sa-empty">🔍 未找到与「${q}」匹配的项目。<br>
          试试搜索：<span class="sa-hint">美洲 / 欧洲 / 亚太 / 英国 / 美国 / 新加坡 / 日本</span>，
          或学校名（如 <span class="sa-hint">伯克利、莫纳什、早稻田</span>）、条件（如 <span class="sa-hint">雅思、GPA、交换</span>）。</div>`;
      } else {
        html += `<h4 class="sa-h">搜索「${q}」命中 ${a.results.length} 所学校</h4>`;
        a.results.forEach(s => { html += saSchoolCard(s, true); });
      }
    } else {
      html += `<h4 class="sa-h">可留学地区 · 点击展开该地区全部学校与申请要求</h4>`;
      a.regions.forEach(r => {
        html += `<details class="sa-region"><summary>🌏 <b>${r.name}</b>
          <span class="sa-pn">${r.school_count} 所学校 · ${r.countries.map(c => c.country).join("、")}</span></summary>
          ${r.countries.map(c => `<h4 class="sa-country">${c.country}</h4>
            ${c.schools.map(s => saSchoolCard(s, false)).join("")}`).join("")}
        </details>`;
      });
      html += `<details class="gp-prompt"><summary>📋 申请流程（8步）与项目形式说明</summary>
        <ol class="tf-ol">${a.apply_flow.map(s => `<li>${s}</li>`).join("")}</ol>
        ${a.program_modes.map(p => `<p style="margin:6px 0"><b>${p.form}</b>：${p.desc}<br><span class="muted">申请时间：${p.apply_time}</span></p>`).join("")}
        <p class="muted" style="margin-top:8px">咨询：${Object.entries(a.meta.contacts).map(([k, v]) => `${k} ${v}`).join("　|　")}</p>
        <p class="sa-disc">※ ${a.meta.disclaimer}</p></details>`;
    }
    box.innerHTML = html;
    const pb = document.getElementById("sa-plan-btn");
    if (pb) pb.addEventListener("click", () => { SA_MODE = "plan"; runGoalPlan(); });
    box.querySelectorAll(".sa-hint").forEach(h => h.addEventListener("click", () => {
      SA_QUERY = h.textContent.trim(); $("sa-query").value = SA_QUERY; runStudyabroad();
    }));
  } catch (e) {
    box.innerHTML = `<p class="err">留学项目库调取失败：${e.message}</p>`;
  }
}

$("btn-sa-search").addEventListener("click", () => {
  SA_QUERY = $("sa-query").value; SA_MODE = "policy"; runStudyabroad();
});
$("sa-query").addEventListener("keydown", e => {
  if (e.key === "Enter") { SA_QUERY = e.target.value; SA_MODE = "policy"; runStudyabroad(); }
});
$("btn-sa-clear").addEventListener("click", () => {
  SA_QUERY = ""; $("sa-query").value = ""; runStudyabroad();
});

/* ---------- 转专业分析渲染 ---------- */
function renderTransfer(a) {
  const ch = a.channels.map(c => `<tr><td><b>${c.name}</b></td><td>${c.requirement}</td><td>${c.proof}</td></tr>`).join("");
  const hits = a.eligibility.filter(e => e.hit);
  const el = a.eligibility.map(e => `<li class="${e.hit ? "bad" : ""}">${e.hit ? "✘ " : "☐ "}${e.text}</li>`).join("");
  const df = a.diff;
  let diffHtml = "";
  if (df) {
    const tbl = (arr, cols) => arr.length ? `<table class="gp-table"><thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join("")}</tr></thead>
      <tbody>${arr.map(x => `<tr>${cols.map(c => `<td>${x[c[1]] ?? "-"}</td>`).join("")}</tr>`).join("")}</tbody></table>`
      : '<p class="muted">无</p>';
    diffHtml = `
      <div class="gp-kpis">
        <span>${a.from_major}：<b>${df.from_credit_required}</b> 学分 · ${df.from_degree}</span>
        <span>${a.to_major}：<b>${df.to_credit_required}</b> 学分 · ${df.to_degree}</span>
        <span class="ok">可认定 ${df.shared_required.length} 门 / ${df.shared_credit} 学分</span>
        <span class="bad">需补修 ${df.to_make_required.length} 门 / ${df.to_make_credit} 学分</span>
      </div>
      <details open><summary>✚ 转入后需补修的必修课（${df.to_make_required.length} 门）</summary>
        ${tbl(df.to_make_required, [["课程", "name"], ["学分", "credit"], ["开课学期", "term"]])}</details>
      <details><summary>✔ 两专业都有、可申请学分认定的必修课（${df.shared_required.length} 门）</summary>
        ${tbl(df.shared_required, [["课程", "name"], ["学分", "credit"], ["原方案学期", "term_from"], ["新方案学期", "term_to"]])}</details>
      <details><summary>➖ 转出后不再需要的原必修（${df.from_only_required.length} 门）</summary>
        ${tbl(df.from_only_required, [["课程", "name"], ["学分", "credit"]])}</details>`;
  } else {
    diffHtml = `<p class="bad">⚠ 系统尚未同时收录两个专业的完整培养方案，无法自动对比课程；可先参考已收录专业：${(a.options || []).join("、")}</p>`;
  }
  return `
    <div class="ts-head">🔁 转专业分析：${a.from_major} → <b>${a.to_major}</b>
      ${a.quota != null ? `<span class="ts-tag">本学年该专业可接收 ${a.quota} 人</span>` : ""}
      <span class="ts-tag ghost">依据《${a.source.replace(/[《》]/g, "")}》</span></div>
    ${hits.length ? `<div class="ts-block" style="background:#fdeceb;border-color:#eab9b2"><h4>🚫 你已命中不予考虑情形</h4><ul class="tf-ul bad">${hits.map(h => `<li>${h.text}</li>`).join("")}</ul></div>` : ""}
    <div class="ts-block"><h4>板块一 · 必须达到的要求</h4>
      <p class="muted" style="line-height:1.8">基本条件：${a.basic_conditions.join("；")}</p>
      <p style="font-size:14.5px;margin-top:6px">申请通道（满足其一即可）：</p>
      <table class="gp-table"><thead><tr><th>通道</th><th>要求</th><th>证明材料</th></tr></thead><tbody>${ch}</tbody></table>
      <details class="gp-prompt"><summary>限制情形与不予考虑情形（点开核对）</summary>
        <ul class="tf-ul">${a.restrictions.map(x => `<li>⚠ ${x}</li>`).join("")}${el}</ul></details>
    </div>
    <div class="ts-block"><h4>板块二 · 两个专业培养方案对比</h4>${diffHtml}</div>
    <div class="ts-block"><h4>板块三 · 你需要做的工作（流程时间线）</h4>
      <ol class="tf-ol">${a.process.map(s => `<li>${s}</li>`).join("")}</ol>
      <ul class="tf-ul">${a.notes.map(n => `<li>· ${n}</li>`).join("")}</ul></div>
    <div class="ts-block"><h4>板块四 · 考核准备（定性建议）</h4>
      <p style="font-size:15px;line-height:1.9">转入学院考核通常含笔试+面试（热门院常考数学/专业基础）；准备好专业认知与学习规划陈述。走<b>学业优秀类</b>：守住正考 GPA≥3.0 是第一要务；走<b>兴趣专长类</b>：现在就去修目标专业 MOOC/预修课或打竞赛攒材料。</p></div>
    <p class="muted" style="margin-top:8px">来源：${a.official_basis.join("　|　")}</p>`;
}

/* ---------- 课程图谱 ---------- */
async function loadMajors() {
  try {
    const d = await api("/api/majors");
    const cur = (PROFILE && PROFILE.major) || $("g-sub-major").value || d.majors[0] || "";
    const opts = d.majors.map(m => `<option ${m === cur ? "selected" : ""}>${m}</option>`).join("");
    $("g-sub-major").innerHTML = opts;
    // 镜像控件：各子模块统一从全局选择器取值
    ["major-select", "ts-major", "gp-major"].forEach(id => { $(id).innerHTML = opts; $(id).value = cur; });
    const g = (PROFILE && PROFILE.grade) || "";
    if (g) { $("g-sub-grade").value = g; }
    ["ts-grade", "gp-grade"].forEach(id => { $(id).value = $("g-sub-grade").value; });
    if (!$("g-sub-major")._bound) {
      $("g-sub-major").addEventListener("change", onSubMajorChange);
      $("g-sub-grade").addEventListener("change", onSubMajorChange);
      $("g-sub-major")._bound = true;
    }
  } catch (e) {}
}
function onSubMajorChange() {
  const m = $("g-sub-major").value, g = $("g-sub-grade").value;
  ["major-select", "ts-major", "gp-major"].forEach(id => { $(id).value = m; });
  ["ts-grade", "gp-grade"].forEach(id => { $(id).value = g; });
  // 实时跟进：重绘当前可见子模块
  renderGraph();
  if (isLogged()) loadPlan();
  if (!document.getElementById("sub-ts").classList.contains("hidden")) runTermSchedule();
  if (!document.getElementById("sub-gp").classList.contains("hidden")) {
    if (GP_GOAL === "保研" && BY_MODE === "policy") runBaoyan();
    else if (GP_GOAL === "考研" && KY_MODE === "policy") runKaoyan();
    else if (GP_GOAL === "出国" && SA_MODE === "policy") runStudyabroad();
    else if (GP_GOAL === "就业") runCareer();
    else runGoalPlan();
  }
}

/* ---------- 学业规划板块：四模块并列子标签 ---------- */
document.querySelectorAll(".gsub-tab").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".gsub-tab").forEach(x => x.classList.toggle("on", x === b));
  ["graph", "ts", "gp", "check"].forEach(k =>
    $("sub-" + k).classList.toggle("hidden", k !== b.dataset.sub));
  if (b.dataset.sub === "graph" && graphChart) setTimeout(() => graphChart.resize(), 50);
}));
async function renderGraph() {
  const major = $("major-select").value || (PROFILE && PROFILE.major) || "";
  try {
    const d = await api("/api/graph?major=" + encodeURIComponent(major));
    curNodes = d.nodes;
    renderChecks(d.nodes);
    loadTimetable();
    $("path-result").innerHTML = "";
    // [AI编写] 等待图表库延迟加载完成再初始化（本地化性能优化轮）
    if (typeof echarts === "undefined") {  // 图表库延迟加载：等待就绪再初始化
      await new Promise(res => { const t = setInterval(() => { if (typeof echarts !== "undefined") { clearInterval(t); res(); } }, 40); });
    }
    if (!graphChart) graphChart = echarts.init($("graph-canvas"));
    graphChart.setOption({
      tooltip: { formatter: p => p.data.name ?
        `${p.data.name}<br>${p.data.credit || ""}学分 · ${p.data.semester || ""} · ${p.data.ctype || ""}` : "" },
      legend: { data: ["必修", "选修"], bottom: 8 },
      series: [{
        type: "graph", layout: "force", roam: true, draggable: true,
        categories: [{ name: "必修" }, { name: "选修" }],
        force: { repulsion: 380, edgeLength: 90 },
        label: { show: true, position: "right", fontSize: 11 },
        edgeSymbol: ["none", "arrow"], edgeSymbolSize: 8,
        lineStyle: { color: "#88a99b", curveness: 0.12 },
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        data: d.nodes.map(n => ({ ...n, itemStyle: { color: n.category ? "#e6a23c" : "#1a6b4f" } })),
        links: d.links,
      }],
    });
  } catch (e) { $("graph-canvas").innerHTML = `<p style="padding:20px;color:#c0392b">${e.message}</p>`; }
}
/* ---------- 实时课程表（周课表：周一~周日 · 本学期） ---------- */
async function loadTimetable() {
  const major = $("major-select").value || (PROFILE && PROFILE.major) || "";
  const grade = $("g-sub-grade").value || (PROFILE && PROFILE.grade) || 0;
  try {
    TT_DATA = await api("/api/timetable?major=" + encodeURIComponent(major) + "&grade=" + encodeURIComponent(grade));
    TT_EDIT = null;
    $("tt-editor").classList.add("hidden");
    renderTimetable();
  } catch (e) {
    $("tt-grid").innerHTML = `<p class="bad" style="padding:6px 0">${e.message}</p>`;
  }
}

const ttCovers = (c, period) => period >= (+c.start) && period < (+c.start) + Math.max(1, +c.span || 1);

function renderTimetable() {
  const d = TT_DATA;
  if (!d) return;
  const days = d.config.days, periods = d.config.periods, courses = d.courses || [];
  $("tt-term-label").textContent = d.term.sub ? `${d.term.label} · ${d.term.sub}` : d.term.label;
  $("tt-note").innerHTML = `按周一~周日呈现本学期课程，节次作息取自学校作息表`
    + `（上午 1-5 节 / 下午 6-9 节 / 晚上 10-12 节，课间休息 10 分钟）；`
    + `如学校调整作息，改 <code>data/timetable_config.json</code> 即可。`;

  if (!d.logged_in) {
    const assumed = d.grade_assumed ? `（未填年级，暂按培养方案 ${d.grade} 级推算学期）` : "";
    $("tt-hint").innerHTML = `当前为<b>游客浏览</b>：课表为空框架，下方按培养方案列出本学期课程${assumed}。`
      + ` <a href="javascript:void(0)" id="tt-login-link">登录 / 注册</a> 后可以录入或导入自己的课表。`;
  } else if (!courses.length) {
    $("tt-hint").innerHTML = `这是你的<b>空课表框架</b>：点任意格子可手动添加课程，`
      + `也可用最下方的「教务管理系统导入」。`;
  } else {
    $("tt-hint").innerHTML = `已保存 <b>${courses.length}</b> 门课程：点课程块可删除，点空格子可继续添加。`;
  }

  const head = `<div class="tt-corner" style="grid-row:1;grid-column:1">节次</div>`
    + days.map((x, i) => `<div class="tt-day" style="grid-row:1;grid-column:${i + 2}">${x}</div>`).join("");

  const body = periods.map((p, r) => {
    const rowNo = r + 2;
    const newBlock = p.block && (r === 0 || periods[r - 1].block !== p.block);
    const timeCell = `<div class="tt-time" style="grid-row:${rowNo};grid-column:1">`
      + `${newBlock ? `<i class="tt-block-tag">${esc(p.block)}</i>` : ""}`
      + `${p.label}<span>${p.time}</span></div>`;
    const cells = days.map((_, i) => {
      const day = i + 1;
      if (courses.some(c => +c.day === day && ttCovers(c, p.no))) return "";
      return `<div class="tt-cell" data-day="${day}" data-period="${p.no}" `
        + `style="grid-row:${rowNo};grid-column:${day + 1}"></div>`;
    }).join("");
    return timeCell + cells;
  }).join("");

  const blocks = courses.map((c, idx) => {
    const day = Math.min(7, Math.max(1, +c.day || 1));
    const start = Math.max(1, +c.start || 1);
    const span = Math.max(1, +c.span || 1);
    const sub = [c.teacher, c.room].filter(Boolean).join(" · ");
    return `<div class="tt-block${c.from_plan ? " plan" : ""}" data-idx="${idx}" `
      + `style="grid-column:${day + 1};grid-row:${start + 1} / span ${span}" `
      + `title="${esc(c.name)}${sub ? " · " + esc(sub) : ""}">`
      + `<b>${esc(c.name)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}`
      + `${c.weeks ? `<i>${esc(c.weeks)}</i>` : ""}</div>`;
  }).join("");

  $("tt-grid").innerHTML = head + body + blocks;

  const plan = d.plan_courses || [];
  $("tt-plan-box").classList.toggle("hidden", !plan.length);
  if (plan.length) {
    $("tt-plan-title").textContent = `本学期培养方案课程（${d.term.sub || d.term.label} · 共 ${plan.length} 门 `
      + `${Math.round(plan.reduce((s, c) => s + (+c.credit || 0), 0) * 10) / 10} 学分）`;
    $("tt-plan-list").innerHTML = plan.map(c =>
      `<span class="tt-plan-item"><b>${esc(c.name)}</b>${c.credit}分`
      + `<i class="cc-tag ${c.nature === "必修" ? "req" : "ele"}">${esc(c.nature || "选修")}</i></span>`).join("");
  }
}

function ttOpenEditor(day, period) {
  if (!isLogged()) { showLogin(() => loadTimetable()); return; }
  TT_EDIT = { day, period };
  $("tt-editor-title").textContent = `添加课程 · ${TT_DATA.config.days[day - 1]}第 ${period} 节起`;
  $("tt-f-name").value = ""; $("tt-f-teacher").value = "";
  $("tt-f-room").value = ""; $("tt-f-weeks").value = "";
  $("tt-f-span").value = Math.min(2, TT_DATA.config.periods.length - period + 1);
  $("tt-f-err").textContent = "";
  $("tt-editor").classList.remove("hidden");
  $("tt-f-name").focus();
}

async function ttSaveEditor() {
  if (!TT_EDIT || !TT_DATA) return;
  const name = $("tt-f-name").value.trim();
  if (!name) { $("tt-f-err").textContent = "请填写课程名"; return; }
  const maxSpan = TT_DATA.config.periods.length - TT_EDIT.period + 1;
  const span = Math.max(1, Math.min(maxSpan, Number($("tt-f-span").value) || 1));
  const item = { name, teacher: $("tt-f-teacher").value.trim(), room: $("tt-f-room").value.trim(),
                 weeks: $("tt-f-weeks").value.trim(), day: TT_EDIT.day, start: TT_EDIT.period, span };
  // 同一格已有课 → 覆盖；与之重叠的旧课自动移除，避免课程块叠在一起
  const list = (TT_DATA.courses || []).filter(c => !(+c.day === item.day &&
    item.start < (+c.start) + Math.max(1, +c.span || 1) &&
    (+c.start) < item.start + item.span));
  list.push(item);
  await ttSubmit(list);
}

async function ttSubmit(list, errEl) {
  list.sort((a, b) => (a.day - b.day) || (a.start - b.start));
  try {
    const d = await api("/api/timetable", { method: "POST", body: JSON.stringify({ courses: list }) });
    TT_DATA.courses = d.courses || list;
    TT_EDIT = null;
    $("tt-editor").classList.add("hidden");
    renderTimetable();
    return true;
  } catch (e) { (errEl || $("tt-f-err")).textContent = e.message; return false; }
}

$("tt-grid").addEventListener("click", (e) => {
  const cell = e.target.closest(".tt-cell");
  if (cell) { ttOpenEditor(+cell.dataset.day, +cell.dataset.period); return; }
  const blk = e.target.closest(".tt-block");
  if (!blk) return;
  if (!isLogged()) { showLogin(() => loadTimetable()); return; }
  const c = (TT_DATA.courses || [])[+blk.dataset.idx];
  if (!c) return;
  if (!confirm(`删除《${c.name}》（${TT_DATA.config.days[+c.day - 1]} 第 ${c.start} 节）？`)) return;
  ttSubmit((TT_DATA.courses || []).filter((x, i) => i !== +blk.dataset.idx));
});
$("tt-hint").addEventListener("click", (e) => {
  if (e.target.id === "tt-login-link") { e.preventDefault(); showLogin(() => loadTimetable()); }
});
$("tt-f-save").addEventListener("click", ttSaveEditor);
$("tt-f-cancel").addEventListener("click", () => {
  TT_EDIT = null; $("tt-editor").classList.add("hidden");
});
$("btn-tt-import").addEventListener("click", () => {
  ttToggleImport($("tt-import-panel").classList.contains("hidden"));
});

/* ---------- 课表识别导入：复制粘贴 / 图片识别 ---------- */
let TT_IMPORT_MODE = "text";     // text=粘贴文本，image=截图识别
let TT_IMPORT_IMAGE = "";        // 截图 dataURL
let TT_IMPORT_RESULT = [];       // 识别出来待确认的课程

function ttToggleImport(open) {
  $("tt-import-panel").classList.toggle("hidden", !open);
  if (open) { $("tt-import-msg").textContent = ""; $("tt-import-text").focus(); }
}
function ttSetImportMode(mode) {
  TT_IMPORT_MODE = mode;
  document.querySelectorAll(".tt-itab").forEach(b => b.classList.toggle("on", b.dataset.imode === mode));
  $("tt-ipane-text").classList.toggle("hidden", mode !== "text");
  $("tt-ipane-image").classList.toggle("hidden", mode !== "image");
}
document.querySelectorAll(".tt-itab").forEach(b =>
  b.addEventListener("click", () => ttSetImportMode(b.dataset.imode)));
$("btn-tt-close").addEventListener("click", () => ttToggleImport(false));

$("tt-import-img").addEventListener("change", () => {
  const f = $("tt-import-img").files[0];
  TT_IMPORT_IMAGE = "";
  $("tt-import-preview").innerHTML = "";
  $("tt-import-msg2").textContent = "";
  if (!f) return;
  if (f.size > 8 * 1024 * 1024) { $("tt-import-msg2").textContent = "图片超过 8MB，请压缩后再传"; return; }
  const rd = new FileReader();
  rd.onload = () => {
    TT_IMPORT_IMAGE = rd.result;
    $("tt-import-preview").innerHTML = `<img src="${rd.result}" alt="课表截图预览">`;
  };
  rd.readAsDataURL(f);
});

async function ttRunImport() {
  if (!isLogged()) { showLogin(() => ttRunImport()); return; }
  const text = $("tt-import-text").value;
  if (TT_IMPORT_MODE === "image" && !TT_IMPORT_IMAGE) { $("tt-import-msg2").textContent = "请先选择课表截图"; return; }
  if (TT_IMPORT_MODE === "text" && !text.trim()) { $("tt-import-msg2").textContent = "请先粘贴课表内容"; return; }
  $("tt-import-msg2").textContent = "识别中，请稍候…";
  $("btn-tt-run").disabled = true;
  try {
    const payload = TT_IMPORT_MODE === "image" ? { image: TT_IMPORT_IMAGE } : { text };
    const d = await api("/api/timetable/import", { method: "POST", body: JSON.stringify(payload) });
    TT_IMPORT_RESULT = d.courses || [];
    $("tt-import-msg2").textContent = "";
    ttShowImportResult(d);
  } catch (e) {
    $("tt-import-msg2").textContent = e.message;
  } finally { $("btn-tt-run").disabled = false; }
}

function ttShowImportResult(d) {
  const srcName = { rules: "规则解析", llm: "大模型识别", vision: "图片识别" }[d.source] || d.source;
  const days = TT_DATA ? TT_DATA.config.days : [];
  const box = $("tt-import-result");
  box.classList.remove("hidden");
  box.innerHTML = `
    <p class="muted">识别方式：<b>${esc(srcName)}</b> · 共 <b>${d.count}</b> 门课；请核对后确认导入（会覆盖你现在的课表）</p>
    ${d.need_day ? `<p class="muted">⚠ 复制内容里没有星期信息，请给下面 ${d.need_day} 门课选一下星期</p>` : ""}
    <div class="tt-import-list">${d.courses.map((c, i) => `<span class="tt-plan-item">`
      + (c.day ? `<b class="tt-day-fixed">${esc(days[c.day - 1] || "")}</b>`
               : `<select class="tt-day-pick" data-idx="${i}"><option value="">星期?…</option>`
                 + days.map((x, j) => `<option value="${j + 1}">${x}</option>`).join("") + `</select>`)
      + `<b>${esc(c.name)}</b> 第 ${c.start}${c.span > 1 ? "-" + (c.start + c.span - 1) : ""} 节`
      + `${c.teacher ? " · " + esc(c.teacher) : ""}${c.room ? " · " + esc(c.room) : ""}`
      + `${c.weeks ? " · " + esc(c.weeks) : ""}</span>`).join("")}</div>
    ${(d.warnings || []).length ? `<p class="muted">提示：${d.warnings.map(esc).join("；")}</p>` : ""}
    <button id="btn-tt-confirm" class="btn-primary btn-sm" type="button">确认导入</button>
    <button id="btn-tt-cancel" class="tt-btn-line" type="button">取消</button>`;
  // 星期没识别出来的，用户在预览里点选（文本里确实没有这个信息）
  box.querySelectorAll(".tt-day-pick").forEach(sel => sel.addEventListener("change", () => {
    TT_IMPORT_RESULT[+sel.dataset.idx].day = +sel.value || 0;
  }));
  $("btn-tt-confirm").addEventListener("click", ttConfirmImport);
  $("btn-tt-cancel").addEventListener("click", () => box.classList.add("hidden"));
}

async function ttConfirmImport() {
  if (!TT_IMPORT_RESULT.length) return;
  const missing = TT_IMPORT_RESULT.filter(c => !c.day).length;
  if (missing) {
    $("tt-import-msg2").textContent = `还有 ${missing} 门课没选星期，请先选好星期再导入`;
    return;
  }
  const n = TT_IMPORT_RESULT.length;
  const ok = await ttSubmit(TT_IMPORT_RESULT.slice(), $("tt-import-msg2"));
  if (!ok) return;
  TT_IMPORT_RESULT = [];
  $("tt-import-text").value = "";
  TT_IMPORT_IMAGE = "";
  $("tt-import-preview").innerHTML = "";
  $("tt-import-img").value = "";
  $("tt-import-result").classList.add("hidden");
  ttToggleImport(false);
  $("tt-import-msg").textContent = `✔ 已导入 ${n} 门课程`;
}
$("btn-tt-run").addEventListener("click", ttRunImport);
function renderChecks(nodes) {
  const byTerm = {};
  nodes.forEach(n => { (byTerm[n.term] = byTerm[n.term] || []).push(n); });
  const terms = Object.keys(byTerm).sort((a, b) => a - b);
  $("course-checks").innerHTML = terms.map(t => {
    const cs = byTerm[t].sort((a, b) => (a.category || 0) - (b.category || 0));
    return `<div class="cc-term"><div class="cc-term-h">第 ${t} 学期</div><div class="cc-items">` +
      cs.map(n => `<label class="${n.category ? "cc-ele" : "cc-req"}">
        <input type="checkbox" value="${n.id}">
        <span class="cc-name">${n.name}</span>
        <span class="cc-cred">${n.credit}分</span>
        <b class="cc-tag ${n.category ? "ele" : "req"}">${n.category ? "选修" : "必修"}</b>
      </label>`).join("") + `</div></div>`;
  }).join("");
}
$("btn-check").addEventListener("click", async () => {
  const courses = [...document.querySelectorAll("#course-checks input:checked")].map(i => i.value);
  try {
    const d = await api("/api/check-selection", { method: "POST",
      body: JSON.stringify({ major: $("major-select").value, courses }) });
    $("check-result").innerHTML = d.ok
      ? `<p class="ok">✔ 课表可行：总学分 ${d.total_credit} / 上限 ${d.max_credit}，无先修冲突。</p>`
      : `<p class="bad">✘ 发现 ${d.problems.length} 个问题（总学分 ${d.total_credit ?? "-"}）：</p>`
        + d.problems.map(p => `<p class="bad">· ${p}</p>`).join("");
  } catch (e) { $("check-result").innerHTML = `<p class="bad">${e.message}</p>`; }
});
$("btn-path").addEventListener("click", async () => {
  const course = $("path-input").value.trim();
  if (!course) return;
  try {
    const d = await api("/api/course-path", { method: "POST",
      body: JSON.stringify({ major: $("major-select").value, course }) });
    const chain = d.prereq_chain.map(c => c.name).join(" <span class='arrow'>→</span> ");
    $("path-result").innerHTML = `<div class="path-chain">
      <b>达成《${d.target.name}》的学习路径：</b><br>${chain}
      <br><span class="muted">整条链合计 ${d.total_credit} 学分 · 选中课程后可在图谱中对照学期分布</span></div>`;
    if (graphChart) {  // 高亮路径
      const ids = new Set(d.prereq_chain.map(c => c.code));
      graphChart.setOption({ series: [{ data: curNodes.map(n => ({
        ...n, symbolSize: ids.has(n.id) ? 34 : 18 + n.credit * 3,
        itemStyle: { color: ids.has(n.id) ? "#d9483b" : (n.category ? "#e6a23c" : "#1a6b4f") } })) }] });
    }
  } catch (e) { $("path-result").innerHTML = `<p class="bad">${e.message}</p>`; }
});

/* ---------- 二课（官方规则引擎） ---------- */
let ERKE_RULES = null;

async function loadErkeTypes() {
  try {
    ERKE_RULES = await api("/api/erke/rules");
    $("erke-cat").innerHTML = ERKE_RULES.categories.map(c =>
      `<option value="${c.id}">${c.name}（满分${c.full}）</option>`).join("");
    onCatChange();
    $("erke-cat").addEventListener("change", onCatChange);
    $("erke-rule").addEventListener("change", renderRuleFields);
  } catch (e) {}
}
function curCat() { return ERKE_RULES.categories.find(c => c.id === $("erke-cat").value); }
function curRule() { return curCat().items.find(r => r.id === $("erke-rule").value); }
function onCatChange() {
  const c = curCat();
  $("erke-rule").innerHTML = c.items.map(r =>
    `<option value="${r.id}">${r.article}·${r.title.length > 26 ? r.title.slice(0, 26) + "…" : r.title}（上限${r.cap}）</option>`).join("");
  renderRuleFields();
}
function renderRuleFields() {
  const r = curRule();
  if (!r) return;
  $("erke-rule-desc").textContent = `计分方式：${ruleDesc(r)}`;
  let h = "";
  const needTimes = ["times"].includes(r.kind);
  if (r.kind === "times" && r.role_map) {
    h += `<label>参与身份<select id="f-role">${Object.keys(r.role_map).map(k => `<option>${k}</option>`).join("")}</select></label>`;
  }
  if (needTimes) h += `<label>参加次数<input id="f-times" type="number" min="1" value="1"></label>`;
  if (r.kind === "hours_rate" || r.kind === "hours_threshold" || r.kind === "hours_extra")
    h += `<label>时长（小时）<input id="f-hours" type="number" min="0" step="0.5" value="${r.kind === "hours_threshold" ? 10 : 0}"></label>`;
  if (r.kind === "base_minus") h += `<label>${r.param}<input id="f-param" type="number" min="0" value="0"></label>`;
  if (r.kind === "choice") h += `<label>请选择<select id="f-option">${r.options.map(o => `<option>${o.label}</option>`).join("")}</select></label>`;
  if (r.kind === "level") h += `<label>获奖级别<select id="f-level">${Object.keys(r.levels).map(k => `<option>${k}</option>`).join("")}</select></label>`;
  if ((r.kind === "level" || r.kind === "matrix") && r.group_half)
    h += `<label style="display:flex;align-items:center;gap:6px"><input id="f-group" type="checkbox" style="width:auto"> 集体获奖（按半数计）</label>`;
  if (r.kind === "matrix") {
    h += `<label>赛事级别<select id="f-level">${Object.keys(r.levels).map(k => `<option>${k}</option>`).join("")}</select></label>`;
    h += `<label>获奖等级<select id="f-award">${r.awards.map(a => `<option>${a}</option>`).join("")}</select></label>`;
    if (r.major) h += `<label style="display:flex;align-items:center;gap:6px"><input id="f-major" type="checkbox" style="width:auto"> ${r.major.flag}（本节直接记满${r.major.score}分）</label>`;
  }
  $("erke-fields").innerHTML = h;
}
function ruleDesc(r) {
  switch (r.kind) {
    case "fixed": return `计 ${r.score} 分/项`;
    case "times": return r.role_map ? Object.entries(r.role_map).map(([k, v]) => `${k}每次${v}分`).join("，") + `，上限${r.cap}` : `每次 ${r.per} 分，上限 ${r.cap}`;
    case "hours_rate": return `每${r.unit} ${r.per} 分，上限 ${r.cap}`;
    case "hours_threshold": return `${r.unit}≥${r.threshold} 计 ${r.score} 分，不足不计`;
    case "hours_extra": return `超过 ${r.threshold} 的部分每单位 ${r.per} 分，上限 ${r.cap}`;
    case "base_minus": return `基础 ${r.base} 分，每 1 次${r.param}扣 ${r.deduct} 分`;
    case "choice": return r.options.map(o => `${o.label}=${o.score}分`).join("，");
    case "level": return Object.entries(r.levels).map(([k, v]) => `${k}${v}分`).join("，") + (r.group_half ? "；集体按半数" : "");
    case "matrix": return "按赛事级别×获奖等级查表计分（见分值表），集体按半数";
  }
  return "";
}
$("erke-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!curRule()) return;
  const detail = {};
  const g = (id) => document.getElementById(id);
  if (g("f-role")) detail.role = g("f-role").value;
  if (g("f-times")) detail.times = Number(g("f-times").value);
  if (g("f-hours")) detail.hours = Number(g("f-hours").value);
  if (g("f-param")) detail.param = Number(g("f-param").value);
  if (g("f-option")) detail.option = g("f-option").value;
  if (g("f-level")) detail.level = g("f-level").value;
  if (g("f-award")) detail.award = g("f-award").value;
  if (g("f-group")) detail.group = g("f-group").checked;
  if (g("f-major")) detail.major = g("f-major").checked;
  try {
    // 1) 先把待选图片逐个上传，拿到服务端文件名
    const files = [...(g("erke-img").files || [])];
    const uploaded = [];
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch("/api/erke/upload", { method: "POST", headers: { "X-Session-Token": TOKEN }, body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "图片上传失败");
      uploaded.push(d.name);
    }
    if (uploaded.length > 6) throw new Error("每条记录最多 6 张佐证图片");
    // 2) 再提交记录（携带图片文件名）
    const d = await api("/api/erke", { method: "POST", body: JSON.stringify({
      rule_id: curRule().id, detail, term: $("erke-term").value,
      evidence: $("erke-evid").value, images: uploaded }) });
    $("erke-err").textContent = "";
    $("erke-img").value = ""; renderImgPreview();
    alert(`录入成功，本条原始得分 ${d.score} 分` + (d.images ? `，已保存 ${d.images} 张佐证图片` : ""));
    loadErke();
  } catch (err) { $("erke-err").textContent = err.message; }
});

/* ---------- 佐证图片：选择即预览 ---------- */
let pendingImgs = [];
$("erke-img").addEventListener("change", () => { pendingImgs = [...($("erke-img").files || [])]; renderImgPreview(); });
function renderImgPreview() {
  const box = $("erke-img-preview");
  box.innerHTML = "";
  pendingImgs.forEach(f => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(new Blob([f], { type: f.type }));
    img.onload = () => URL.revokeObjectURL(img.src);
    img.title = f.name;
    box.appendChild(img);
  });
}

/* ---------- 导出记录+图片 zip ---------- */
$("btn-export").addEventListener("click", async () => {
  try {
    const r = await fetch("/api/erke/export", { headers: { "X-Session-Token": TOKEN } });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || "导出失败"); }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    a.download = m ? decodeURIComponent(m[1]) : "二课记录.zip";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  } catch (e) { alert(e.message); }
});
async function loadErke() {
  if (!ERKE_RULES) await loadErkeTypes();
  try {
    const d = await api("/api/erke");
    const s = d.summary;
    $("erke-total-note").textContent = `总分 ${s.total} / ${s.total_full}`;
    $("erke-note").textContent = `${s.note} 规则来源：${s.source}`;
    $("erke-cats").innerHTML = s.categories.map(c => {
      const pct = Math.min(100, c.score / c.full * 100);
      const rulesHtml = c.rules.length ? `<div class="rule-lines">` + c.rules.map(r =>
        `<span class="rule-line">${r.article} ${r.title.length > 18 ? r.title.slice(0, 18) + "…" : r.title}：${r.score}分${r.raw > r.cap ? `（原始${r.raw}，已封顶）` : ""}</span>`).join("") + `</div>` : "";
      return `<div class="cat-card">
        <div class="cat-head"><b>${c.name}</b><span>${c.score} / ${c.full}</span></div>
        <div class="bar"><i style="width:${pct}%"></i></div>
        <div class="cat-sub">基础 ${c.base}（上限${c.base_cap}）· 拓展 ${c.ext}（上限${c.ext_cap}）</div>
        ${rulesHtml}</div>`;
    }).join("");
    $("erke-rows").innerHTML = d.records.map(r =>
      `<tr><td>${esc(r.rule_title || r.rule_id)}<br><span class="muted">${esc(r.term || "")} ${esc(r.evidence || "")}</span></td>
       <td>${fmtDetail(r)}</td><td>${r.category || "-"}</td><td>${r.score ?? "-"}</td>
       <td class="thumb-cell">${(r.images && r.images.length)
         ? r.images.map(n => `<img class="thumb" src="/api/erke/image/${n}" onclick="viewImg('${n}')" title="点击放大">`).join("")
         : '<span class="muted">-</span>'}</td>
       <td><button class="del" onclick="delErke(${r.id})">删除</button></td></tr>`).join("") ||
      `<tr><td colspan="6" class="muted" style="text-align:center;padding:18px">暂无记录，请在左侧录入</td></tr>`;
  } catch (e) {}
}

/* 点击缩略图 → 全屏预览（佐证图片查看/另存即为导出单张） */
function viewImg(name) {
  const mask = document.createElement("div");
  mask.className = "img-modal";
  mask.innerHTML = `<div class="img-modal-box"><img src="/api/erke/image/${name}">
    <div class="img-modal-bar"><a href="/api/erke/image/${name}" download="${name}"
      onclick="event.stopPropagation()">下载原图</a><span>点击空白处关闭</span></div></div>`;
  mask.addEventListener("click", () => mask.remove());
  document.body.appendChild(mask);
}
function fmtDetail(r) {
  const d = r.detail || {};
  const parts = [];
  if (d.times) parts.push(`${d.times}次`);
  if (d.role) parts.push(d.role);
  if (d.hours !== undefined && d.hours !== null) parts.push(`${d.hours}小时`);
  if (d.param !== undefined && d.param !== null && d.param !== 0) parts.push(`${r.rule_article?.includes("青年") ? "缺勤" : "扣减"}${d.param}次`);
  if (d.option) parts.push(d.option);
  if (d.level) parts.push(d.level);
  if (d.award) parts.push(d.award);
  if (d.group) parts.push("集体");
  if (d.major) parts.push("重大赛事");
  return parts.join(" · ");
}
async function delErke(id) { try { await api("/api/erke/" + id, { method: "DELETE" }); loadErke(); } catch (e) {} }

/* ---------- FAQ 与反馈 ---------- */
async function loadFaq() {
  try {
    const d = await api("/api/faq");
    $("faq-list").innerHTML = d.items.map(it =>
      `<div class="faq-item"><div class="faq-q">${esc(it.question)}<span>▾</span></div>
       <div class="faq-a">${esc(it.answer)}</div></div>`).join("");
    document.querySelectorAll(".faq-q").forEach(q =>
      q.addEventListener("click", () => q.parentElement.classList.toggle("open")));
  } catch (e) {}
}
$("fb-send").addEventListener("click", async () => {
  const t = $("fb-text").value.trim();
  if (!t) return;
  try {
    const d = await api("/api/feedback", { method: "POST", body: JSON.stringify({ question: t }) });
    $("fb-msg").textContent = d.msg; $("fb-text").value = "";
    setTimeout(() => $("fb-msg").textContent = "", 4000);
  } catch (e) { $("fb-msg").textContent = e.message; }
});
