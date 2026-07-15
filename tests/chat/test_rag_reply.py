import pytest


@pytest.mark.asyncio
async def test_post_user_message_triggers_rag(chat_client, mocker):
    mocker.patch(
        "services.chat.routes.run_pipeline_sync",
        return_value={
            "reply": "They won 2-1.",
            "snapshot": "{}",
            "snapshot_turn_count": 0,
            "citations": [],
            "run_id": 7,
            "classification": "KNOWLEDGE",
            "reached_max_retries": False,
        },
    )

    create = await chat_client.post("/chats", json={"title": "RAG test"})
    chat_id = create.json()["data"]["id"]

    response = await chat_client.post(
        f"/chats/{chat_id}/messages",
        json={"role": "user", "content": "Score?", "web_search_enabled": True},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["message"]["role"] == "user"
    assert body["assistant_message"]["content"] == "They won 2-1."
    assert body["run_id"] == 7
