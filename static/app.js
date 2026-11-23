/* 售后星 Web GUI —— 原生 JS，全部通过 fetch 调用已有 FastAPI 接口 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  /* ---------- 通用请求 / 提示 ---------- */
  async function api(path, options) {
    var resp = await fetch(path, options);
    var data;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!resp.ok) {
      var detail = data && data.detail ? data.detail : ('请求失败（HTTP ' + resp.status + '）');
      throw new Error(detail);
    }
    return data;
  }

  var toastTimer = null;
  function toast(message, isError) {
    var box = $('toast');
    box.textContent = message;
    box.className = 'toast show' + (isError ? ' error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.className = 'toast'; }, 2800);
  }

  /* ---------- 客服对话 ---------- */
  var messages = $('messages');

  function scrollBottom() { messages.scrollTop = messages.scrollHeight; }

  function tierInfo(tier) {
    if (tier === 'auto_reply') return { cls: 'auto', text: '自动回复' };
    if (tier === 'human_approval') return { cls: 'approval', text: '人工审批' };
    if (tier === 'human_fallback') return { cls: 'fallback', text: '转人工兜底' };
    return { cls: 'intent', text: tier };
  }
  function intentText(intent) {
    return { return: '退货', logistics: '查物流', refund: '退款', unknown: '未识别' }[intent] || intent;
  }

  function appendUser(text, orderId) {
    var wrap = el('div', 'msg user');
    wrap.appendChild(el('div', 'msg-label', '我'));
    var bubble = el('div', 'bubble', text + (orderId ? '\n（订单号：' + orderId + '）' : ''));
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    scrollBottom();
  }

  function renderAnswer(container, text) {
    var parts = String(text || '').split(/(【来源:[^】]*】)/g);
    parts.forEach(function (part) {
      if (!part) return;
      if (part.indexOf('【来源:') === 0) {
        container.appendChild(el('span', 'cite-inline', part));
      } else {
        container.appendChild(document.createTextNode(part));
      }
    });
  }

  function appendBot(data) {
    var wrap = el('div', 'msg bot');
    wrap.appendChild(el('div', 'msg-label', '售后星 · 智能客服'));

    var bubble = el('div', 'bubble');
    var meta = el('div', 'msg-meta');
    var t = tierInfo(data.tier);
    meta.appendChild(el('span', 'badge ' + t.cls, t.text));
    meta.appendChild(el('span', 'badge intent', '意图：' + intentText(data.intent)));
    if (typeof data.intent_confidence === 'number') {
      meta.appendChild(el('span', 'badge intent', '置信度：' + data.intent_confidence.toFixed(2)));
    }
    bubble.appendChild(meta);

    var answer = el('div', 'msg-text');
    renderAnswer(answer, data.answer);
    bubble.appendChild(answer);

    var citations = data.citations || [];
    if (citations.length) {
      var box = el('div', 'citations');
      box.appendChild(el('div', 'citations-title', '答案出处 / 引用（' + citations.length + ' 条）'));
      citations.forEach(function (c) {
        var item = el('div', 'cite-item');
        item.appendChild(el('span', 'sid', '【来源:' + c.source_id + '】 '));
        item.appendChild(el('span', 'snippet', c.snippet));
        box.appendChild(item);
      });
      bubble.appendChild(box);
    } else {
      bubble.appendChild(el('div', 'no-cite', '本回复未附带可核验引用（已按反幻觉策略转人工）'));
    }

    if (data.approval_id) {
      bubble.appendChild(el('div', 'approval-hint',
        '已创建退款审批工单 ' + data.approval_id + '，请在下方「退款审批工单区」人工处理。'));
    }

    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    scrollBottom();
  }

  async function sendChat(text, orderId) {
    if (!text) return;
    var version = $('versionSelect').value;
    var sendBtn = $('sendBtn');
    appendUser(text, orderId);
    sendBtn.disabled = true;
    sendBtn.textContent = '处理中…';
    try {
      var data = await api('/chat?version=' + encodeURIComponent(version), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text, order_id: orderId || null })
      });
      appendBot(data);
      if (data.tier === 'human_approval') {
        $('approvalFilter').value = 'pending';
        await loadApprovals();
      }
    } catch (err) {
      toast('对话失败：' + err.message, true);
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = '发送';
    }
  }

  $('chatForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var text = $('chatInput').value.trim();
    var orderId = $('orderInput').value.trim();
    if (!text) return;
    $('chatInput').value = '';
    $('orderInput').value = '';
    sendChat(text, orderId);
  });

  document.querySelectorAll('.chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      $('chatInput').value = chip.getAttribute('data-text');
      $('chatInput').focus();
    });
  });

  $('clearChatBtn').addEventListener('click', function () {
    messages.innerHTML = '';
    messages.appendChild(el('div', 'empty-state', '还没有消息，输入一条售后咨询开始对话吧。'));
  });

  /* ---------- 退款审批工单区 ---------- */
  function statusText(status) {
    return { pending: '待审批', approved: '已批准', rejected: '已驳回' }[status] || status;
  }

  function renderTickets(tickets) {
    var list = $('ticketList');
    list.innerHTML = '';
    $('approvalHint').textContent = '共 ' + tickets.length + ' 条';
    if (!tickets.length) {
      list.appendChild(el('div', 'empty-state', '当前筛选下暂无工单。发送「退款示例」或点击上方按钮生成。'));
      return;
    }
    tickets.forEach(function (t) {
      var card = el('div', 'ticket ' + t.status);
      var top = el('div', 'ticket-top');
      var left = el('div');
      var idLine = el('div', 'ticket-id');
      idLine.appendChild(document.createTextNode(t.id + '　'));
      idLine.appendChild(el('span', 'status-tag ' + t.status, statusText(t.status)));
      left.appendChild(idLine);
      left.appendChild(el('div', 'ticket-meta',
        '订单：' + (t.order_id || '—') + '　意图：' + intentText(t.intent) + '　创建：' + (t.created_at || '—').replace('T', ' ').slice(0, 19)));
      top.appendChild(left);
      card.appendChild(top);
      card.appendChild(el('div', 'ticket-reason', t.reason));
      if (t.answer) card.appendChild(el('div', 'ticket-answer', t.answer));
      if (t.resolved_at) {
        card.appendChild(el('div', 'ticket-meta', '处理时间：' + t.resolved_at.replace('T', ' ').slice(0, 19)));
      }
      if (t.status === 'pending') {
        var actions = el('div', 'ticket-actions');
        var approve = el('button', 'btn btn-sm btn-approve', '批准');
        approve.setAttribute('data-action', 'approve');
        approve.setAttribute('data-id', t.id);
        var reject = el('button', 'btn btn-sm btn-reject', '驳回');
        reject.setAttribute('data-action', 'reject');
        reject.setAttribute('data-id', t.id);
        actions.appendChild(approve);
        actions.appendChild(reject);
        card.appendChild(actions);
      }
      list.appendChild(card);
    });
  }

  async function loadApprovals() {
    var status = $('approvalFilter').value;
    var path = '/approvals' + (status === 'all' ? '' : '?status=' + encodeURIComponent(status));
    try {
      renderTickets(await api(path));
    } catch (err) {
      toast('加载审批工单失败：' + err.message, true);
    }
  }

  $('ticketList').addEventListener('click', async function (e) {
    var btn = e.target.closest('button[data-action]');
    if (!btn) return;
    var id = btn.getAttribute('data-id');
    var action = btn.getAttribute('data-action');
    btn.disabled = true;
    try {
      var ticket = await api('/approvals/' + encodeURIComponent(id) + '/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: 'Web GUI 人工决策' })
      });
      toast('工单 ' + id + ' 已' + statusText(ticket.status));
      await loadApprovals();
    } catch (err) {
      toast('决策失败：' + err.message, true);
      btn.disabled = false;
    }
  });

  $('refreshApprovalsBtn').addEventListener('click', loadApprovals);
  $('approvalFilter').addEventListener('change', loadApprovals);

  $('genRefundBtn').addEventListener('click', async function () {
    var oid = 'ORD10' + (Math.floor(Math.random() * 40) + 11);
    $('approvalFilter').value = 'pending';
    await sendChat('订单 ' + oid + ' 我要退款，钱什么时候到账', '');
    await loadApprovals();
  });

  /* ---------- 工具白名单 ---------- */
  async function loadTools() {
    try {
      var tools = await api('/tools');
      var list = $('toolList');
      list.innerHTML = '';
      $('toolsCount').textContent = tools.length + ' 个可用';
      tools.forEach(function (tool) {
        var item = el('div', 'tool-item');
        item.appendChild(el('div', 'tool-icon', tool.name.slice(0, 1).toUpperCase()));
        var body = el('div');
        body.appendChild(el('div', 'tool-name', tool.name));
        body.appendChild(el('div', 'tool-desc', tool.description));
        item.appendChild(body);
        list.appendChild(item);
      });
    } catch (err) {
      toast('加载工具白名单失败：' + err.message, true);
    }
  }

  /* ---------- 评测结果 ---------- */
  function fmtPct(x) { return (Number(x) * 100).toFixed(0) + '%'; }
  function fmtMoney4(x) { return '¥' + Number(x).toFixed(4); }
  function fmtMoney6(x) { return '¥' + Number(x).toFixed(6); }

  async function loadHistorical() {
    try {
      var data = await api('/eval/historical');
      var cards = document.querySelectorAll('#historicalMetrics .metric');
      var v1 = data.v1, v2 = data.v2, d = data.delta;

      var c0 = cards[0];
      c0.querySelector('.old').textContent = fmtPct(v1.auto_resolution_rate);
      c0.querySelector('.new').textContent = fmtPct(v2.auto_resolution_rate);
      c0.querySelector('.metric-foot').textContent = '+' + d.auto_resolution_rate_pp + 'pp';

      var c1 = cards[1];
      c1.querySelector('.old').textContent = fmtPct(v1.net_resolution_rate);
      c1.querySelector('.new').textContent = fmtPct(v2.net_resolution_rate);
      c1.querySelector('.metric-foot').textContent = '+' + d.net_resolution_rate_pp + 'pp';

      var c2 = cards[2];
      c2.querySelector('.down').textContent = '-' + (d.ai_cost_reduction * 100).toFixed(0) + '%';
      c2.querySelector('.metric-foot').textContent =
        fmtMoney6(v1.ai_cost_per_ticket) + ' → ' + fmtMoney6(v2.ai_cost_per_ticket);
    } catch (err) {
      toast('加载历史评测结果失败：' + err.message, true);
    }
  }

  function abTable(report) {
    var table = el('table', 'ab-table');
    var head = el('tr');
    ['指标', 'v1', 'v2'].forEach(function (h) { head.appendChild(el('th', '', h)); });
    table.appendChild(head);
    function row(label, v1val, v2val) {
      var tr = el('tr');
      tr.appendChild(el('td', '', label));
      tr.appendChild(el('td', '', v1val));
      tr.appendChild(el('td', '', v2val));
      table.appendChild(tr);
    }
    row('用例数', report.cases, '—');
    row('自动解决率', fmtPct(report.v1.auto_resolution_rate), fmtPct(report.v2.auto_resolution_rate));
    row('净解决率', fmtPct(report.v1.net_resolution_rate), fmtPct(report.v2.net_resolution_rate));
    row('AI 单笔成本', fmtMoney6(report.v1.ai_cost_per_ticket), fmtMoney6(report.v2.ai_cost_per_ticket));
    row('综合单笔成本', fmtMoney4(report.v1.cost_per_ticket), fmtMoney4(report.v2.cost_per_ticket));
    return table;
  }

  $('runAbBtn').addEventListener('click', async function () {
    var btn = $('runAbBtn');
    var hint = $('abHint');
    btn.disabled = true;
    btn.textContent = '评测中…';
    hint.textContent = '正在用 MockLLM 跑 200 条用例…';
    try {
      var report = await api('/eval/ab', { method: 'POST' });
      var box = $('abResult');
      box.innerHTML = '';
      box.appendChild(abTable(report));
      var d = report.delta;
      box.appendChild(el('div', 'ab-delta',
        '差异：自动解决率 +' + d.auto_resolution_rate_pp + 'pp ｜ 净解决率 +' +
        d.net_resolution_rate_pp + 'pp ｜ AI 单笔成本 -' +
        (d.ai_cost_reduction * 100).toFixed(1) + '% ｜ 综合单笔成本 -' +
        (d.total_cost_reduction * 100).toFixed(1) + '%'));
      hint.textContent = '实时评测完成（' + report.cases + ' 条用例）';
      toast('A/B 评测完成');
    } catch (err) {
      hint.textContent = '评测失败：' + err.message;
      toast('A/B 评测失败：' + err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = '运行 A/B 评测（200 条用例）';
    }
  });

  /* ---------- 初始化 ---------- */
  loadTools();
  loadApprovals();
  loadHistorical();
})();
