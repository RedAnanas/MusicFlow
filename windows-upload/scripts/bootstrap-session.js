// 仅读取当前 Apple Music 账号的授权会话，通过二进制消息交给本地 DPAPI 保存。
// 不读取密码，不输出认证内容，不发送账号请求，不修改客户端既有参数。
const app = Process.getModuleByName('AMPLibraryAgent.exe');
const cf = Process.getModuleByName('CoreFoundation.dll');
function native(rva, ret, args) { return new NativeFunction(app.base.add(rva), ret, args); }
function api(name, ret, args) { return new NativeFunction(cf.getExportByName(name), ret, args); }
const ready = native(0xb8c490, 'bool', []);
const getUser = native(0xb9448c, 'pointer', ['pointer']);
const getDsid = native(0xb944c4, 'uint64', ['pointer']);
const getToken = native(0xb95198, 'pointer', ['pointer', 'pointer']);
const getFront = native(0xb9584c, 'pointer', ['pointer', 'pointer']);
const toCF = native(0x205434, 'pointer', ['pointer', 'pointer']);
const releaseUser = native(0x211aac, 'void', ['pointer']);
const releaseString = native(0x2052bc, 'void', ['pointer']);
const release = api('CFRelease', 'void', ['pointer']);
const acceptLanguage = native(0x21544c, 'pointer', []);
const userAgent = native(0xbaab3c, 'pointer', ['pointer']);
const getLength = api('CFStringGetLength', 'int64', ['pointer']);
const getCString = api('CFStringGetCString', 'bool', ['pointer', 'pointer', 'int64', 'uint']);
function text(value) {
  if (value.isNull()) return '';
  const size = getLength(value).toNumber() * 4 + 1;
  if (size > 262144) throw new Error('field-too-large');
  const buffer = Memory.alloc(size);
  if (!getCString(value, buffer, size, 0x08000100)) throw new Error('conversion-failed');
  return buffer.readUtf8String();
}
function stringValue(value) {
  const result = toCF(value, ptr(0));
  try { return text(result); } finally { if (!result.isNull()) release(result); }
}
if (!ready()) {
  send({ kind: 'bootstrap-failed', reason: 'services-not-ready' });
} else {
  const user = Memory.alloc(16), token = Memory.alloc(16), front = Memory.alloc(16);
  for (const p of [user, token, front]) p.writeByteArray(new Uint8Array(16));
  try {
    getUser(user);
    const dsid = getDsid(user).toString();
    getToken(user, token);
    getFront(user, front);
    const tokenValue = stringValue(token), frontValue = stringValue(front);
    if (dsid === '0' || !tokenValue) throw new Error('account-not-ready');
    const headers = { 'X-Dsid': dsid, 'X-Token': tokenValue };
    const agentString = Memory.alloc(16);
    agentString.writeByteArray(new Uint8Array(16));
    try {
      userAgent(agentString);
      const agent = stringValue(agentString);
      if (agent) headers['User-Agent'] = agent;
    } finally { releaseString(agentString); }
    const language = text(acceptLanguage());
    if (language) headers['Accept-Language'] = language;
    if (frontValue) headers['X-Apple-Store-Front'] = frontValue;
    // Cookie getter仅按已确认的 Apple 上传服务 URL 查询，数据仍留在本地。
    const makeString = api('CFStringCreateWithCString', 'pointer', ['pointer', 'pointer', 'uint']);
    const makeURL = api('CFURLCreateWithString', 'pointer', ['pointer', 'pointer', 'pointer']);
    const makeDict = api('CFDictionaryCreateMutable', 'pointer', ['pointer', 'int64', 'pointer', 'pointer']);
    const dictGet = api('CFDictionaryGetValue', 'pointer', ['pointer', 'pointer']);
    const readCookies = native(0x4e405c, 'int', ['pointer', 'pointer', 'pointer', 'pointer']);
    const cookiesByHost = {};
    for (const [host, path] of [
      ['genius-3.itunes.apple.com', '/WebObjects/UCGovernor.woa/wa/libraryUpdateAcceptingRequests'],
      ['genius-upload-2.itunes.apple.com', '/updateLibrary/'],
      ['genius-download-2.itunes.apple.com', '/SGCourier/downloadRequests/'],
      ['genius-upload.itunes.apple.com', '/updateLibrary/'],
      ['genius-download.itunes.apple.com', '/SGCourier/downloadRequests/'],
    ]) {
      const urlString = makeString(ptr(0), Memory.allocUtf8String('https://' + host + path), 0x08000100);
      const url = makeURL(ptr(0), urlString, ptr(0));
      const dict = makeDict(ptr(0), 0, cf.getExportByName('kCFTypeDictionaryKeyCallBacks'), cf.getExportByName('kCFTypeDictionaryValueCallBacks'));
      try {
        if (readCookies(ptr(0), user, url, dict) !== 0) throw new Error('cookie-read-failed');
        const cookie = text(dictGet(dict, app.base.add(0x11a7a80).readPointer()));
        if (cookie) cookiesByHost[host] = cookie;
      } finally { release(dict); release(url); release(urlString); }
    }
    if (cookiesByHost['genius-3.itunes.apple.com']) headers.Cookie = cookiesByHost['genius-3.itunes.apple.com'];
    const session = { version: 1, source: 'official-client-bootstrap', headers, cookies_by_host: cookiesByHost };
    // 直接读取当前已初始化的资料库偏好，不触发资料库更新或歌曲上传。
    const library = app.base.add(0x1156f60).readPointer();
    if (!library.isNull()) {
      const libraryDsid = library.add(0x68).readU64().toString();
      const cuid = stringValue(library.add(0x30));
      const troveid = stringValue(library.add(0x70));
      if (libraryDsid === dsid && cuid && troveid) {
        session.library_identity = { dsid: libraryDsid, cuid, troveid,
          itre: app.base.add(0x1156506).readU8() ? 1 : 0 };
      }
    }
    // 只复制上传相关服务配置，不读取云端歌曲或歌单。
    const bagGet = native(0x4edd9c, 'pointer', ['pointer', 'pointer', 'uint64']);
    const stringType = api('CFStringGetTypeID', 'uint64', []);
    const store = app.base.add(0x1158c50).readPointer();
    session.upload_configuration = {};
    if (!store.isNull()) {
      for (const key of ['cloud-library-update-request', 'cloud-library-update-check', 'cloud-library-match-request', 'library-update-accepting-requests', 'cloud-assets-update']) {
        const name = makeString(ptr(0), Memory.allocUtf8String(key), 0x08000100);
        try {
          const value = bagGet(store, name, stringType());
          if (!value.isNull()) session.upload_configuration[key] = text(value);
        } finally { release(name); }
      }
    }
    const encoded = JSON.stringify(session).replace(/[^\x00-\x7f]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
    const packet = Memory.allocUtf8String(encoded);
    const bytes = packet.readByteArray(encoded.length);
    send({ kind: 'private-session' }, bytes);
  } catch (_) {
    send({ kind: 'bootstrap-failed', reason: 'native-session-read-failed' });
  } finally { releaseString(token); releaseString(front); releaseUser(user); }
}
