FROM python:3.12-slim
WORKDIR /workspace/starter
COPY starter/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=starter/wheels,target=/tmp/wheels \
    if [ -f /tmp/wheels/COMPLETE ]; then \
        pip install --no-index --find-links=/tmp/wheels -r /tmp/requirements.txt; \
    else \
        pip install --timeout 120 --retries 8 -r /tmp/requirements.txt; \
    fi
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.run", "--help"]
