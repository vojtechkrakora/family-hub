FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY homeboard ./homeboard
COPY homeboard/static/ ./homeboard/static/
RUN test -s homeboard/static/index.html \
    && test -s homeboard/static/app.js \
    && test -s homeboard/static/style.css \
    && test -s homeboard/static/minimap.js \
    && test -s homeboard/static/minimap.svg \
    && test -s homeboard/static/icons/bus.svg
USER 10001:10001
EXPOSE 8091
CMD ["uvicorn", "homeboard.main:app", "--host", "0.0.0.0", "--port", "8091"]
