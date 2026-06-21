"""Tests for AI output parsing/validation and the analyst agent with a mock ARK."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import stock_analyst_agent as saa
from agents.ark_client import ChatResult


def test_extract_json_plain():
    parsed = saa._extract_json('{"symbol": "NVDA", "action": "hold"}')
    assert parsed["symbol"] == "NVDA"


def test_extract_json_with_fence():
    text = "```json\n{\"symbol\": \"NVDA\"}\n```"
    assert saa._extract_json(text)["symbol"] == "NVDA"


def test_extract_json_embedded_prose():
    text = "分析如下： {\"symbol\": \"AMD\", \"risk_level\": \"high\"} 以上。"
    parsed = saa._extract_json(text)
    assert parsed["risk_level"] == "high"


def test_validate_clamps_invalid_enums():
    out = saa._validate({"recommendation": "MOON", "risk_level": "extreme",
                         "action": "yolo", "next_watch_price": "abc"}, "NVDA")
    assert out["recommendation"] == "觀察"
    assert out["risk_level"] == "medium"
    assert out["action"] == "wait"
    assert out["next_watch_price"] is None
    assert out["symbol"] == "NVDA"


def test_validate_keeps_valid_values():
    out = saa._validate({"recommendation": "續抱", "risk_level": "low",
                         "action": "hold", "next_watch_price": 123.45}, "NVDA")
    assert out["recommendation"] == "續抱"
    assert out["action"] == "hold"
    assert out["next_watch_price"] == 123.45


class _MockClient:
    enabled = True

    def chat(self, system_prompt, user_prompt, **kwargs):
        return ChatResult(
            content='{"symbol":"NVDA","recommendation":"續抱","risk_level":"low",'
                    '"action":"hold","summary":"穩健","invalidation_condition":"跌破MA60",'
                    '"next_watch_price":120}',
            input_tokens=10, output_tokens=20, model="mock-model")


def test_agent_analyze_with_mock(temp_db):
    from db import database as db
    db.insert("holdings", {"symbol": "NVDA", "shares": 10, "avg_cost": 100,
                           "category": "core", "active": 1})
    db.record_tick("NVDA", price=130.0, source="test")

    agent = saa.StockAnalystAgent(client=_MockClient())
    result = agent.analyze("NVDA", trigger_description="test")
    assert result["recommendation"] == "續抱"
    assert result["action"] == "hold"
    assert result["_meta"]["model"] == "mock-model"
    assert "context" in result["_meta"]


def test_agent_disabled_returns_none(temp_db):
    class _Off:
        enabled = False
        def chat(self, *a, **k):
            return None
    agent = saa.StockAnalystAgent(client=_Off())
    assert agent.analyze("NVDA") is None
