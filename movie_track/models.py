from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, model_validator


class MovieMetadata(BaseModel):
    rating: str | None = None
    runtime: str | None = None
    language: str | None = None
    listing_date_range: str | None = None
    details: str | None = None


class Showtime(BaseModel):
    movie: str = Field(min_length=1)
    cinema: str = Field(min_length=1)
    theater_type: str = Field(min_length=1)
    starts_at: datetime
    metadata: MovieMetadata = Field(default_factory=MovieMetadata)

    @model_validator(mode="after")
    def require_timezone(self):
        if self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include a UTC offset")
        return self


class Listings(BaseModel):
    showtimes: list[Showtime]


class ImportRequest(BaseModel):
    source_url: HttpUrl
    image_urls: list[HttpUrl] = Field(default_factory=list, max_length=20)
    timezone: str = "America/Nassau"
    context: str = Field(default="", max_length=2000)


class AlertRequest(BaseModel):
    movie: str = Field(min_length=1)
    theater_type: str = Field(min_length=1)
    cinema: str | None = None
    channel: str = Field(pattern="^(email|whatsapp)$")
    recipient: str = Field(min_length=1)
    dry_run: bool = True
