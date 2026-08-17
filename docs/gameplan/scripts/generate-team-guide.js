const fs=require('fs');
const src=fs.readFileSync('rebuild.js','utf8');
const K=eval('('+src.slice(src.indexOf('const K={')+8, src.indexOf('// price, depot stock')).trim().replace(/;$/,'')+')');
const P=eval('('+src.slice(src.indexOf('const P={')+8, src.indexOf('const GROUPS=')).trim().replace(/;$/,'')+')');
const GROUPS=eval('('+src.slice(src.indexOf('const GROUPS=')+13, src.indexOf('const FURN=')).trim().replace(/;$/,'')+')');
const ITEMS=Object.keys(K);
const STRUCT=ITEMS.filter(k=>k.startsWith('25mm'));
const REST=ITEMS.filter(k=>!k.startsWith('25mm'));

const T={1:{n:"Launch",path:"both",recv:"—",hand:"Team 2 (Path A) and Team 3 (Path B)",
 spec:["Launch both balls at the same instant, from a single release.",
       "One ball goes to Path A, the other to Path B.",
       "The launch point must be at least 3 ft above the floor.",
       "Both balls must leave with enough speed to complete the rest of the run."],
 done:"One action releases both balls together, and each enters the next team's section cleanly at a height you have agreed with them."}};

const PATH_A=[[1,"Launch"],[2,"Raise elevation 1.5 ft above launch"],[4,"Long jump, 1.5 ft"],[6,"Open section"],[8,"Timing"],[10,"Final capture"]];
const PATH_B=[[1,"Launch"],[3,"Drop elevation 2 ft below launch"],[5,"Short jump, 0.75 ft"],[7,"Open section"],[9,"Timing"],[10,"Final capture"]];

function grid(items,me){
  let h='<table class="mx"><tr><th class="it">Item</th>';
  for(let n=1;n<=10;n++) h+=`<th class="${n==me?'me':''}">${n}</th>`;
  h+='</tr>';
  items.forEach(k=>{ if(!K[k].some(x=>x)) return;
    h+=`<tr><td class="it">${k}</td>`;
    for(let n=1;n<=10;n++){const v=K[k][n-1];
      h+=`<td class="${n==me?'me':''}${v?' has':''}">${v||'·'}</td>`;}
    h+='</tr>';});
  return h+'</table>';
}
function catalogue(){
  let h='';
  GROUPS.forEach(([g,list])=>{ h+=`<div class="grp">${g.split('—')[0].trim()}</div><div class="cat">`;
    list.forEach(k=>{h+=`<div class="card"><div class="ph">photo</div><div class="nm">${k}</div><div class="pr">${P[k][0]}</div></div>`;});
    h+='</div>';});
  return h;
}
const n=1, t=T[n];
const kit=ITEMS.filter(k=>K[k][n-1]&&k!=='Permanent pen tip marker').map(k=>`<tr><td>${k}</td><td class="q">${K[k][n-1]}</td></tr>`).join('');

