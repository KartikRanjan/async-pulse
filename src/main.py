"""
Main application module for async-pulse.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    """Return a greeting message."""
    return {"message": "Hello World"}
