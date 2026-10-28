from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=6000)

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=16)