const html=`<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page{size:A4;margin:14mm 13mm}
body{font-family:"DejaVu Sans",Verdana,sans-serif;font-size:10.8pt;line-height:1.5;color:#111;margin:0}
h1{font-size:30pt;color:#0b3d6b;margin:0;letter-spacing:.5px}
h2{font-size:19pt;font-weight:normal;margin:2px 0 14px}
h3{font-size:14pt;color:#0b3d6b;border-bottom:2px solid #0b3d6b;padding-bottom:4px;margin:26px 0 10px;page-break-after:avoid}
h4{font-size:11.5pt;color:#0b3d6b;margin:16px 0 6px;page-break-after:avoid}
p{margin:0 0 9px}
table{border-collapse:collapse;width:100%;margin:8px 0 14px;font-size:10pt;page-break-inside:avoid}
th{background:#0b3d6b;color:#fff;text-align:left;padding:5px 8px}
td{border-bottom:1px solid #ccc;padding:4px 8px}
tr:nth-child(even) td{background:#f4f6f8}
td.q{text-align:center;width:60px;font-weight:bold}
ul{margin:0 0 10px;padding-left:19px} li{margin-bottom:4px}
.mx{font-size:8.4pt} .mx th{padding:4px 3px;text-align:center} .mx th.it{text-align:left}
.mx td{padding:3px;text-align:center;border-bottom:1px solid #ddd}
.mx td.it{text-align:left;width:210px}
.mx .me{background:#0b3d6b!important;color:#fff}
.mx td.has{font-weight:bold}
.mx tr:nth-child(even) td{background:#f4f6f8}
.mx tr:nth-child(even) td.me{background:#0b3d6b}
.cat{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.card{width:92px;border:1px solid #bbb;border-radius:3px;padding:4px;text-align:center;page-break-inside:avoid}
.ph{height:56px;background:#eef1f5;border:1px dashed #aab;color:#99a;font-size:7pt;line-height:56px}
.nm{font-size:7.2pt;line-height:1.25;margin-top:3px;height:30px;overflow:hidden}
.pr{font-size:9pt;font-weight:bold;color:#0b3d6b}
.grp{font-size:9.5pt;font-weight:bold;color:#0b3d6b;margin:10px 0 5px;border-bottom:1px solid #ccd}
.box{border:1px solid #0b3d6b;background:#f4f7fb;padding:9px 12px;margin:12px 0}
.rule{page-break-before:always}
.notes{height:150mm;border:1px solid #ddd}
</style></head><body>

<h1>TEAM ${n}</h1><h2>${t.n}</h2>
<p><b>Marble Run Challenge · Tata Advanced Systems Limited</b></p>
<table><tr><th>Name</th><th>Name</th></tr><tr><td>1.</td><td>4.</td></tr><tr><td>2.</td><td>5.</td></tr><tr><td>3.</td><td>6.</td></tr></table>
<p>Keep this book on your table. Everything you need is in it.</p>

<h3>1. What the room is building</h3>
<p>Ten teams. One marble run.</p>
<p>Two balls are launched at the same instant from Team 1. They travel by two separate routes through the room and finish in two buckets at Team 10. The run succeeds when both balls land in their buckets at the same time.</p>
<p>Your team owns one section. It has to take a ball from the team before you and pass it to the team after you. No section is judged on its own — if one fails, the run fails.</p>

<h3>2. The two paths</h3>
<h4>Path A — small ball</h4>
<table><tr><th>Team</th><th>Section</th></tr>${PATH_A.map(([a,b])=>`<tr><td class="q">${a==n?'<b>'+a+'</b>':a}</td><td>${b}${a==n?' &nbsp;← you':''}</td></tr>`).join('')}</table>
<h4>Path B — large ball</h4>
<table><tr><th>Team</th><th>Section</th></tr>${PATH_B.map(([a,b])=>`<tr><td class="q">${a==n?'<b>'+a+'</b>':a}</td><td>${b}${a==n?' &nbsp;← you':''}</td></tr>`).join('')}</table>

<h3>3. Your challenge: ${t.n}</h3>
${t.spec.map(x=>`<p>${x}</p>`).join('')}
<p><b>You receive from:</b> ${t.recv}<br><b>You hand on to:</b> ${t.hand}</p>
<div class="box"><b>You are done when:</b> ${t.done}</div>
<h4>Rules that apply to every section</h4>
<ul>
<li>Once the run starts, nobody touches a ball.</li>
<li>No motors, no batteries, no compressed air, no external power.</li>
<li>Anything you build runs on the energy the ball brings, or on energy you store in your section before the run starts.</li>
<li>Your section stands on its own. Nobody holds it during the run.</li>
<li>Measurements are checked with a tape measure. Build to the number.</li>
</ul>

<h3>4. What is in your box</h3>
<table><tr><th>Item</th><th>Qty</th></tr>${kit}</table>
<h4>Tools</h4>
<table><tr><th>Item</th><th>Qty</th></tr>
<tr><td>Tape measure</td><td class="q">1</td></tr><tr><td>PVC cutter</td><td class="q">1</td></tr>
<tr><td>Junior hacksaw</td><td class="q">1</td></tr><tr><td>Paper knife</td><td class="q">1</td></tr>
<tr><td>Permanent pen tip marker</td><td class="q">1</td></tr>
<tr><td>Gloves (pairs)</td><td class="q">2</td></tr><tr><td>Safety glasses</td><td class="q">2</td></tr></table>
<h4>Your money</h4>
<p>Every team gets the same: <b>2,000 Kasu</b>. The materials are not the same.</p>
<table><tr><th>Coin</th><th>Number</th><th>Value</th></tr>
<tr><td>500 Kasu</td><td class="q">2</td><td class="q">1,000</td></tr>
<tr><td>100 Kasu</td><td class="q">3</td><td class="q">300</td></tr>
<tr><td>50 Kasu</td><td class="q">8</td><td class="q">400</td></tr>
<tr><td>20 Kasu</td><td class="q">10</td><td class="q">200</td></tr>
<tr><td>10 Kasu</td><td class="q">10</td><td class="q">100</td></tr>
<tr><td><b>Total</b></td><td class="q"><b>33</b></td><td class="q"><b>2,000</b></td></tr></table>
<div class="box">No box has everything its team needs. That is deliberate. Somewhere in this room is a team holding what you are short of.</div>

<h3 class="rule">5. What every team has</h3>
<p>Your column is highlighted. Put what you don't need in your spares tray so others can see it.</p>
<h4>Structural — 25mm</h4>
${grid(STRUCT,n)}
<h4>Pathway and consumables</h4>
${grid(REST,n)}

<h3 class="rule">6. Parts at the depot</h3>
<p>Price shown is the starting price. It can go up.</p>
${catalogue()}

<h3 class="rule">7. The depot</h3>
<ul>
<li>The depot sells at the price on the board. The board is the truth, not this book.</li>
<li>It buys back at the <b>starting price</b>, whatever the board says at the time.</li>
<li>Unused and in original condition: full price back. Cut or modified but usable: half. Cut about and unusable: nothing.</li>
<li><b>Only your nominated Trader may approach the counter.</b></li>
</ul>
<h4>The cutting bay</h4>
<ul>
<li>Bring material and it will be cut for you on power tools. No charge.</li>
<li>Up to five cuts per visit, then back of the queue.</li>
<li><b>Nobody from your team touches the power tools.</b> Stand outside the marked line.</li>
<li>You have a cutter and hacksaw in your box. The bay is faster and cleaner. Whether the queue is worth it is your call.</li>
</ul>

<h3>8. Trading with other teams</h3>
<p>No rules beyond common sense. Sell, buy, swap, lend, pool money, split a purchase, trade a favour or a pair of hands.</p>
<p>You cannot trade your safety gear. Everything else is yours to deal with.</p>
<p>Write down what you agree. There is a page at the back.</p>

<h3>9. Things will change</h3>
<p>Prices at the depot are not fixed. Events during the game can move them, sometimes a long way. When something changes we will announce it and the board will be updated. Keep an eye on it.</p>
<p>Prices are not the only thing that can change. Treat any announcement as part of the game.</p>

<h3>10. Working with the material</h3>
<p><b>Safety.</b> Gloves and glasses on whenever anyone is cutting. Cut away from your body, and keep cutting to one end of your table.</p>
<p><b>Cutting.</b> Measure twice. Cut square, and clean the burr off the inside and outside of every cut edge before you assemble anything.</p>
<p><b>Assembly.</b> Dry-fit before you commit to glue. Glue is permanent and glued parts have no resale value. Zip ties and tape hold more than you think.</p>
<p><b>Testing.</b> Roll a ball through each piece as you finish it. Do not wait until the end.</p>
<p><b>Clearance.</b> Every opening, catcher and channel must let the gauge through. Check it physically, not by eye. You may be asked to run a larger ball later.</p>

<h3 class="rule">11. Trade log</h3>
<table><tr><th>Time</th><th>Who with</th><th>What we gave</th><th>What we got</th><th>Agreed by</th></tr>
${'<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td></tr>'.repeat(18)}</table>

<h3>12. Notes</h3><div class="notes"></div>
</body></html>`;
fs.writeFileSync('guide_T1.html',html);
console.log('html written');
