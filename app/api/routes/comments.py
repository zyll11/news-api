from fastapi import APIRouter, Response, status

from app.api.deps import CommentServiceDep, CurrentUser, PaginationDep
from app.models import Comment
from app.schemas.comment import CommentCreate, CommentRead, CommentUpdate
from app.schemas.common import ErrorResponse, Page

router = APIRouter(tags=["comments"])

_errors: dict[int | str, dict[str, object]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get(
    "/news/{news_id}/comments",
    response_model=Page[CommentRead],
    responses={404: {"model": ErrorResponse}},
)
async def list_comments(
    news_id: int, pagination: PaginationDep, service: CommentServiceDep
) -> Page[CommentRead]:
    return await service.list_for_news(news_id, pagination)


@router.post(
    "/news/{news_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}},
)
async def create_comment(
    news_id: int, data: CommentCreate, user: CurrentUser, service: CommentServiceDep
) -> Comment:
    return await service.create(user, news_id, data)


@router.patch("/comments/{comment_id}", response_model=CommentRead, responses=_errors)
async def update_comment(
    comment_id: int, data: CommentUpdate, user: CurrentUser, service: CommentServiceDep
) -> Comment:
    return await service.update(user, comment_id, data)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_errors)
async def delete_comment(
    comment_id: int, user: CurrentUser, service: CommentServiceDep
) -> Response:
    await service.delete(user, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
