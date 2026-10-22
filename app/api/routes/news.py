from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, NewsServiceDep, PaginationDep
from app.schemas.common import ErrorResponse, Page
from app.schemas.news import NewsCreate, NewsRead, NewsUpdate

router = APIRouter(prefix="/news", tags=["news"])

_errors: dict[int | str, dict[str, object]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get("", response_model=Page[NewsRead])
async def list_news(pagination: PaginationDep, service: NewsServiceDep) -> Page[NewsRead]:
    return await service.list(pagination)


@router.post(
    "",
    response_model=NewsRead,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}},
)
async def create_news(data: NewsCreate, user: CurrentUser, service: NewsServiceDep) -> NewsRead:
    return await service.create(user, data)


@router.get("/{news_id}", response_model=NewsRead, responses={404: {"model": ErrorResponse}})
async def get_news(news_id: int, service: NewsServiceDep) -> NewsRead:
    return await service.get(news_id)


@router.patch("/{news_id}", response_model=NewsRead, responses=_errors)
async def update_news(
    news_id: int, data: NewsUpdate, user: CurrentUser, service: NewsServiceDep
) -> NewsRead:
    return await service.update(user, news_id, data)


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_errors)
async def delete_news(news_id: int, user: CurrentUser, service: NewsServiceDep) -> Response:
    await service.delete(user, news_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
