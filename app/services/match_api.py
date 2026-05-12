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
        "Content-Type": "application/json;charset:utf-8;",
        "Referer": "https://servicewechat.com/wxffa42ecd6c0e693d/78/page-frame.html",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 26_4_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.71(0x18004730) NetType/WIFI Language/zh_CN"
    }

async def request_match_detail(match_id: str) -> dict:
    url = build_match_detail_url()
    headers = build_match_detail_headers()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"id": match_id}, headers=headers)
        resp.raise_for_status()
        return resp.json()

