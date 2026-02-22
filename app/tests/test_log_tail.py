from pathlib import Path

from app.core.log_tail import build_log_tail_payload


def test_build_log_tail_payload_filters_by_level_and_module(tmp_path: Path):
    log_file = tmp_path / "service.log"
    log_file.write_text(
        "\n".join(
            [
                "2026-02-22 10:00:00,000 [INFO] [scheduler] scheduler_started",
                "2026-02-22 10:01:00,000 [WARNING] [sync] remote_rename_failed payload_json_decode_failed",
                "2026-02-22 10:02:00,000 [ERROR] [sync] run_failed fatal_error",
            ]
        ),
        encoding="utf-8",
    )

    payload = build_log_tail_payload(str(log_file), n=100, level="WARNING", module="sync")

    assert payload["count"] == 1
    assert payload["items"][0]["level"] == "WARNING"
    assert payload["items"][0]["module"] == "sync"
    assert "remote_rename_failed" in payload["tail"]


def test_build_log_tail_payload_handles_missing_file(tmp_path: Path):
    payload = build_log_tail_payload(str(tmp_path / "missing.log"), n=20)
    assert payload["count"] == 0
    assert payload["tail"] == ""
