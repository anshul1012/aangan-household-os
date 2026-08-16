"""Tests for the nightly expense-logging reminder job — no DB, no live Gemini."""

from aangan.config.config import Config
from aangan.scheduler import reminder


async def test_build_uses_llm_text_when_available(monkeypatch):
    async def fake_generate_text(prompt):
        return "  Log it before midnight! 🕙  "

    monkeypatch.setattr(reminder, "generate_text", fake_generate_text)
    message = await reminder._build()
    assert message.text == "Log it before midnight! 🕙"
    assert message.chart_png is None


async def test_build_falls_back_on_llm_failure(monkeypatch):
    async def boom(prompt):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(reminder, "generate_text", boom)
    message = await reminder._build()
    assert message.text == reminder._FALLBACK
    assert message.chart_png is None


async def test_build_falls_back_on_empty_llm_response(monkeypatch):
    async def empty(prompt):
        return "   "

    monkeypatch.setattr(reminder, "generate_text", empty)
    message = await reminder._build()
    assert message.text == reminder._FALLBACK


def test_build_job_wires_channel_and_trigger():
    config = Config(bot_token="x", gemini_api_key="x", expenses_channel_id=999)
    job = reminder.build_job(config)
    assert job.channel_id == 999
    assert job.name == reminder.JOB_NAME
    assert job.trigger.fields  # sanity: CronTrigger constructed
