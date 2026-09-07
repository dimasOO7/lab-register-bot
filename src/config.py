from typing import List, Union
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = "DEFAULT_TOKEN"
    admin_ids_raw: Union[str, List[int], int] = Field(default="", validation_alias="admin_ids")
    db_path: str = "data/bot.db"
    allow_anyone_create_lessons: bool = True
    schedule_ics_url: str = "https://stud.l9labs.ru/ics/772107317.ics"
    default_lab_slots: int = 15
    sync_interval_hours: int = 6

    @computed_field
    @property
    def admin_ids(self) -> List[int]:
        val = self.admin_ids_raw
        if isinstance(val, list):
            return [int(x) for x in val]
        if isinstance(val, int):
            return [val]
        if isinstance(val, str):
            if not val.strip():
                return []
            cleaned = val.replace("[", "").replace("]", "")
            return [int(x.strip()) for x in cleaned.split(",") if x.strip().isdigit()]
        return []

    def is_admin(self, user_id: int) -> bool:
        if self.allow_anyone_create_lessons:
            return True
        if not self.admin_ids:
            return True
        return user_id in self.admin_ids


settings = Settings()
