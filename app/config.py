from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    google_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"
    llm_provider: str = "browser_use"
    browser_use_model: str = "bu-latest"
    browser_use_api_key : str =""
    upload_dir: str = "./data/uploads"
    ocr_min_text_length: int = 200
    browser_headless: bool = False
    log_level: str = "INFO"


settings = Settings()
