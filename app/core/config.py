import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. Refusing to start "
        "with a guessable default — set a long random SECRET_KEY in "
        "your environment (Render dashboard -> Environment tab)."
    )

ALGORITHM = os.getenv("ALGORITHM", "HS256")

try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    )
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
