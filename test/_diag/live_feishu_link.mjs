import { readLink } from '/Users/lute/project/audit_multi_content/tools/agent/feishu_link.mjs';

const urls = [
  'https://momcozy-in.feishu.cn/docx/Ybg1dZtoaoG5GKxLfREcHAK2nfs',
  'https://momcozy-in.feishu.cn/sheets/B1aUs2Vuah8YwjtwWO6cr5MFnUd',
  'https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0',
  'https://momcozy-in.feishu.cn/wiki/A0fxdtmKxoQbmAxmpXVce7SVnEd',
  'https://momcozy-in.feishu.cn/file/IWbobAGHAoDcycxRFWNcBYd1nY6',
];
for (const u of urls) {
  try {
    const r = await readLink(u);
    console.log(`OK  ${u}\n    type=${r.contentType} title=${JSON.stringify(r.title)} chars=${r.text.length}`);
    console.log(`    head=${JSON.stringify(r.text.slice(0, 160))}`);
  } catch (e) {
    console.log(`ERR ${u}\n    name=${e.name} kind=${e.linkKind ?? '-'} msg=${JSON.stringify(String(e.message).slice(0, 160))}`);
    if (e.shouhengReply) console.log(`    reply=${JSON.stringify(e.shouhengReply.slice(0, 300))}`);
  }
}
