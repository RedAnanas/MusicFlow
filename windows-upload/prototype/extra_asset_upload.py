"""复刻 CloudAssetUploadConversation，给既有云歌曲上传歌词和封面。"""

import base64
import gzip
import hashlib
import plistlib
import time

from prototype.local_session import save_session
from prototype.upload_asset import upload_asset


def asset_metadata(data):
    """原生初始化请求同时携带两种摘要，不改变资产字节。"""
    return {"file-size": len(data), "hash-values": {
        "md5": hashlib.md5(data).hexdigest(), "sha256": hashlib.sha256(data).hexdigest()}}


def upload_extras(uploader, assets):
    """沿用歌曲云标识；每个阶段保存密文，失败后不新建歌曲。"""
    from prototype.uploader import SongUploadError

    state = uploader.state
    cloud_id = state["cloud_id"]
    common = uploader.common

    def remember(key, reply):
        state[key] = base64.b64encode(plistlib.dumps(reply)).decode("ascii")
        save_session(uploader.job, state)
        return reply

    def saved(key):
        return plistlib.loads(base64.b64decode(state[key]))

    def wait(reply):
        delay = reply.get("retry-in-ms", reply.get("back-off-delay-in-ms", 1000))
        if type(delay) is not int or delay < 0:
            raise SongUploadError("资产服务返回无效等待时间")
        uploader.progress("extras-waiting", min(delay, 60000) // 1000)
        time.sleep(min(max(delay, 1000), 60000) / 1000)

    def final_tokens(reply):
        if reply.get("error"):
            raise SongUploadError("资产服务报告会话处理失败")
        tokens = {}
        for ticket in reply.get("payload", []):
            if ticket.get("cloud-id") != cloud_id:
                raise SongUploadError("资产完成响应不属于当前歌曲")
            for action in ticket.get("actions", []):
                if action.get("error"):
                    raise SongUploadError("资产服务报告单曲处理失败")
                for kind in assets:
                    token = action.get(f"token-{kind}")
                    if isinstance(token, str) and token:
                        tokens[kind] = token
        state.setdefault("tokens", {}).update(tokens)

    if state.get("completed"):
        return {"extras_completed": True, "assets": sorted(assets)}
    if any(record.get("state") != "received" for record in state["requests"]):
        raise SongUploadError("资产请求结果尚未确认，停止自动重发")
    # 响应和阶段标记之间可能中断；先重放已确认响应，避免重复初始化或回报。
    result_received = False
    for record in state["requests"]:
        raw = base64.b64decode(record["response"])
        reply = plistlib.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b\x08") else raw)
        if not isinstance(reply, dict) or reply.get("status") != 0:
            raise SongUploadError("已保存的资产响应未成功，停止自动恢复")
        route = record.get("route")
        if route is None:
            state.setdefault("initial", base64.b64encode(plistlib.dumps(reply)).decode("ascii"))
        elif route == "uploadResponses":
            result_received = True
            state.setdefault("result", base64.b64encode(plistlib.dumps(reply)).decode("ascii"))
            final_tokens(reply)
        elif route == "downloadRequests":
            if result_received:
                state["availability"] = base64.b64encode(plistlib.dumps(reply)).decode("ascii")
                final_tokens(reply)
            elif reply.get("payload") or reply.get("all-work-completed"):
                state.setdefault("work", base64.b64encode(plistlib.dumps(reply)).decode("ascii"))
    uploader.progress("extras-create-session")
    initial = saved("initial") if "initial" in state else remember("initial", uploader._post(
        uploader.account["upload_configuration"]["cloud-assets-update"],
        {**common, "payload": {"cloud-ids": [cloud_id],
                              **{kind: asset_metadata(data) for kind, data in assets.items()}}}))
    if initial.get("all-work-completed") is True:
        final_tokens(initial)
        if set(state.get("tokens", {})) != set(assets):
            raise SongUploadError("资产会话已结束，但尚未取得全部资产完成票据")
    else:
        deadline = time.monotonic() + 600
        download = initial["download-requests-url"]
        upload = initial["upload-responses-url"]
        if "work" not in state:
            while time.monotonic() < deadline:
                work = uploader._post(download, common, "downloadRequests")
                if work.get("payload") or work.get("all-work-completed"):
                    remember("work", work)
                    break
                wait(work)
            else:
                raise SongUploadError("等待资产上传任务超时")
        work = saved("work")
        if work.get("all-work-completed"):
            final_tokens(work)
        else:
            tickets = work.get("payload", [])
            if len(tickets) != 1 or tickets[0].get("cloud-id") != cloud_id:
                raise SongUploadError("资产任务不属于当前单曲")
            actions = tickets[0].get("actions", [])
            if len(actions) != 1 or actions[0].get("action") != "upload-track":
                raise SongUploadError("服务端返回了未验证的资产操作")
            action = actions[0]
            if not action.get("assets") or not set(action["assets"]).issubset(assets):
                raise SongUploadError("服务端资产类型与本地文件不一致")
            if "result" not in state:
                statuses = state.setdefault("asset_statuses", {})
                for kind, task in action["assets"].items():
                    if kind not in statuses:
                        uploader.progress(f"upload-{kind}")
                        statuses[kind] = upload_asset(task["upload-info"], assets[kind],
                                                     uploader.account["headers"]["User-Agent"])[-1]
                        save_session(uploader.job, state)
                response_action = {"action": "upload-track", "assets": {
                    kind: {"response-code": statuses[kind]} for kind in action["assets"]},
                    "response-data": action["response-data"]}
                remember("result", uploader._post(upload, {**common, "payload": [
                    {"cloud-id": cloud_id, "actions": [response_action]}]}, "uploadResponses"))
            result = saved("result")
            final_tokens(result)
            reply = saved("availability") if "availability" in state else result
            while reply.get("all-work-completed") is not True and time.monotonic() < deadline:
                wait(reply)
                reply = uploader._post(download, common, "downloadRequests")
                final_tokens(reply)
                remember("availability", reply)
            if reply.get("all-work-completed") is not True:
                raise SongUploadError("资产已传输，等待云端可用确认超时")
        if set(state.get("tokens", {})) != set(assets):
            raise SongUploadError("服务端尚未返回全部歌词和封面完成票据")
    state["completed"] = True
    save_session(uploader.job, state)
    return {"extras_completed": True, "assets": sorted(assets), "client_rpc_used": False}
