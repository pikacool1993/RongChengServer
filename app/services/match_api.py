from __future__ import annotations

import os

import httpx


def build_match_detail_url() -> str:
    base_url = os.getenv(
        "MATCH_API_BASE_URL",
        "https://fccdn1.k4n.cc/fc/wx_api/v1/MiniApp/getMatchInfo",
    )
    lid2 = os.getenv("MATCH_API_LID2")
    if not lid2:
        raise RuntimeError("环境变量 MATCH_API_LID2 未设置。")
    return f"{base_url}?lid2={lid2}"


def build_match_detail_headers() -> dict[str, str]:
    bearer = os.getenv("MATCH_API_BEARER")
    if not bearer:
        raise RuntimeError("环境变量 MATCH_API_BEARER 未设置。")

    return {
        "Authorization": f"Bearer {bearer}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254181d) XWEB/19201",
        "xweb_xhr": "1",
        "Content-Type": "application/json;charset:utf-8;",
        "Accept": "*/*",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://servicewechat.com/wxffa42ecd6c0e693d/78/page-frame.html",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


async def request_match_detail(match_id: str) -> dict:
    url = build_match_detail_url()
    headers = build_match_detail_headers()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"id": match_id}, headers=headers)
        resp.raise_for_status()
        return resp.json()

