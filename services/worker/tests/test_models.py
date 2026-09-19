from worker.models import ScriptV1


def test_script_v1_duration():
    s = ScriptV1.model_validate(
        {
            "version": 1,
            "scenes": [
                {"index": i, "duration_s": 4, "visual_prompt": "x", "narration": {"fr": "a", "en": "b"}} for i in range(6)
            ],
            "metadata": {
                "fr": {"title": "t", "description": "d", "tags": []},
                "en": {"title": "t", "description": "d", "tags": []},
            },
        }
    )
    assert s.duration_s == 24
