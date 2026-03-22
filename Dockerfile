FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["mcp-ros2-logs", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
