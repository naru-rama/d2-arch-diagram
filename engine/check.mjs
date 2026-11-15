import puppeteer from '/opt/aws-diagram/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';

const [file, png, flow] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage();
await page.goto('file://' + file);
const result = await page.evaluate((flow) => {
    const MARGIN = 2;
    const HUG_DIST = 12;
    const HUG_LEN = 30;
    const STEP = 2;

    // awsdiag.py は要素の ID を Base64 にしてクラス名の先頭に入れる

    const decode = (s) => {
      try {
        return new TextDecoder().decode(Uint8Array.from(atob(s), (c) => c.charCodeAt(0)))
          .replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&');
      } catch {
        return null;
      }
    };
    const box = (el) => {
      const b = el.getBBox();
      if (el.tagName === 'image') {
        const side = Math.min(b.width, b.height);
        const x = b.x + (b.width - side) / 2;
        const y = b.y + (b.height - side) / 2;
        return { x1: x, y1: y, x2: x + side, y2: y + side };
      }
      return { x1: b.x, y1: b.y, x2: b.x + b.width, y2: b.y + b.height };
    };
    const inflate = (b, m) => ({ x1: b.x1 - m, y1: b.y1 - m, x2: b.x2 + m, y2: b.y2 + m });
    const inside = (p, b) => p.x > b.x1 && p.x < b.x2 && p.y > b.y1 && p.y < b.y2;
    const overlap = (a, b) => a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
    const crossesBorder = (t, r) => overlap(t, r) && !(t.x1 >= r.x1 && t.x2 <= r.x2 && t.y1 >= r.y1 && t.y2 <= r.y2);

    const nodes = {};
    const containers = {};
    const edges = [];
    const texts = [];

    for (const g of document.querySelectorAll('g[class]')) {
      const [first, ...rest] = g.getAttribute('class').split(' ');
      const id = decode(first);
      if (!id) continue;
      const text = g.querySelector(':scope > text');
      if (rest.includes('group')) {
        const rect = g.querySelector('rect');
        const c = { id, rect: box(rect), kinds: rest };
        const icon = g.querySelector(':scope > image');
        if (icon) c.icon = box(icon);
        if (text) {
          c.label = box(text);
          texts.push({ owner: id, kind: 'group', name: text.textContent, b: c.label });
        }
        containers[id] = c;
      } else if (rest.includes('svc')) {
        const icon = g.querySelector('image');
        const n = { id, icon: icon ? box(icon) : null };
        if (text) {
          n.label = box(text);
          texts.push({ owner: id, kind: 'node', name: text.textContent, b: n.label });
        }
        nodes[id] = n;
      } else if (id.includes('->')) {
        const m = id.match(/^(?:(.*)\.)?\((.*) -> (.*)\)\[\d+\]$/);
        if (!m) continue;
        const prefix = m[1] ? m[1] + '.' : '';
        const path = g.querySelector('path.connection');
        const len = path.getTotalLength();
        const pts = [];
        for (let l = 0; l <= len; l += STEP) pts.push(path.getPointAtLength(l));
        const tokens = path.getAttribute('d').match(/[MLSCQ]|-?[\d.]+/g);
        const corners = [];
        let cmd = null;
        let cur = null;
        let prev = null;
        for (let i = 0; i < tokens.length;) {
          if ('MLSCQ'.includes(tokens[i])) { cmd = tokens[i]; i++; continue; }
          const size = { M: 2, L: 2, S: 4, Q: 4, C: 6 }[cmd];
          const v = tokens.slice(i, i + size).map(Number);
          if (cmd === 'M') { cur = { x: v[0], y: v[1] }; prev = cur; }
          else if (cmd === 'L') { cur = { x: v[0], y: v[1] }; }
          else if (cmd === 'S') { corners.push({ x: v[0], y: v[1] }); prev = corners[corners.length - 1]; cur = { x: v[2], y: v[3] }; }
          else if (cmd === 'Q') { corners.push({ x: v[0], y: v[1] }); prev = corners[corners.length - 1]; cur = { x: v[2], y: v[3] }; }
          else {
            const end = { x: v[4], y: v[5] };
            if (prev && prev.y === cur.y) {
              const mid = (cur.x + end.x) / 2;
              corners.push({ x: mid, y: cur.y }, { x: mid, y: end.y });
            } else {
              const mid = (cur.y + end.y) / 2;
              corners.push({ x: cur.x, y: mid }, { x: end.x, y: mid });
            }
            prev = corners[corners.length - 1];
            cur = end;
          }
          i += size;
        }
        const e = { id, src: prefix + m[2], dst: prefix + m[3], pts, corners };
        if (text) {
          e.label = box(text);
          texts.push({ owner: id, kind: 'edge', name: text.textContent, b: e.label });
        }
        edges.push(e);
      }
    }

    const ancestors = (id) => Object.keys(containers).filter((c) => id.startsWith(c + '.'));
    const issues = [];
    const add = (type, detail) => issues.push({ type, detail });
    const short = (id) => id.split('.').pop();

    for (const e of edges) {
      const name = e.label ? texts.find((t) => t.owner === e.id).name : `${short(e.src)}→${short(e.dst)}`;
      const body = e.pts.slice(3, -3);

      for (const t of texts) {
        if (t.owner === e.id) continue;
        if (body.some((p) => inside(p, inflate(t.b, MARGIN)))) add('矢印が文字を貫く', `${name} × 「${t.name}」`);
      }
      for (const n of Object.values(nodes)) {
        if (!n.icon || n.id === e.src || n.id === e.dst) continue;
        if (body.some((p) => inside(p, inflate(n.icon, -1)))) add('矢印がアイコンを貫く', `${name} × ${short(n.id)}`);
      }
      for (const c of Object.values(containers)) {
        if (c.icon && body.some((p) => inside(p, c.icon))) add('矢印がアイコンを貫く', `${name} × 枠 ${short(c.id)}`);

        const r = c.rect;
        const lines = [
          { d: (p) => Math.abs(p.y - r.y1), on: (p) => p.x >= r.x1 && p.x <= r.x2 },
          { d: (p) => Math.abs(p.y - r.y2), on: (p) => p.x >= r.x1 && p.x <= r.x2 },
          { d: (p) => Math.abs(p.x - r.x1), on: (p) => p.y >= r.y1 && p.y <= r.y2 },
          { d: (p) => Math.abs(p.x - r.x2), on: (p) => p.y >= r.y1 && p.y <= r.y2 },
        ];
        for (const line of lines) {
          let run = 0;
          let longest = 0;
          for (const p of body) {
            run = line.on(p) && line.d(p) < HUG_DIST ? run + STEP : 0;
            longest = Math.max(longest, run);
          }
          if (longest >= HUG_LEN) add('矢印が枠線に沿っている', `${name} × 枠 ${short(c.id)}（${longest}px）`);
        }

        const needed = ancestors(e.src).includes(c.id) !== ancestors(e.dst).includes(c.id) || c.id === e.src || c.id === e.dst ? 1 : 0;
        let crossings = 0;
        for (let i = 1; i < e.pts.length; i++) {
          if (inside(e.pts[i - 1], r) !== inside(e.pts[i], r)) crossings++;
        }
        if (crossings > needed) add('矢印が余計な枠に出入りする', `${name} × 枠 ${short(c.id)}（${crossings} 回）`);
      }
    }

    for (const e of edges) {
      const name = e.label ? texts.find((t) => t.owner === e.id).name : `${short(e.src)}→${short(e.dst)}`;
      const first = e.pts[0];
      const last = e.pts[e.pts.length - 1];
      const poly = [first, ...e.corners, last];
      const diagonal = poly.slice(1).some((p, i) => Math.abs(p.x - poly[i].x) > 0.5 && Math.abs(p.y - poly[i].y) > 0.5);
      if (diagonal) add('矢印が斜め', name);
    }
    for (const e of edges) {
      if (!e.label) continue;
      const name = texts.find((t) => t.owner === e.id).name;
      if (e.corners.some((p) => inside(p, inflate(e.label, 10)))) add('ラベルが曲がり角にかかる', `「${name}」`);
    }
    const axisAt = (e) => {
      const c = { x: (e.label.x1 + e.label.x2) / 2, y: (e.label.y1 + e.label.y2) / 2 };
      const near = e.pts.filter((p) => Math.hypot(p.x - c.x, p.y - c.y) < 20);
      if (near.length < 2) return null;
      const dx = Math.abs(near[near.length - 1].x - near[0].x);
      const dy = Math.abs(near[near.length - 1].y - near[0].y);
      return dx >= dy ? 'h' : 'v';
    };
    const labeledAll = edges.filter((e) => e.label);
    const fanOut = new Set(labeledAll.filter((e) => labeledAll.some((o) => o !== e && o.src === e.src)));
    for (const key of ['src', 'dst']) {
      const labeled = key === 'src' ? labeledAll : labeledAll.filter((e) => !fanOut.has(e));
      for (let i = 0; i < labeled.length; i++) {
        for (let j = i + 1; j < labeled.length; j++) {
          const a = labeled[i];
          const b = labeled[j];
          if (a[key] !== b[key] || axisAt(a) !== axisAt(b)) continue;
          const dx = Math.abs((a.label.x1 + a.label.x2) / 2 - (b.label.x1 + b.label.x2) / 2);
          const dy = Math.abs((a.label.y1 + a.label.y2) / 2 - (b.label.y1 + b.label.y2) / 2);
          if (dx > 2 && dy > 2) {
            const na = texts.find((t) => t.owner === a.id).name;
            const nb = texts.find((t) => t.owner === b.id).name;
            add('ラベルの位置がそろっていない', `「${na}」と「${nb}」`);
          }
        }
      }
    }
    for (const n of Object.values(nodes)) {
      for (const c of Object.values(containers)) {
        const header = [c.icon, c.label].filter(Boolean);
        if (header.some((h) => [n.icon, n.label].filter(Boolean).some((b) => overlap(b, h)))) {
          add('ノードが枠の見出しに重なる', `${short(n.id)} × 枠 ${short(c.id)}`);
        }
      }
    }

    const ports = {};
    for (const e of edges) {
      for (const [id, p] of [[e.src, e.pts[0]], [e.dst, e.pts[e.pts.length - 1]]]) {
        const n = nodes[id];
        if (!n || !n.icon) continue;
        const b = n.icon;
        const side = p.x <= b.x1 + 4 ? 'left' : p.x >= b.x2 - 4 ? 'right' : p.y <= b.y1 + 4 ? 'top' : 'bottom';
        const along = side === 'left' || side === 'right' ? p.y : p.x;
        (ports[`${id}|${side}`] ||= []).push(along);
      }
    }
    for (const [key, list] of Object.entries(ports)) {
      if (list.length < 2) continue;
      const [id, side] = key.split('|');
      const b = nodes[id].icon;
      const center = side === 'left' || side === 'right' ? (b.y1 + b.y2) / 2 : (b.x1 + b.x2) / 2;
      const mean = list.reduce((a, v) => a + v, 0) / list.length;
      const sorted = [...list].sort((a, v) => a - v);
      const gap = Math.min(...sorted.slice(1).map((v, i) => v - sorted[i]));
      if (Math.abs(mean - center) > 6) add('接続位置が偏っている', `${short(id)} の${side}（中心から ${Math.round(mean - center)}px）`);
      if (gap < 8) add('接続位置が近すぎる', `${short(id)} の${side}（${Math.round(gap)}px）`);
    }

    for (let i = 0; i < texts.length; i++) {
      for (let j = i + 1; j < texts.length; j++) {
        if (overlap(texts[i].b, texts[j].b)) add('文字どうしが重なる', `「${texts[i].name}」×「${texts[j].name}」`);
      }
    }
    for (const t of texts) {
      if (t.kind === 'group') continue;
      for (const c of Object.values(containers)) {
        if (crossesBorder(inflate(t.b, MARGIN), c.rect)) add('文字が枠線にかかる', `「${t.name}」× 枠 ${short(c.id)}`);
      }
    }

    let crossings = 0;
    for (let i = 0; i < edges.length; i++) {
      for (let j = i + 1; j < edges.length; j++) {
        const a = edges[i];
        const b = edges[j];
        const shared = [a.src, a.dst].filter((id) => id === b.src || id === b.dst)
          .map((id) => nodes[id] && nodes[id].icon && inflate(nodes[id].icon, 16)).filter(Boolean);
        const near = a.pts.filter((p) => !shared.some((s) => inside(p, s)) && b.pts.some((q) => Math.hypot(p.x - q.x, p.y - q.y) < 1.5));
        if (!near.length) continue;
        const na = a.label ? texts.find((t) => t.owner === a.id).name : `${short(a.src)}→${short(a.dst)}`;
        const nb = b.label ? texts.find((t) => t.owner === b.id).name : `${short(b.src)}→${short(b.dst)}`;
        if (near.length >= 8) add('矢印どうしが重なる', `${na} × ${nb}`);
        else {
          add('矢印どうしが交差する', `${na} × ${nb}`);
          crossings++;
        }
      }
    }

    const mid = (b) => ({ x: (b.x1 + b.x2) / 2, y: (b.y1 + b.y2) / 2 });
    const edgeName = (e) => (e.label ? texts.find((t) => t.owner === e.id).name : `${short(e.src)}→${short(e.dst)}`);
    const placed = Object.values(nodes).filter((n) => n.icon);
    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        const a = mid(placed[i].icon);
        const b = mid(placed[j].icon);
        const pair = `${short(placed[i].id)} と ${short(placed[j].id)}`;
        const dx = Math.abs(a.x - b.x);
        const dy = Math.abs(a.y - b.y);
        if (dx > 1.5 && dx < 12) add('ほぼそろっているがずれている', `${pair} の横位置（${dx.toFixed(1)}px）`);
        if (dy > 1.5 && dy < 12) add('ほぼそろっているがずれている', `${pair} の縦位置（${dy.toFixed(1)}px）`);
      }
    }

    const parentOf = (id) => (id.includes('.') ? id.slice(0, id.lastIndexOf('.')) : '');
    const kindOf = (c) => c.kinds.filter((k) => k !== 'group').sort().join(' ');
    const allIds = [...Object.keys(nodes), ...Object.keys(containers)];
    const innerOf = (c) => allIds.filter((id) => id.startsWith(c.id + '.')).map((id) => id.slice(c.id.length + 1)).sort().join('|');
    const anchorOf = (id) => (nodes[id] && nodes[id].icon ? mid(nodes[id].icon) : containers[id] ? mid(containers[id].rect) : null);
    const buckets = {};
    for (const c of Object.values(containers)) {
      const inner = innerOf(c);
      if (inner) (buckets[`${parentOf(c.id)}#${kindOf(c)}#${inner}`] ||= []).push(c);
    }
    for (const group of Object.values(buckets)) {
      if (group.length < 2) continue;
      const row = new Set(group.map((c) => Math.round(c.rect.y1))).size === 1;
      const members = [...group].sort((a, b) => (row ? a.rect.x1 - b.rect.x1 : a.rect.y1 - b.rect.y1));
      const first = members[0];
      const size = (c) => ({ w: c.rect.x2 - c.rect.x1, h: c.rect.y2 - c.rect.y1 });
      for (const m of members.slice(1)) {
        const aligned = row ? Math.abs(m.rect.y1 - first.rect.y1) <= 2 : Math.abs(m.rect.x1 - first.rect.x1) <= 2;
        if (Math.abs(size(m).w - size(first).w) > 2 || Math.abs(size(m).h - size(first).h) > 2 || !aligned) {
          add('対になる枠の大きさや位置がそろっていない', `${short(first.id)} と ${short(m.id)}`);
        }
      }
      const mapTo = (m, id) => (id.startsWith(first.id + '.') ? m.id + id.slice(first.id.length) : id);
      for (const n of placed) {
        if (!n.id.startsWith(first.id + '.')) continue;
        for (const m of members.slice(1)) {
          const t = nodes[mapTo(m, n.id)];
          if (!t || !t.icon) continue;
          const pa = mid(n.icon);
          const pb = mid(t.icon);
          if (Math.abs(pa.x - first.rect.x1 - (pb.x - m.rect.x1)) > 2 || Math.abs(pa.y - first.rect.y1 - (pb.y - m.rect.y1)) > 2) {
            add('対になる位置がそろっていない', `${short(n.id)}（${short(m.id)}）`);
          }
        }
      }
      const compare = (a, b, move) => {
        const moved = a.pts.map(move);
        const off = moved.filter((p) => !b.pts.some((q) => Math.hypot(p.x - q.x, p.y - q.y) < 3)).length;
        if (off > moved.length * 0.05) add('対になる矢印が対称でない', `${edgeName(a)} と ${edgeName(b)}`);
      };
      for (const e of edges) {
        const inFirst = [e.src, e.dst].map((id) => id.startsWith(first.id + '.'));
        if (!inFirst.some(Boolean)) continue;
        const twins = members.map((m) => edges.find((o) => o.src === mapTo(m, e.src) && o.dst === mapTo(m, e.dst)));
        if (twins.some((t) => !t)) continue;
        if (inFirst.every(Boolean)) {
          members.slice(1).forEach((m, k) => compare(e, twins[k + 1], (p) => ({ x: p.x + m.rect.x1 - first.rect.x1, y: p.y + m.rect.y1 - first.rect.y1 })));
          continue;
        }
        const shared = anchorOf(inFirst[0] ? e.dst : e.src);
        if (!shared) continue;
        const n = members.length;
        for (let i = 0; i < Math.floor(n / 2); i++) {
          const a = members[i];
          const b = members[n - 1 - i];
          const axis = row ? (mid(a.rect).x + mid(b.rect).x) / 2 : (mid(a.rect).y + mid(b.rect).y) / 2;
          if (Math.abs((row ? shared.x : shared.y) - axis) > 2) continue;
          const flip = row ? (p) => ({ x: 2 * axis - p.x, y: p.y }) : (p) => ({ x: p.x, y: 2 * axis - p.y });
          // 枠の中の並びが鏡写しでない対（両端の位置が写し合わない）は比べない
          const ends = (e) => [e.pts[0], e.pts[e.pts.length - 1]];
          if (ends(twins[i]).map(flip).some((p, k) => Math.hypot(p.x - ends(twins[n - 1 - i])[k].x, p.y - ends(twins[n - 1 - i])[k].y) > 3)) continue;
          compare(twins[i], twins[n - 1 - i], flip);
        }
      }
    }

    for (const e of edges) {
      const s = nodes[e.src] && nodes[e.src].icon && mid(nodes[e.src].icon);
      const d = nodes[e.dst] && nodes[e.dst].icon && mid(nodes[e.dst].icon);
      // 矢印の先が向く向きで判断する（下から回り込んで横から入る線は逆向きに見えない）
      const tip = e.pts[e.pts.length - 1];
      const before = [...e.corners].reverse().find((p) => Math.hypot(p.x - tip.x, p.y - tip.y) > 1) || e.pts[0];
      const back = flow === 'down' ? tip.y < before.y - 1 && Math.abs(tip.x - before.x) < 1 : tip.x < before.x - 1 && Math.abs(tip.y - before.y) < 1;
      if (s && d && back) add('流れと逆向きの矢印', edgeName(e));
      if (e.corners.length > 2) add('曲がりが多い', `${edgeName(e)}（${e.corners.length} 回）`);
    }

    const vb = document.querySelector('svg').viewBox.baseVal;
    return { issues, width: Math.round(vb.width), height: Math.round(vb.height) };
  }, flow);

await page.setViewport({ width: result.width, height: result.height, deviceScaleFactor: 2 });
await (await page.$('svg')).screenshot({ path: png });
await browser.close();
process.stdout.write(JSON.stringify(result));
