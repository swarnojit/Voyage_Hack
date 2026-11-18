FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 lab && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin lab
COPY --chown=10001:10001 backend/app /srv/app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
