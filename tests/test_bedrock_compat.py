from bridge.bedrock_compat import strip_nova_tool_cache_points


def test_nova_requests_do_not_include_tool_cache_points():
    request = {
        "toolConfig": {
            "tools": [
                {"toolSpec": {"name": "search"}},
                {"cachePoint": {"type": "default"}},
            ],
        },
    }

    assert strip_nova_tool_cache_points(request, "amazon.nova-lite-v1:0") == {
        "toolConfig": {"tools": [{"toolSpec": {"name": "search"}}]},
    }
    assert request["toolConfig"]["tools"][-1] == {"cachePoint": {"type": "default"}}


def test_non_nova_requests_are_unchanged():
    request = {"toolConfig": {"tools": [{"cachePoint": {"type": "default"}}]}}

    assert strip_nova_tool_cache_points(request, "anthropic.claude-sonnet") == request


def test_nova_requests_do_not_include_system_or_message_cache_points():
    request = {
        "system": [{"text": "instructions"}, {"cachePoint": {"type": "default"}}],
        "messages": [
            {
                "role": "user",
                "content": [{"text": "previous turn"}, {"cachePoint": {"type": "default"}}],
            },
            {"role": "assistant", "content": [{"text": "latest turn"}]},
        ],
    }

    assert strip_nova_tool_cache_points(request, "amazon.nova-lite-v1:0") == {
        "system": [{"text": "instructions"}],
        "messages": [
            {"role": "user", "content": [{"text": "previous turn"}]},
            {"role": "assistant", "content": [{"text": "latest turn"}]},
        ],
    }
