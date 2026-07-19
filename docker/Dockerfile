FROM python:3.14-slim AS runtime

ARG APPLICATION_VERSION

COPY rugbytracker-${APPLICATION_VERSION}.0 /opt/rugbytracker/

WORKDIR /opt/rugbytracker

RUN pip install --no-cache-dir rugby_union_tracker-${APPLICATION_VERSION}-py3-none-any.whl
RUN mkdir -p /var/opt/rugbytracker

ENV RUGBY_TRACKER_ROOT=/opt/rugbytracker
ENV RUGBY_TRACKER_DB=/var/opt/rugbytracker/rugbytracker.db

EXPOSE 8501

CMD ["rugby-tracker", "--server.address=0.0.0.0", "--server.port=8501"]
