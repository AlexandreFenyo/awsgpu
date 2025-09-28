#!/usr/bin/env python3

import logging
logging.basicConfig(level=logging.DEBUG)

from pydantic import BaseModel
import instructor
from typing import List
from openai import OpenAI

class Character(BaseModel):
    name: str
    age: int

class FileList(BaseModel):
    files: List[str]

client = instructor.from_openai(
    OpenAI(
        base_url="http://127.0.0.1:8000/v1",
        api_key="ollama",
    ),
    mode=instructor.Mode.TOOLS,
)

resp = client.chat.completions.create(
    model="qwen2.5:7b-instruct",
    messages=[
        {"role": "user", "content": "Liste les fichiers de /tmp"},
    ],
    response_model=FileList,
)

print(resp)
