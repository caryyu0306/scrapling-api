FROM pyd4vinci/scrapling

WORKDIR /service

RUN python -m pip install --no-cache-dir "scrapling[all]" fastapi "uvicorn[standard]" markdownify beautifulsoup4

COPY main.py .

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
