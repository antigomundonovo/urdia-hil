"""Social Inbox tests (UHL-4).

Core rules under test:
- inbox items are workspace/profile-scoped;
- status transitions: UNREAD -> OPEN/RESOLVED/IGNORED;
- assignment promotes status UNREAD -> OPEN;
- cross-profile access fails closed.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.auth import get_current_user
from packages.domain.models import Profile, User, Workspace, WorkspaceMember
from packages.domain.publishing import Comment
from packages.research.social import SocialError, SocialIntelligenceService
from packages.shared.db import get_session


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"inbox-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    return ws, profile


def _comment(db, world) -> Comment:
    ws, profile = world
    comment = Comment(
        workspace_id=ws.id,
        profile_id=profile.id,
        author_ref="user-99",
        text="Ótimo vídeo!",
        intent="POSITIVE",
        qualified_signal=None,
    )
    db.add(comment)
    db.commit()
    return comment


def _ctx(world):
    from packages.shared.execution_context import ExecutionContext

    ws, profile = world
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _authenticate(db, workspace):
    actor = User(email=f"api-inbox-{uuid.uuid4().hex[:8]}@test.com")
    db.add(actor)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=actor.id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: actor
    return actor


def test_create_inbox_item_defaults(db, world):
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    item = service.create_inbox_item(
        _ctx(world),
        comment_id=comment.id,
    )
    assert item.status == "UNREAD"
    assert item.item_type == "COMMENT"
    assert item.assigned_to is None


def test_create_inbox_item_requires_profile(db, world):
    ws, _ = world
    from packages.shared.execution_context import ExecutionContext

    ctx = ExecutionContext(workspace_id=ws.id, profile_id=None)
    service = SocialIntelligenceService(db)
    with pytest.raises(SocialError, match="profile context required"):
        service.create_inbox_item(ctx)


def test_update_inbox_item_status(db, world):
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    item = service.create_inbox_item(_ctx(world), comment_id=comment.id)
    updated = service.update_inbox_item_status(_ctx(world), item.id, status="OPEN")
    assert updated.status == "OPEN"


def test_invalid_status_rejected(db, world):
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    item = service.create_inbox_item(_ctx(world), comment_id=comment.id)
    with pytest.raises(SocialError, match="invalid status"):
        service.update_inbox_item_status(_ctx(world), item.id, status="BOGUS")


def test_assign_inbox_item_promotes_unread_to_open(db, world):
    comment = _comment(db, world)
    ws, profile = world
    user = User(email=f"u{uuid.uuid4().hex[:6]}@test.com")
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id))
    db.commit()
    service = SocialIntelligenceService(db)
    item = service.create_inbox_item(_ctx(world), comment_id=comment.id)
    assert item.status == "UNREAD"
    assigned = service.assign_inbox_item(_ctx(world), item.id, user_id=user.id)
    assert assigned.status == "OPEN"
    assert assigned.assigned_to is not None


def test_list_inbox_items_filter_by_status(db, world):
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    service.create_inbox_item(_ctx(world), comment_id=comment.id)
    c2 = _comment(db, world)
    item2 = service.create_inbox_item(_ctx(world), comment_id=c2.id)
    service.update_inbox_item_status(_ctx(world), item2.id, status="RESOLVED")
    db.commit()

    unread = service.list_inbox_items(_ctx(world), status="UNREAD")
    resolved = service.list_inbox_items(_ctx(world), status="RESOLVED")
    assert all(i.status == "UNREAD" for i in unread)
    assert all(i.status == "RESOLVED" for i in resolved)


def test_inbox_item_profile_isolation(db, world):
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    item = service.create_inbox_item(_ctx(world), comment_id=comment.id)

    ws, profile = world
    foreign_profile = Profile(workspace_id=ws.id, key="secondary", name="Secondary")
    db.add(foreign_profile)
    db.commit()
    from packages.shared.execution_context import ExecutionContext

    foreign = ExecutionContext(workspace_id=ws.id, profile_id=foreign_profile.id)
    assert service.get_inbox_item(foreign, item.id) is None


def test_create_inbox_item_rejects_foreign_comment(db, world):
    foreign_ws = Workspace(name=f"foreign-{uuid.uuid4().hex[:8]}")
    db.add(foreign_ws)
    db.flush()
    foreign_profile = Profile(
        workspace_id=foreign_ws.id, key="foreign", name="Foreign"
    )
    db.add(foreign_profile)
    db.flush()
    foreign_comment = Comment(
        workspace_id=foreign_ws.id,
        profile_id=foreign_profile.id,
        author_ref="foreign",
        text="Foreign comment",
        intent="QUESTION",
        qualified_signal=None,
    )
    db.add(foreign_comment)
    db.commit()

    with pytest.raises(SocialError, match="comment not found in profile"):
        SocialIntelligenceService(db).create_inbox_item(
            _ctx(world), comment_id=foreign_comment.id
        )


def test_assign_inbox_item_rejects_foreign_workspace_user(db, world):
    comment = _comment(db, world)
    service = SocialIntelligenceService(db)
    item = service.create_inbox_item(_ctx(world), comment_id=comment.id)

    foreign_ws = Workspace(name=f"assign-{uuid.uuid4().hex[:8]}")
    db.add(foreign_ws)
    db.flush()
    user = User(email=f"foreign-{uuid.uuid4().hex[:8]}@test.com")
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=foreign_ws.id, user_id=user.id))
    db.commit()

    with pytest.raises(SocialError, match="workspace member"):
        service.assign_inbox_item(_ctx(world), item.id, user.id)


def test_api_social_inbox_flow(client, db, world):
    comment = _comment(db, world)
    ws, profile = world

    created = client.post(
        f"/api/v1/social/inbox?workspace_id={ws.id}",
        json={
            "profile_id": str(profile.id),
            "comment_id": str(comment.id),
            "item_type": "COMMENT",
        },
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["id"]
    assert created.json()["status"] == "UNREAD"

    actor = _authenticate(db, ws)

    listed = client.get(
        f"/api/v1/social/inbox?workspace_id={ws.id}&profile_id={profile.id}"
    )
    assert listed.status_code == 200
    assert any(i["id"] == item_id for i in listed.json())

    status_updated = client.post(
        f"/api/v1/social/inbox/{item_id}/status?workspace_id={ws.id}",
        json={"profile_id": str(profile.id), "status": "RESOLVED"},
    )
    assert status_updated.status_code == 200
    assert status_updated.json()["status"] == "RESOLVED"

    from packages.domain.social import SocialInboxItem
    from packages.domain.models import AuditEvent
    from sqlalchemy import select

    audit = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == item_id,
            AuditEvent.action == "SOCIAL_INBOX_ITEM_UPDATED",
        )
    ).one()
    assert audit.actor_id == actor.id



def test_api_inbox_invalid_status_rejected(client, db, world):
    comment = _comment(db, world)
    ws, profile = world
    _authenticate(db, ws)

    created = client.post(
        f"/api/v1/social/inbox?workspace_id={ws.id}",
        json={"profile_id": str(profile.id), "comment_id": str(comment.id)},
    )
    item_id = created.json()["id"]

    resp = client.post(
        f"/api/v1/social/inbox/{item_id}/status?workspace_id={ws.id}",
        json={"profile_id": str(profile.id), "status": "INVALID"},
    )
    assert resp.status_code == 422
