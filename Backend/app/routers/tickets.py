"""Tickets del mesón de soporte (lectura desde Jira, ámbito de sede/grupo)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_supervisor
from app.models.user import Role, User
from app.schemas.ticket import (
    JiraGroupOut, LinkOut, LinkRequest, TicketDetailOut, TicketListOut, TicketOut,
    TicketStatsOut,
)
from app.schemas.user import UserBrief
from app.services import audit_service, auth_service, ticket_service

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])


def _list_out(result: ticket_service.TicketList, *, account_id: str | None = None) -> TicketListOut:
    return TicketListOut(
        provider=result.provider, linked=result.linked, scope_label=result.scope_label,
        total=len(result.items), has_more=result.has_more, account_id=account_id,
        items=[
            TicketOut(
                key=item.key,
                url=f"{settings.JIRA_BASE_URL}/browse/{item.key}" if settings.JIRA_BASE_URL else "",
                summary=item.summary, status_name=item.status_name,
                status_category=item.status_category, priority=item.priority,
                assignee_name=item.assignee_name, assignee_account_id=item.assignee_account_id,
                created=item.created, updated=item.updated, is_mine=item.is_mine,
            )
            for item in result.items
        ],
    )


@router.get("/mine", response_model=TicketListOut, summary="Mis tickets del mesón (ámbito de sede)")
def my_tickets(
    scope: str = Query(default="open", description="open | done | all"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TicketListOut:
    try:
        result = ticket_service.list_tickets(db, current_user, mine=True, scope=scope)
    except ticket_service.TicketError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return _list_out(result, account_id=current_user.jira_account_id)


@router.get("/global", response_model=TicketListOut, summary="Mesón completo de esta sede")
def global_tickets(
    scope: str = Query(default="open", description="open | done | all"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TicketListOut:
    try:
        result = ticket_service.list_tickets(db, current_user, mine=False, scope=scope)
    except ticket_service.TicketError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return _list_out(result)


@router.get("/stats", response_model=TicketStatsOut, summary="KPIs del mesón (abiertos, SLA, MTTR, CSAT)")
def tickets_stats(current_user: User = Depends(get_current_user)) -> TicketStatsOut:
    stats = ticket_service.get_stats()
    return TicketStatsOut(
        provider=stats.provider, open_count=stats.open_count, sla_risk=stats.sla_risk,
        sla_configured=bool(settings.JIRA_TICKETS_SLA_RISK_JQL),
        mttr_hours=stats.mttr_hours, satisfaction_pct=stats.satisfaction_pct,
        rated_count=stats.rated_count, resolved_count=stats.resolved_count,
        window_days=stats.window_days,
    )


@router.get("/groups", response_model=list[JiraGroupOut], summary="Grupos de Jira (supervisor/admin)")
def jira_groups(
    query: str = Query(default="", max_length=100),
    supervisor: User = Depends(require_supervisor),
) -> list[JiraGroupOut]:
    """Para descubrir el nombre EXACTO del grupo y ponerlo en JIRA_TICKETS_GROUP."""
    from app.integrations import jira

    try:
        groups = jira.find_groups(query)
    except jira.JiraError as exc:
        raise HTTPException(503, str(exc))
    return [JiraGroupOut(name=g.get("name") or "", group_id=g.get("groupId"))
            for g in groups if g.get("name")]


@router.post("/link", response_model=LinkOut, summary="Vincular mi cuenta de Jira")
def link_account(
    payload: LinkRequest | None = None,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> LinkOut:
    body = payload or LinkRequest()
    target = current_user
    if body.user_id is not None and body.user_id != current_user.id:
        if current_user.role != Role.ADMIN:
            raise HTTPException(403, "Solo un administrador puede vincular cuentas de otros usuarios")
        target = auth_service.get_user_by_id(db, body.user_id)
        if target is None:
            raise HTTPException(404, "Usuario no encontrado")
    email = body.email.strip().lower() if body.email else None
    if email and email != target.email and current_user.role != Role.ADMIN:
        raise HTTPException(403, "Solo puedes vincular con tu propio correo")
    try:
        info = ticket_service.link_account(db, target, email=email)
    except ticket_service.TicketError as exc:
        raise HTTPException(exc.status_code, exc.message)
    audit_service.log(db, "TICKET_LINKED", actor=current_user, target=target,
                      detail=f"accountId={info['account_id']}")
    return LinkOut(linked=True, account_id=info["account_id"],
                   display_name=info.get("display_name"), user=UserBrief.model_validate(target))


@router.delete("/link", status_code=204, summary="Desvincular mi cuenta de Jira")
def unlink_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    ticket_service.unlink_account(db, current_user)
    audit_service.log(db, "TICKET_UNLINKED", actor=current_user)
    return None


# ── Detalle: SIEMPRE al final (rutas literales ya registradas) ──
@router.get("/{key}", response_model=TicketDetailOut, summary="Detalle de un ticket del mesón")
def ticket_detail(
    key: str,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TicketDetailOut:
    try:
        detail = ticket_service.get_ticket(current_user, key)
    except ticket_service.TicketError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return TicketDetailOut(
        key=detail.key,
        url=f"{settings.JIRA_BASE_URL}/browse/{detail.key}" if settings.JIRA_BASE_URL else "",
        summary=detail.summary, status_name=detail.status_name,
        status_category=detail.status_category, priority=detail.priority,
        assignee_name=detail.assignee_name, reporter_name=detail.reporter_name,
        created=detail.created, updated=detail.updated, resolved=detail.resolved,
        description=detail.description, comments_count=len(detail.comments),
        comments=[{"author": c.author, "created": c.created, "body": c.body} for c in detail.comments],
        attachments=[{"filename": a.filename, "size_kb": a.size_kb, "mime": a.mime}
                     for a in detail.attachments],
        is_mine=detail.is_mine,
    )