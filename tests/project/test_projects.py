import pytest


@pytest.mark.asyncio
async def test_projects_require_auth(project_client):
    response = await project_client.get("/projects")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_project_crud(project_client):
    headers = {"X-User-ID": "owner-1"}

    create = await project_client.post(
        "/projects",
        json={"name": "My Project", "description": "test"},
        headers=headers,
    )
    assert create.status_code == 201
    project_id = create.json()["data"]["id"]

    listed = await project_client.get("/projects", headers=headers)
    assert len(listed.json()["data"]) == 1

    got = await project_client.get(f"/projects/{project_id}", headers=headers)
    assert got.json()["data"]["name"] == "My Project"

    deleted = await project_client.delete(f"/projects/{project_id}", headers=headers)
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_upload_file_metadata(project_client):
    headers = {"X-User-ID": "owner-1"}
    create = await project_client.post(
        "/projects", json={"name": "Files"}, headers=headers
    )
    project_id = create.json()["data"]["id"]

    files = {"file": ("notes.txt", b"hello world", "text/plain")}
    upload = await project_client.post(
        f"/projects/{project_id}/files", files=files, headers=headers
    )
    assert upload.status_code == 201
    assert upload.json()["data"]["status"] == "pending"
    assert upload.json()["data"]["filename"] == "notes.txt"

    listed = await project_client.get(f"/projects/{project_id}/files", headers=headers)
    assert len(listed.json()["data"]) == 1

@pytest.mark.asyncio
async def test_patch_file_status_internal(project_client):
    headers = {"X-User-ID": "owner-1"}
    create = await project_client.post(
        "/projects", json={"name": "Status"}, headers=headers
    )
    project_id = create.json()["data"]["id"]

    files = {"file": ("notes.txt", b"hello world", "text/plain")}
    upload = await project_client.post(
        f"/projects/{project_id}/files", files=files, headers=headers
    )
    file_id = upload.json()["data"]["id"]

    patch = await project_client.patch(
        f"/projects/{project_id}/files/{file_id}/status",
        json={"status": "failed", "error_message": "Not football related"},
    )
    assert patch.status_code == 200
    data = patch.json()["data"]
    assert data["status"] == "failed"
    assert data["error_message"] == "Not football related"


@pytest.mark.asyncio
async def test_upload_triggers_ingestion_job(project_client, mocker):
    mock_post = mocker.patch("services.project.ingestion_trigger.httpx.post")
    mock_response = mocker.Mock()
    mock_response.raise_for_status = mocker.Mock()
    mock_post.return_value = mock_response

    headers = {"X-User-ID": "owner-1"}
    create = await project_client.post(
        "/projects", json={"name": "Trigger"}, headers=headers
    )
    project_id = create.json()["data"]["id"]

    files = {"file": ("notes.txt", b"hello", "text/plain")}
    await project_client.post(
        f"/projects/{project_id}/files", files=files, headers=headers
    )

    assert mock_post.called
    payload = mock_post.call_args.kwargs["json"]
    assert payload["project_id"] == project_id
    assert payload["filename"] == "notes.txt"


@pytest.mark.asyncio
async def test_memory_and_context(project_client):
    headers = {"X-User-ID": "owner-1"}
    create = await project_client.post(
        "/projects", json={"name": "Memory"}, headers=headers
    )
    project_id = create.json()["data"]["id"]

    mem = await project_client.post(
        f"/projects/{project_id}/memory",
        json={"memory_type": "preference", "content": "Likes Liverpool"},
        headers=headers,
    )
    assert mem.status_code == 201

    ctx = await project_client.get(f"/projects/{project_id}/context", headers=headers)
    assert ctx.status_code == 200
    data = ctx.json()["data"]
    assert data["project"]["name"] == "Memory"
    assert len(data["memory"]) == 1
    assert data["memory"][0]["content"] == "Likes Liverpool"
