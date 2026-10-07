// 本文件由团队编写为主；标注 [AI编写] 的段落为开发迭代过程中由 AI（千问工作助理）生成的代码，均已标注。
/* 模拟学业凭据仅本次验证；提交和关闭时清空，不写浏览器存储。 */
let eduDraft = null;
let eduJobId = null, eduPollTimer = null, eduReviewJob = null;
function clearEducationCredentials() {
  $('edu-id').value=''; $('edu-password').value=''; $('edu-challenge').value='';
}
window.addEventListener('pagehide',clearEducationCredentials);
window.addEventListener('pageshow',clearEducationCredentials);
function openPersonalService() {
  const dialog=$('personal-dialog');
  if(!dialog.open){clearEducationCredentials();dialog.showModal();}
  const guest=!isLogged();
  $('personal-account-note').classList.toggle('hidden',!guest);
  $('personal-account-login').classList.toggle('hidden',!guest);
  $('edu-password').disabled=false;
  $('edu-sync-term').value ||= emptyEducation().term;
  if(guest) {
    $('edu-status').textContent='这是可选服务，暂不接入也可继续使用网站。请先登录百花网站，再登录绑定本人的模拟学业账号。';
  } else {
    loadEducation();
  }
}
async function closePersonalService(cancelActive=true) {
  clearEducationCredentials();
  $('edu-password').value=''; $('edu-consent').checked=false;
  $('personal-dialog').close();
}
$('personal-close').addEventListener('click',()=>closePersonalService());
$('personal-later').addEventListener('click',()=>closePersonalService());
$('personal-dialog').addEventListener('cancel',e=>{e.preventDefault();closePersonalService();});
$('personal-account-login').addEventListener('click',async()=>{await closePersonalService();showLogin(openPersonalService);});
document.querySelectorAll('[data-open-personal]').forEach(b=>b.addEventListener('click',openPersonalService));
const stateLabels = {passed:'已通过', enrolled:'在修', failed:'未通过', pending:'待发布', withdrawn:'退课', completed:'已修，通过情况待核对', unknown:'状态未知', not_taken:'未修'};
function emptyEducation() {
  const now = new Date(), year = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear()-1;
  return {term:`${year}-${year+1}-${now.getMonth() >= 7 ? 1 : 2}`, records:[], meetings:[], offerings:[],
    history_complete:false, timetable_complete:false, offerings_complete:false};
}
function resetEducation() {
  if (eduPollTimer) clearTimeout(eduPollTimer);
  eduPollTimer=null; eduJobId=null; eduReviewJob=null; eduDraft=null;
  clearEducationCredentials(); $('edu-consent').checked=false;
  $('edu-job-panel').classList.add('hidden'); $('edu-identity-label').classList.add('hidden');
  $('edu-import').textContent='保存导入数据';
  $('edu-preview-timetable').textContent='';
}
async function loadEducation() {
  try {
    const [status, result] = await Promise.all([api('/api/education/status'), api('/api/education/data')]);
    $('edu-status').textContent = `${status.message}。${status.has_data ? `已启用${status.record_count}条虚构课程记录，学期${status.term}` : '尚未启用个性化服务'}。`;
    $('edu-sync-btn').disabled = false;
    $('edu-password').disabled = false;
    $('edu-challenge').disabled = false;
    $('edu-password').placeholder = '与网站密码不同，仅本次输入';
    $('edu-sync-term').value ||= emptyEducation().term;
    if (eduReviewJob) return; // 切换标签不会覆盖尚未确认的采集预览。
    eduDraft = result.snapshot ? cleanSnapshot(result.snapshot) : emptyEducation();
    $('edu-term').value = eduDraft.term;
    $('edu-complete').checked = eduDraft.history_complete;
    $('edu-timetable-complete').checked = eduDraft.timetable_complete;
    renderEducationRecords();
    await loadDemoGrades(!!result.snapshot?.demo);

  } catch (e) { $('edu-message').textContent=e.message; }
}
function cleanSnapshot(data) {
  return {term:data.term, records:data.records || [], meetings:data.meetings || [], offerings:data.offerings || [],
    history_complete:!!data.history_complete, timetable_complete:!!data.timetable_complete, offerings_complete:!!data.offerings_complete};
}
function renderEducationRecords() {
  $('edu-records').innerHTML = `<table class="tt-table"><thead><tr><th>课程号</th><th>课程</th><th>学分</th><th>数据来源</th><th>核对后的状态</th><th></th></tr></thead><tbody>${(eduDraft?.records || []).map((r,i)=>
    `<tr><td>${esc(r.code || '')}</td><td>${esc(r.name)}</td><td>${esc(r.credit)}</td><td>${esc(r.school_status || (PROFILE?.demo?'虚构演示':'学生录入'))}</td><td><select data-review-state="${i}">${Object.entries(stateLabels).map(([v,label])=>`<option value="${v}"${r.status===v?' selected':''}>${esc(label)}</option>`).join('')}</select></td><td>${eduReviewJob?'采集预览':`<button type="button" data-remove-record="${i}">移出待导入</button>`}</td></tr>`).join('')}</tbody></table>`;
  $('edu-records').querySelectorAll('[data-review-state]').forEach(b=>b.addEventListener('change',()=>{eduDraft.records[Number(b.dataset.reviewState)].status=b.value;}));
  $('edu-records').querySelectorAll('[data-remove-record]').forEach(b=>b.addEventListener('click',()=>{eduDraft.records.splice(Number(b.dataset.removeRecord),1);renderEducationRecords();}));
}
$('edu-sync-form').addEventListener('submit',async e=>{
  e.preventDefault();
  if(!isLogged()){clearEducationCredentials();$('edu-message').textContent='请先登录百花网站';return;}
  const payload=JSON.stringify({username:$('edu-id').value.trim(),password:$('edu-password').value,consent:$('edu-consent').checked});
  clearEducationCredentials();$('edu-consent').checked=false;$('edu-sync-btn').disabled=true;
  try {
    const d=await api('/api/demo/login',{method:'POST',body:payload});
    $('edu-message').textContent=d.message;
    await closePersonalService(false);switchTab('education');
    await loadEducation();await loadPlan();await eduLoadTimetable();
    if(ERKE_RULES)await loadErke();
  }catch(e){$('edu-message').textContent=e.message;}
  finally{clearEducationCredentials();$('edu-sync-btn').disabled=false;}
});
async function loadDemoGrades(enabled){
  $('demo-logout').classList.toggle('hidden',!enabled);
  if(!enabled){$('demo-grades').textContent='';return;}
  const d=await api('/api/demo/data');
  const labels={cumulative_regular:'累计正考GPA',term_regular:'学期正考GPA',highest:'最高成绩GPA'};
  const exam={regular:'正考',makeup:'补考',retake:'重修'};
  $('demo-grades').innerHTML='<h3>我的成绩与绩点 · 全部虚构</h3><p class="muted">'+esc(d.grades.rule)+'</p>'+d.grades.gpa.map(g=>`<span class="demo-gpa">${esc(labels[g.scope])} ${esc(g.term==='ALL'?'':g.term)}：<b>${g.gpa==null?'暂无成绩':g.gpa.toFixed(2)}</b></span>`).join('')+
    '<details><summary>展开历次成绩（保留重修前记录）</summary><table class="tt-table"><thead><tr><th>学期</th><th>课程</th><th>学分</th><th>考试类型</th><th>状态</th><th>成绩</th><th>绩点</th></tr></thead><tbody>'+d.grades.records.map(r=>`<tr><td>${esc(r.term)}</td><td>${esc(r.name)}</td><td>${r.credits}</td><td>${exam[r.exam_type]}</td><td>${stateLabels[r.status]}</td><td>${r.score??'未出成绩'}</td><td>${r.grade_point==null?(r.gpa_included?'—':'不计GPA'):r.grade_point.toFixed(2)}</td></tr>`).join('')+'</tbody></table></details>';
}
$('demo-logout').addEventListener('click',async()=>{
  try{await api('/api/demo/logout',{method:'POST'});resetEducation();await loadEducation();await loadPlan();await eduLoadTimetable();if(ERKE_RULES)await loadErke();}
  catch(e){$('edu-message').textContent=e.message;}
});
$('edu-skip').addEventListener('click',()=>{resetEducation();switchTab('home');});
$('edu-record-form').addEventListener('submit', e=>{
  e.preventDefault(); eduDraft ||= emptyEducation();
  if(eduReviewJob){$('edu-message').textContent='请先确认或取消本次采集，再手动添加课程';return;}
  eduDraft.records.push({code:$('edu-code').value.trim(),name:$('edu-name').value.trim(),credit:Number($('edu-credit').value),status:$('edu-state').value,term:$('edu-term').value});
  renderEducationRecords(); e.target.reset();
});
$('edu-file').addEventListener('change',async e=>{
  try {
    if(eduReviewJob)throw new Error('请先确认或取消本次采集，再导入文件');
    const file=e.target.files[0]; if(!file)return;
    if(file.size>2*1024*1024)throw new Error('导入文件不能超过2MB');
    const raw=JSON.parse(await file.text());
    eduDraft=cleanSnapshot(raw.snapshot || raw);
    if(!Array.isArray(eduDraft.records)||!Array.isArray(eduDraft.meetings)||!Array.isArray(eduDraft.offerings))throw new Error('记录和课表必须为数组');
    $('edu-term').value=eduDraft.term || ''; $('edu-complete').checked=eduDraft.history_complete;
    renderEducationRecords(); $('edu-message').textContent='文件已读入待导入区；核对并授权后才保存';
  } catch(err){$('edu-message').textContent='无法读取：'+err.message;}
  finally { e.target.value=''; }
});
function downloadEducation(data,name) {
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
$('edu-template').addEventListener('click',()=>downloadEducation(emptyEducation(),'教务数据空白模板.json'));
$('edu-export').addEventListener('click',async()=>{
  try {const d=await api('/api/education/data'); if(!d.snapshot)throw new Error('尚无保存的数据');downloadEducation(d.snapshot.demo?await api('/api/demo/data'):cleanSnapshot(d.snapshot),'我的学业数据.json');}
  catch(e){$('edu-message').textContent=e.message;}
});
$('edu-import').addEventListener('click',async()=>{
  if(!$('edu-import-consent').checked){$('edu-message').textContent='请先同意保存数据';return;}
  if(!eduDraft){$('edu-message').textContent='请先导入或添加记录';return;}
  eduDraft.term=$('edu-term').value.trim();eduDraft.history_complete=$('edu-complete').checked;
  eduDraft.timetable_complete=$('edu-timetable-complete').checked;
  const path='/api/education/import';
  try {const d=await api(path,{method:'POST',body:JSON.stringify({snapshot:eduDraft,consent:true,...(eduReviewJob?{identity_confirmed:true}:{})})});$('edu-message').textContent=d.message;eduReviewJob=null;eduJobId=null;$('edu-import').textContent='保存导入数据';$('edu-identity-label').classList.add('hidden');$('edu-preview-timetable').textContent='';renderEducationRecords();await loadPlan();await eduLoadTimetable();}
  catch(e){$('edu-message').textContent=e.message;}
});
$('edu-clear').addEventListener('click',async()=>{
  if(!confirm('退出当前个性化服务并清除个人数据展示？演示数据库仍保留，可以重新登录启用。'))return;
  try {const d=await api('/api/education/data',{method:'DELETE'});$('edu-message').textContent=d.message;resetEducation();await loadEducation();await loadPlan();await eduLoadTimetable();}
  catch(e){$('edu-message').textContent=e.message;}
});
// [AI编写] 隔离改名：原函数名 loadTimetable，为避免覆盖本站课表函数由 AI 重命名并加空值守卫（合并轮）
async function eduLoadTimetable() {
  const __box=$('timetable-result'); if(!__box) return;
  const box=$('timetable-result');
  if(!isLogged()){box.innerHTML='<p class="muted">在个性化服务窗口登录模拟学业账号后显示演示课程表。</p>';return;}
  try {
    const d=await api('/api/education/timetable?week='+($('timetable-week').value || 1));
    if(!d.has_data){box.textContent=d.message;return;}
    const rows=d.meetings || [], max=Math.max(12,...rows.map(m=>m.end));
    const days=['一','二','三','四','五','六','日'];
    let html=`<p class="muted">${esc(d.term)} · 第${d.week}周 · ${d.source==='competition_demo'?'竞赛演示数据，全部虚构':d.source==='official_connector'?'教务连接同步':d.source==='school_page_reviewed'?'学校页面采集，本人核对':'学生导入，待在线核验'} · ${d.complete?'本人已声明课表完整':'课表完整性待核对'}</p>`;
    html+='<table class="timetable"><thead><tr><th>节次</th>'+days.map(day=>`<th>周${day}</th>`).join('')+'</tr></thead><tbody>';
    for(let period=1;period<=max;period++){
      html+=`<tr><th>第${period}节</th>`;
      for(let day=1;day<=7;day++)html+='<td>'+rows.filter(m=>m.day===day&&m.start<=period&&m.end>=period).map(m=>`<div class="timetable-course">${esc(m.name)}<br>${m.start}—${m.end}节<br>${esc(m.room)} ${esc(m.campus)}${m.section_id?'<br>教学班 '+esc(m.section_id):''}</div>`).join('')+'</td>';
      html+='</tr>';
    }
    html+='</tbody></table>';
    html+=(d.conflicts || []).map(c=>`<p class="bad">${esc(c.a)}与${esc(c.b)}：周${days[c.day-1]}，重叠周次${c.weeks.join('、')}</p>`).join('');
    if(!rows.length)html+='<p class="muted">本周没有已导入的课程；不代表无需上课，请检查周次和数据完整性。</p>';
    box.innerHTML=html;
  }catch(e){box.textContent=e.message;}
}
$('timetable-refresh') && $('timetable-refresh').addEventListener('click',eduLoadTimetable);
document.querySelectorAll('[data-go-education]').forEach(b=>b.addEventListener('click',openPersonalService));

