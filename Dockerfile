FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY lab ./lab
COPY services ./services
# UID comes from `labctl init` so only this user can write host runtime files.
ARG LAB_UID=1000
ARG LAB_GID=1000
USER ${LAB_UID}:${LAB_GID}
CMD ["python", "-m", "services.app", "catalog"]
